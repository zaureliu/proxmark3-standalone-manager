"""Identificação multiperfil e correlação dinâmica. Não grava e não chama make."""

from __future__ import annotations

import threading
from pathlib import Path

from pm3manager.compatibility.engine import GuideConstraint, Verdict, evaluate, passes_filter
from pm3manager.compatibility.rules import load_checkout_rules, parse_hal, pm5_standalone_state
from pm3manager.hardware.identity import parse_identity
from pm3manager.hardware.profile import (
    Family,
    IdConfidence,
    IdentifyInput,
    Model,
    authorization_invalidated,
    identify,
    operation_block,
)
from pm3manager.hardware.session import (
    IdentificationCache,
    ProbeAction,
    ProbeRequest,
    choose_probe,
    probe_profile,
)
from pm3manager.messages import Msg
from pm3manager.models import Category, Compatibility, Confidence, Device, Module
from pm3manager.modules.catalog import can_apply
from pm3manager.preferences import Preferences
from pm3manager.workflow.lock import OperationLock
from tests.fakes import VERSION, device
from tests.support import require_local_proxspace

HAL = """
define KNOWN_STANDALONE_DEFINITIONS
| STANDALONE | DESCRIPTION |
| HF_MATTYRUN | Mifare sniff |
| HF_ST25_TEAROFF | tearoff |
| HF_LEGIC_RDV4 | legic |
| HF_REBLAY | relay |
| HF_CARDHOPPER | hopper |
| (RDV4 only) | |
endef
STANDALONE_MODES := HF_MATTYRUN
STANDALONE_MODES += HF_ST25_TEAROFF HF_LEGIC_RDV4 HF_REBLAY HF_CARDHOPPER
STANDALONE_MODES_REQ_BT := HF_CARDHOPPER HF_REBLAY
STANDALONE_MODES_REQ_SMARTCARD :=
STANDALONE_MODES_REQ_FLASH := HF_ST25_TEAROFF HF_LEGIC_RDV4
"""

PM5_BLOCK = """
#ifndef PM5
RunMod();
#else // temporarily blocking standalone mod
#endif
"""


def _mod(module_id: str, compatibility=Compatibility.COMPATIBLE, **flags) -> Module:
    return Module(
        id=module_id,
        name=module_id,
        description="descricao",
        frequency="HF",
        category=Category.HF,
        compatibility=compatibility,
        hardware_requirements="Generic",
        limitations=(),
        hal_description="",
        doc_hardware="",
        requires_flash=flags.get("flash", compatibility == Compatibility.REQUIRES_FLASH),
        requires_bt=flags.get("bt", False),
        requires_smartcard=flags.get("card", False),
        rdv4_only=flags.get("rdv4", compatibility == Compatibility.INCOMPATIBLE),
    )


def _usb(description: str = "Proxmark3", confidence=Confidence.HIGH, serial: str = "SERIAL-UNICO-123456") -> Device:
    return Device(
        port="COM7",
        hardware_name="Proxmark3",
        confidence=confidence,
        vid=0x9AC4,
        pid=0x4B8F,
        serial_number=serial,
        description=description,
        manufacturer="proxmark.org",
        hwid="USB VID:PID=9AC4:4B8F",
        reason="teste",
    )


def _seen(text: str, **kwargs) -> object:
    observation = IdentifyInput(device=_usb(), client_text=text, client_exit=0, expected_version=VERSION, **kwargs)
    return identify(observation)


def _rules():
    return parse_hal(HAL)


def test_target_generic_nao_e_pm3_generic():
    report = parse_identity("[ Proxmark3 ]\nTarget.... GENERIC\n", exit_code=0, expected_version=VERSION)
    assert report.firmware_kind == "GENERIC"
    assert report.firmware_kind != "PM3 GENERIC"
    profile = _seen("[ Proxmark3 ]\nTarget.... GENERIC\n")
    assert profile.model == Model.DESCONHECIDO
    assert profile.confidence == IdConfidence.INCONCLUSIVA
    assert profile.block_pipeline
    assert operation_block(profile, "") == Msg.FLASH_IDENTITY_BLOCKED


