"""Manual offline. A ficha não executa RFID e não baixa texto."""

from __future__ import annotations

import json

import pytest

from pm3manager.guide.catalog import build_cards, coverage, load_reviewed, render_plain
from pm3manager.guide.models import FIELD_KEYS, GuideDataError
from pm3manager.guide.search import filter_cards
from pm3manager.guide.urls import is_allowed, is_relative_source
from pm3manager.models import Category, Compatibility, Module
from pm3manager.modules.catalog import load_modules
from pm3manager.paths import project_root
from pm3manager.proxspace.locator import locate
from tests.fakes import module
from tests.support import require_local_proxspace

REQUIRED = (
    "HF_MATTYRUN",
    "LF_EM4100RWC",
    "LF_SAMYRUN",
    "HF_REBLAY",
    "HF_LEGIC_RDV4",
    "HF_ST25_TEAROFF",
    "DANKARMULTI",
    "LF_SKELETON",
)


def _cards():
    library = load_reviewed()
    modules = [
        module(module_id, Compatibility.COMPATIBLE)
        for module_id in library.modules
    ]
    return build_cards(modules, library), library


def _by_id(cards):
    return {card.module_id: card for card in cards}


def test_quarenta_e_uma_fichas_unicas_e_campos_obrigatorios():
    cards, library = _cards()
    ids = [card.module_id for card in cards]
    assert len(cards) == 41
    assert len(set(ids)) == 41
    assert coverage(
        [module(module_id) for module_id in library.modules],
        library,
    ).exact
    assert library.checkout_commit == "dc0110c29d320e04b37ea436ee2924901407ae72"
    for card in cards:
        assert card.module_id
        assert card.friendly_name
        assert card.review_state in {"completa", "parcial", "pendente"}
        assert set(card.fields) == set(FIELD_KEYS)
        for key in FIELD_KEYS:
            assert card.fields[key].value.strip()
            assert card.fields[key].origin
        assert card.fields["start"].value
        assert card.responsible_use
        if card.review_state == "completa":
            assert not card.pending_fields
    assert all(module_id in ids for module_id in REQUIRED)


def test_cobertura_marca_modulo_novo_e_duplicado():
    library = load_reviewed()
    known = module("HF_MATTYRUN")
    fresh = Module(
        id="HF_NOVO_LAB",
        name="HF_NOVO_LAB",
        description="",
        frequency="",
        category=Category.HF,
        compatibility=Compatibility.COMPATIBLE,
        hardware_requirements="",
        limitations=(),
        hal_description="modo ainda sem ficha",
        doc_hardware="",
        requires_flash=False,
        requires_bt=False,
        requires_smartcard=False,
        rdv4_only=False,
        source_file="Makefile.hal",
    )
    report = coverage([known, known, fresh], library)
    assert report.duplicates == ("HF_MATTYRUN",)
    assert report.unreviewed == ("HF_NOVO_LAB",)
    assert not report.exact
    cards = build_cards([fresh], library)
    assert cards[0].review_state == "pendente"
    assert cards[0].fields["description"].value == "modo ainda sem ficha"
    assert cards[0].fields["leds"].origin == "nao_documentado"
    assert "não executa" in cards[0].responsible_use