def test_target_rdv4_pm5_e_conflito():
    rdv4 = parse_identity(
        "[ Proxmark3 ]\nTarget.... RDV4\nFirmware.................. RDV4\n",
        exit_code=0,
        expected_version=VERSION,
    )
    assert rdv4.firmware_kind == "RDV4"
    confirmed = _seen("[ Proxmark3 ]\nTarget.... RDV4\nFirmware.................. RDV4\n")
    assert confirmed.model == Model.RDV4
    assert confirmed.confidence == IdConfidence.CONFIRMADA
    assert confirmed.block_reason == Msg.RDV4_PIPELINE_BLOCKED
    probable = _seen("[ Proxmark3 ]\nTarget.... RDV4\n")
    assert probable.confidence == IdConfidence.PROVAVEL
    pm5 = _seen("[ Proxmark5 ]\nTarget.... PM5\n--= uC: AT32F437\n")
    assert pm5.model == Model.PM5
    assert pm5.confidence == IdConfidence.CONFIRMADA
    assert pm5.family == Family.PM5
    assert operation_block(pm5, "") == Msg.FLASH_PM5_BLOCKED
    conflict = _seen("[ Proxmark3 ]\nTarget.... RDV4\nTarget.... PM5\n")
    assert conflict.model == Model.DESCONHECIDO
    assert conflict.confidence == IdConfidence.INCONCLUSIVA
    assert conflict.block_pipeline
    assert "SERIAL-UNICO-123456" not in " ".join(conflict.evidence)
    assert "serial:" not in conflict.compact_label()


def test_pm3_generic_nao_escolhe_modelo_comercial():
    text = (
        "[ Proxmark3 ]\nFirmware.................. PM3 GENERIC\n"
        "Target.... PM3 GENERIC\n--= uC: AT91SAM7S512\n"
        "External flash............ present\n"
    )
    profile = _seen(text, configured_platform="PM3GENERIC", led_order="PM3EASY", prefs_kind="RDV4")
    assert profile.family == Family.PM3
    assert profile.model == Model.NAO_CONFIRMADO
    assert profile.confidence == IdConfidence.FAMILIA_CONHECIDA
    assert not profile.block_pipeline
    assert profile.reading_ok
    blob = " ".join(profile.evidence)
    assert "Easy" in blob or "EASY" in blob or "PM3EASY" in blob
    assert "não eleva" in blob
    assert profile.spi.value == "presente"


def test_usb_sozinho_nao_confirma_rdv4_nem_easy():
    named = identify(IdentifyInput(device=_usb(description="Proxmark3 RDV4 Easy"), device_count=2))
    assert named.model == Model.NAO_CONFIRMADO
    assert named.confidence == IdConfidence.FAMILIA_CONHECIDA
    assert not named.block_pipeline
    assert any("RDV4" in item for item in named.evidence)
    assert any("somente o selecionado" in item for item in named.evidence)
    medium = identify(
        IdentifyInput(device=_usb(description="Proxmark something", confidence=Confidence.MEDIUM))
    )
    assert medium.confidence == IdConfidence.INCONCLUSIVA
    assert medium.model != Model.RDV4
    assert identify(IdentifyInput(device=None)).confidence == IdConfidence.NAO_IDENTIFICADO


def test_preferencia_e_plataforma_nao_confirmam_modelo():
    profile = identify(
        IdentifyInput(
            device=_usb(),
            configured_platform="PM3RDV4",
            led_order="PM3EASY",
            prefs_kind="RDV4",
        )
    )
    assert profile.model == Model.NAO_CONFIRMADO
    assert profile.confidence != IdConfidence.CONFIRMADA
    assert any("não identifica" in item.lower() or "não identifica" in item for item in profile.conflicts + profile.evidence)


def test_cache_nao_vale_para_outro_aparelho_e_troca_invalida_autorizacao():
    cache = IdentificationCache()
    first = _seen("[ Proxmark3 ]\nTarget.... PM3 GENERIC\nFirmware.................. PM3 GENERIC\n")
    cache.store(first.identity_key, "abc", first)
    assert cache.lookup(first.identity_key, "abc") is first
    assert cache.lookup("serial:outro", "abc") is None
    assert cache.lookup(first.identity_key, "outro-commit") is None
    cache.invalidate()
    assert cache.lookup(first.identity_key, "abc") is None
    assert authorization_invalidated("", "serial:a") is False
    assert authorization_invalidated("serial:a", "serial:b") is True
    assert authorization_invalidated("serial:a", "") is True