def test_referencias_e_urls():
    cards, _library = _cards()
    commit = "dc0110c29d320e04b37ea436ee2924901407ae72"
    allowed = f"https://github.com/RfidResearchGroup/proxmark3/blob/{commit}/armsrc/Standalone/hf_mattyrun.c"
    assert is_allowed(allowed)
    assert is_allowed("https://github.com/RfidResearchGroup/proxmark3/wiki/Standalone-mode")
    assert is_allowed("https://github.com/RfidResearchGroup/proxmark3")
    rejected = (
        "http://github.com/RfidResearchGroup/proxmark3",
        "https://github.com/RfidResearchGroup/proxmark3/blob/master/armsrc/Standalone/hf_mattyrun.c",
        "https://example.com/hf_mattyrun.c",
        "javascript:alert(1)",
        "file:///C:/firmware.bin",
        allowed + "?raw=1",
        "https://user:pass@github.com/RfidResearchGroup/proxmark3",
        "",
    )
    assert all(not is_allowed(url) for url in rejected)
    assert is_relative_source("armsrc/Standalone/hf_mattyrun.c")
    assert not is_relative_source("../Makefile")
    assert not is_relative_source("/etc/passwd")
    assert not is_relative_source("https://github.com/RfidResearchGroup/proxmark3")
    for card in cards:
        assert card.references
        for item in card.references:
            if item.url:
                assert is_allowed(item.url)
                if "/blob/" in item.url or "/tree/" in item.url:
                    assert "/master/" not in item.url
                    assert commit in item.url
            if item.path:
                assert is_relative_source(item.path)
        assert any(item.url and item.url.endswith("/wiki/Standalone-mode") for item in card.references)


def test_campos_desconhecidos_e_filtros_so_usam_confirmacao():
    cards, _library = _cards()
    found = _by_id(cards)
    assert all(card.generic_hardware is not True for card in cards)
    assert filter_cards(cards, "", "Hardware genérico") == []
    assert filter_cards(cards, "", "filtro inventado") == []
    hf = filter_cards(cards, "", "HF")
    lf = filter_cards(cards, "", "LF")
    assert found["HF_MATTYRUN"] in hf
    assert found["LF_EM4100RWC"] not in hf
    assert found["LF_EM4100RWC"] in lf
    assert found["LF_SKELETON"] not in lf
    rdv4 = {card.module_id for card in filter_cards(cards, "", "RDV4")}
    assert "HF_LEGIC_RDV4" in rdv4
    assert "HF_MFCSIM" in rdv4
    assert "HF_MATTYRUN" not in rdv4
    assert "LF_EM4100RWC" not in rdv4
    spi = {card.module_id for card in filter_cards(cards, "", "Requer flash SPI")}
    assert "HF_ST25_TEAROFF" in spi
    assert "HF_CARDHOPPER" not in spi
    assert all(card.requires_spi is True for card in cards if card.module_id in spi)
    partial = filter_cards(cards, "", "Documentação parcial")
    assert found["HF_MATTYRUN"] in partial
    assert all(card.review_state == "parcial" for card in partial)
    unverified = filter_cards(cards, "", "Informações não verificadas")
    assert unverified
    assert all(card.pending_fields or card.review_state == "pendente" for card in unverified)
    searched = filter_cards(cards, "matty", "")
    assert [card.module_id for card in searched] == ["HF_MATTYRUN"]
    assert filter_cards(cards, "EM4100RWC", "LF")[0].module_id == "LF_EM4100RWC"
    for card in cards:
        for key in ("leds", "buttons", "functions"):
            field = card.fields[key]
            if field.origin in {"nao_documentado", "nao_verificado"}:
                assert field.value.lower().startswith("não ")


def test_fichas_de_laboratorio_nao_inventam_sequencia():
    cards = _by_id(_cards()[0])
    matty = cards["HF_MATTYRUN"]
    em = cards["LF_EM4100RWC"]
    assert matty.review_state == "parcial"
    assert matty.frequency_band == "HF"
    assert matty.generic_hardware is None
    assert matty.rdv4_exclusive is None
    assert matty.requires_spi is None
    assert "dicionário" in matty.fields["functions"].value
    assert "não implementado" in matty.fields["functions"].value.casefold()
    assert matty.fields["leds"].origin == "nao_verificado"
    assert "BUTTON_HOLD" in matty.fields["buttons"].value
    assert "não verificado" in matty.fields["buttons"].value.casefold()
    assert "WITH_FLASH" in matty.fields["spi_flash"].value
    assert "Hardware Validation" in matty.fields["limitations"].value
    assert matty.fields["start"].source == "armsrc/appmain.c"
    text = render_plain(matty)
    assert "<script>" not in text
    assert "os.system" not in text
    assert em.frequency_band == "LF"
    assert "125 kHz" in em.fields["frequency"].value
    assert em.fields["leds"].origin == "nao_documentado"
    assert em.fields["buttons"].origin == "nao_documentado"
    assert em.fields["persistence"].origin == "nao_verificado"
    assert em.rdv4_exclusive is None
    assert em.requires_spi is None
    assert "SaveIDtoFlash" in em.fields["spi_flash"].value
    for card in (matty, em):
        assert "readme.md" in card.fields["limitations"].value
        assert card.checkout_commit.startswith("dc0110c29d32")