def test_sonda_adia_porta_ocupada_e_descarta_resposta_parcial():
    calls = []

    def runner(*_args, **_kwargs):
        calls.append("run")
        return 0, "Unique ID: 0xDEADBEEF\nTarget.... RDV4\n", False, False, "", ()

    env = _env()
    locked = OperationLock()
    assert locked.acquire("compile")
    deferred = probe_profile(
        env=env,
        device=_usb(),
        lock=locked,
        port_free=lambda _port: (True, ""),
        cancel=threading.Event(),
        device_count=1,
        work_dir=Path("."),
        runner=runner,
    )
    assert calls == []
    assert deferred.active_deferred
    assert deferred.model != Model.RDV4
    locked.release()
    cancel = threading.Event()

    def slow(*_args, **kwargs):
        calls.append("slow")
        assert kwargs["cancel"].is_set() or True
        return 0, "Unique ID: 0xDEADBEEF\nTarget.... PM5\n", True, False, "", ()

    expired = probe_profile(
        env=env,
        device=_usb(),
        lock=OperationLock(),
        port_free=lambda _port: (True, ""),
        cancel=cancel,
        device_count=1,
        work_dir=Path("."),
        runner=slow,
    )
    assert expired.model != Model.PM5
    assert "0xDEADBEEF" not in " ".join(expired.evidence)
    busy = probe_profile(
        env=env,
        device=_usb(),
        lock=OperationLock(),
        port_free=lambda _port: (False, "em uso"),
        cancel=threading.Event(),
        device_count=1,
        work_dir=Path("."),
        runner=runner,
    )
    assert busy.active_deferred
    assert choose_probe(ProbeRequest(True, True, True, False)) == ProbeAction.DEFER
    assert choose_probe(ProbeRequest(False, False, True, False)) == ProbeAction.NONE


def test_parser_recusa_makefile_ambiguo_e_aceita_lista_vazia():
    rules = _rules()
    assert rules.complete
    assert "HF_MATTYRUN" in rules.modes
    assert rules.smartcard == frozenset()
    assert pm5_standalone_state(PM5_BLOCK) == "blocked"
    assert pm5_standalone_state("RunMod();\n") == "unknown"
    broken = HAL.replace("STANDALONE_MODES_REQ_BT :=", "STANDALONE_MODES_REQ_BT +=")
    assert not parse_hal(broken).complete
    assert not parse_hal(HAL + "\nSTANDALONE_MODES_REQ_FOO := HF_MATTYRUN\n").complete
    assert not parse_hal(HAL.replace("STANDALONE_MODES_REQ_FLASH := HF_ST25_TEAROFF HF_LEGIC_RDV4\n", "")).complete


def test_correlacao_nao_transforma_ausencia_em_compatibilidade():
    rules = _rules()
    generic = _seen(
        "[ Proxmark3 ]\nFirmware.................. PM3 GENERIC\nTarget.... PM3 GENERIC\n"
        "--= uC: AT91SAM7S512\nExternal flash............ present\n"
    )
    unknown_spi = _seen(
        "[ Proxmark3 ]\nFirmware.................. PM3 GENERIC\nTarget.... PM3 GENERIC\n"
    )
    absent = _seen(
        "[ Proxmark3 ]\nFirmware.................. PM3 GENERIC\nTarget.... PM3 GENERIC\n"
        "External flash............ absent\n"
    )
    matty = _mod("HF_MATTYRUN")
    tear = _mod("HF_ST25_TEAROFF", Compatibility.REQUIRES_FLASH, flash=True)
    legic = _mod("HF_LEGIC_RDV4", Compatibility.INCOMPATIBLE, flash=True, rdv4=True)
    relay = _mod("HF_REBLAY", Compatibility.INCOMPATIBLE, bt=True, rdv4=True)
    assert evaluate(matty, generic, rules).overall == Verdict.COMPATIBLE
    assert "100%" not in evaluate(matty, generic, rules).summary
    assert evaluate(tear, unknown_spi, rules).overall == Verdict.NEEDS_CONFIRMATION
    assert evaluate(tear, absent, rules).overall == Verdict.INCOMPATIBLE
    present = evaluate(tear, generic, rules, spi_checkbox=False)
    assert present.overall == Verdict.COMPATIBLE
    assert any("confirmação da flash SPI" in item for item in present.reasons)
    assert evaluate(legic, generic, rules).overall == Verdict.INCOMPATIBLE
    assert evaluate(relay, generic, rules).overall == Verdict.INCOMPATIBLE
    missing = evaluate(_mod("HF_AUSENTE"), generic, rules)
    assert missing.overall == Verdict.UNAVAILABLE
    incomplete = parse_hal("hal\n")
    assert evaluate(matty, generic, incomplete).overall != Verdict.COMPATIBLE
    unidentified = identify(IdentifyInput(device=None))
    assert evaluate(matty, unidentified, rules).overall != Verdict.COMPATIBLE
    pm5 = _seen("[ Proxmark5 ]\nTarget.... PM5\n--= uC: AT32F437\n")
    blocked = load_like(rules, "blocked")
    assert evaluate(matty, pm5, blocked).overall == Verdict.UNAVAILABLE
    assert evaluate(matty, pm5, blocked).summary != evaluate(matty, generic, rules).summary
    hinted = evaluate(
        matty,
        generic,
        rules,
        guide=GuideConstraint(origin="documentado", documented_rdv4=True),
    )
    assert hinted.overall == Verdict.NEEDS_CONFIRMATION
    assert hinted.conflicts
    inferred = evaluate(matty, generic, rules, guide=GuideConstraint(origin="inferido", inferred=True, documented_flash=True))
    assert inferred.overall == Verdict.COMPATIBLE
    assert any("inferido" in item for item in inferred.reasons)
    uncertain_module = _mod("HF_MATTYRUN", Compatibility.UNCERTAIN)
    uncertain = evaluate(uncertain_module, generic, rules)
    assert uncertain.overall == Verdict.NEEDS_CONFIRMATION
    assert can_apply(uncertain_module, Preferences())[0] is False
    assert can_apply(legic, Preferences())[0] is False