def test_conteudo_malformado(tmp_path):
    target = tmp_path / "reviewed.json"
    target.write_text("{", encoding="utf-8")
    with pytest.raises(GuideDataError):
        load_reviewed(target)
    library = load_reviewed()
    raw = json.loads((project_root() / "pm3manager" / "guide" / "data" / "reviewed.json").read_text(encoding="utf-8"))
    raw["modules"]["HF_MATTYRUN"]["fields"]["leds"]["origin"] = "inventado"
    target.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(GuideDataError):
        load_reviewed(target)
    raw = json.loads((project_root() / "pm3manager" / "guide" / "data" / "reviewed.json").read_text(encoding="utf-8"))
    raw["modules"]["HF_MATTYRUN"]["references"][0]["url"] = "https://github.com/RfidResearchGroup/proxmark3/blob/master/armsrc/Standalone/hf_mattyrun.c"
    target.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(GuideDataError):
        load_reviewed(target)
    raw = json.loads((project_root() / "pm3manager" / "guide" / "data" / "reviewed.json").read_text(encoding="utf-8"))
    raw["modules"]["HF_MATTYRUN"]["references"][0]["path"] = "../secrets.txt"
    target.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(GuideDataError):
        load_reviewed(target)
    assert library.modules["HF_MATTYRUN"]["id"] == "HF_MATTYRUN"


def test_offline_e_sem_execucao(monkeypatch, qapp):
    def blocked(*args, **kwargs):
        raise AssertionError("o manual não consulta a rede")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    monkeypatch.setattr("subprocess.run", blocked)
    cards, library = _cards()
    plain = render_plain(cards[0])
    assert "<" not in plain or "Não" in plain
    from pm3manager.ui.guide_panel import GuidePanel

    panel = GuidePanel([module(card.module_id) for card in cards], parent=None)
    panel.show_module("HF_MATTYRUN")
    qapp.processEvents()
    assert panel.selected_module_id == "HF_MATTYRUN"
    assert "HF_MATTYRUN" in panel.detail.toPlainText()
    assert panel.detail.toPlainText().count("os.system") == 0
    opened = []
    monkeypatch.setattr(
        "pm3manager.ui.guide_panel.QDesktopServices.openUrl",
        lambda url: opened.append(url.toString() if hasattr(url, "toString") else str(url)),
    )
    panel.reference_box.setCurrentIndex(0)
    panel._open()
    assert opened
    assert all(str(url).startswith("https://github.com/RfidResearchGroup/proxmark3") for url in opened)
    index = panel.reference_box.findText("Wiki Standalone, não usada como evidência dos campos")
    assert index >= 0
    panel.reference_box.setItemData(index, "javascript:alert(1)")
    panel.reference_box.setCurrentIndex(index)
    opened.clear()
    panel._open()
    assert opened == []
    assert "não é uma URL permitida" in panel.notice.text()
    guide_root = project_root() / "pm3manager" / "guide"
    for path in guide_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "subprocess" not in text
        assert "os.system" not in text
        assert "urlopen" not in text
    assert library.checkout_note


def test_catalogo_real_coincide_com_as_fichas():
    require_local_proxspace()
    modules = load_modules(locate())
    report = coverage(modules)
    assert len(modules) == 41
    assert report.exact
    assert not report.unreviewed
    assert not report.extra_reviewed
    assert not report.duplicates