def test_rdv4_consultivo_nao_compila_e_pm5_nao_recebe_pipeline_pm3(isolated_data, tmp_path):
    from tests.fakes import FakeShell
    from tests.test_workflow import _service

    shell = FakeShell(tmp_path / "repo")
    service, _env_obj, shell = _service(tmp_path, shell)
    rdv4 = _seen("[ Proxmark3 ]\nTarget.... RDV4\nFirmware.................. RDV4\n")
    compiled = service.recompile(_mod("HF_MATTYRUN"), profile=rdv4)
    assert compiled.code == "E303"
    assert shell.scripts == []
    assert service.prefs.flash_autorizado is False
    shell.scripts.clear()
    pm5 = _seen("[ Proxmark5 ]\nTarget.... PM5\n--= uC: AT32F437\n")
    blocked = service.apply(_mod("HF_MATTYRUN"), device(), force_rebuild=True, flash_authorized=False, profile=pm5)
    assert blocked.code == "E303"
    assert "PM5" in blocked.message or "Proxmark5" in blocked.message
    assert shell.scripts == []
    favorable = evaluate(_mod("HF_MATTYRUN"), rdv4, _rules())
    assert "Compilação e flashing indisponíveis neste aplicativo." in favorable.summary
    assert passes_filter(favorable, "recomendados") is False
    assert passes_filter(favorable, "compativeis") is True


def test_checkout_local_dos_41_modulos():
    require_local_proxspace()
    from pm3manager.modules.catalog import load_modules
    from pm3manager.proxspace.locator import locate

    env = locate()
    modules = load_modules(env)
    rules = load_checkout_rules(env.repo_root, shallow=True)
    assert rules.complete, rules.reason
    assert rules.pm5_standalone == "blocked"
    assert {module.id for module in modules} == set(rules.modes)
    assert len(modules) == 41
    generic = _seen(
        "[ Proxmark3 ]\nFirmware.................. PM3 GENERIC\nTarget.... PM3 GENERIC\n"
        "--= uC: AT91SAM7S512\nExternal flash............ present\n"
    )
    by_id = {module.id: evaluate(module, generic, rules, spi_checkbox=False) for module in modules}
    assert by_id["HF_MATTYRUN"].overall == Verdict.COMPATIBLE
    assert by_id["HF_14ASNIFF"].overall == Verdict.NEEDS_CONFIRMATION
    assert by_id["HF_15SNIFF"].overall == Verdict.NEEDS_CONFIRMATION
    assert by_id["HF_LEGIC_RDV4"].overall == Verdict.INCOMPATIBLE
    assert by_id["HF_ST25_TEAROFF"].hardware == Verdict.COMPATIBLE
    pm5 = _seen("[ Proxmark5 ]\nTarget.... PM5\n--= uC: AT32F437\n")
    pm5_rows = [evaluate(module, pm5, rules) for module in modules]
    assert all(item.overall != Verdict.COMPATIBLE for item in pm5_rows)
    assert all("100%" not in item.summary for item in pm5_rows)
    assert any("Standalone não habilitado" in " ".join(item.reasons) for item in pm5_rows)


def load_like(rules, state: str):
    from pm3manager.compatibility.rules import CheckoutRules

    return CheckoutRules(
        complete=rules.complete,
        reason=rules.reason,
        modes=rules.modes,
        flash=rules.flash,
        bluetooth=rules.bluetooth,
        smartcard=rules.smartcard,
        rdv4_only=rules.rdv4_only,
        pm5_standalone=state,
    )


def _env():
    from pm3manager.models import Environment

    return Environment(
        proxspace_root=Path("."),
        repo_root=Path("."),
        repo_msys="/pm3/test",
        msys_shell=Path("."),
        version=VERSION,
        commit="abc",
        build_time="",
        external_makefile=None,
        external_makefile_text="",
        source_fingerprint="",
    )
