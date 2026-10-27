"""Monta uma ficha por identificador do catálogo. Não recria os IDs."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from pm3manager.guide.models import (
    FIELD_KEYS,
    ORIGINS,
    RESPONSIBLE_USE,
    Evidence,
    GuideDataError,
    ModuleCard,
    Reference,
    blank,
)
from pm3manager.guide.urls import is_allowed, is_relative_source
from pm3manager.models import COMPATIBILITY_LABEL, Module

_BAND = {
    "Low Frequency (LF)": "LF",
    "High Frequency (HF)": "HF",
    "Multimodo": "MULTI",
    "Outros": "OTHER",
}


@dataclass(frozen=True)
class ReviewedLibrary:
    reviewed_on: str
    checkout_commit: str
    checkout_note: str
    common_start: Evidence
    modules: dict[str, dict]


@dataclass(frozen=True)
class Coverage:
    catalog_ids: tuple[str, ...]
    reviewed_ids: tuple[str, ...]
    duplicates: tuple[str, ...]
    unreviewed: tuple[str, ...]
    extra_reviewed: tuple[str, ...]

    @property
    def exact(self) -> bool:
        return not self.duplicates and not self.unreviewed and not self.extra_reviewed


def reviewed_path() -> Path:
    local = Path(__file__).resolve().parent / "data" / "reviewed.json"
    if local.is_file():
        return local
    frozen = getattr(sys, "_MEIPASS", "")
    if frozen:
        bundled = Path(frozen) / "pm3manager" / "guide" / "data" / "reviewed.json"
        if bundled.is_file():
            return bundled
    return local


def load_reviewed(path: Path | None = None) -> ReviewedLibrary:
    target = path or reviewed_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuideDataError(f"Ficha revisada ilegível: {target.name}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("modules"), dict):
        raise GuideDataError("O arquivo de fichas precisa ser um objeto com a chave modules.")
    modules = raw["modules"]
    if len(modules) != len(set(modules)):
        raise GuideDataError("Há identificadores duplicados nas fichas.")
    start = _evidence(raw.get("common_start"), "início comum")
    for module_id, payload in modules.items():
        if not isinstance(module_id, str) or not isinstance(payload, dict):
            raise GuideDataError("Ficha malformada.")
        if payload.get("id", module_id) != module_id:
            raise GuideDataError(f"O identificador interno não confere com {module_id}.")
        state = payload.get("review_state")
        if state not in {"completa", "parcial", "pendente"}:
            raise GuideDataError(f"Estado de revisão inválido em {module_id}.")
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            raise GuideDataError(f"Campos ausentes em {module_id}.")
        for key in FIELD_KEYS:
            if key == "start" and key not in fields:
                continue
            _evidence(fields.get(key), f"{module_id}.{key}")
        for item in payload.get("references") or []:
            _reference(item)
    return ReviewedLibrary(
        reviewed_on=str(raw.get("reviewed_on") or ""),
        checkout_commit=str(raw.get("checkout_commit") or ""),
        checkout_note=str(raw.get("checkout_note") or ""),
        common_start=start,
        modules=modules,
    )


def build_cards(modules: list[Module], library: ReviewedLibrary | None = None) -> list[ModuleCard]:
    reviewed = library or load_reviewed()
    cards: list[ModuleCard] = []
    seen: set[str] = set()
    for module in modules:
        if module.id in seen:
            continue
        seen.add(module.id)
        payload = reviewed.modules.get(module.id)
        if payload is None:
            cards.append(_pending(module, reviewed))
        else:
            cards.append(_from_payload(module, payload, reviewed))
    return cards


def coverage(modules: list[Module], library: ReviewedLibrary | None = None) -> Coverage:
    reviewed = library or load_reviewed()
    catalog_ids = tuple(module.id for module in modules)
    duplicates = tuple(sorted({module_id for module_id in catalog_ids if catalog_ids.count(module_id) > 1}))
    unique = tuple(dict.fromkeys(catalog_ids))
    reviewed_ids = tuple(reviewed.modules)
    unreviewed = tuple(module_id for module_id in unique if module_id not in reviewed.modules)
    extra = tuple(module_id for module_id in reviewed_ids if module_id not in unique)
    return Coverage(unique, reviewed_ids, duplicates, unreviewed, extra)


def render_plain(card: ModuleCard) -> str:
    """Texto puro. Não é HTML e não é interpretado como comando."""
    lines = [
        card.module_id,
        card.friendly_name,
        f"Revisão: {card.review_state}",
        f"Classificação do aplicativo: {card.catalog_compatibility}",
        card.responsible_use,
        "",
    ]
    for key in FIELD_KEYS:
        field = card.fields[key]
        lines.append(f"{key}: {field.value}")
        lines.append(f"origem: {field.origin}; fonte: {field.source or 'não indicada'}")
    lines.append("")
    lines.append("Referências")
    for item in card.references:
        lines.append(item.url or item.path or item.label)
    return "\n".join(_plain(line) for line in lines)


def _from_payload(module: Module, payload: dict, library: ReviewedLibrary) -> ModuleCard:
    fields_raw = payload.get("fields") or {}
    fields = {key: _evidence(fields_raw.get(key), key) if key in fields_raw else blank() for key in FIELD_KEYS}
    if "start" not in fields_raw:
        fields["start"] = library.common_start
    return ModuleCard(
        module_id=module.id,
        friendly_name=_plain(str(payload.get("friendly_name") or module.id)),
        review_state=str(payload.get("review_state") or "pendente"),
        frequency_band=str(payload.get("frequency_band") or _BAND.get(module.category.value, "")),
        generic_hardware=_optional_bool(payload.get("generic_hardware")),
        rdv4_exclusive=_optional_bool(payload.get("rdv4_exclusive")),
        requires_spi=_optional_bool(payload.get("requires_spi")),
        fields=fields,
        references=tuple(_reference(item) for item in payload.get("references") or []),
        reviewed_on=str(payload.get("reviewed_on") or library.reviewed_on),
        checkout_commit=str(payload.get("checkout_commit") or library.checkout_commit),
        catalog_compatibility=COMPATIBILITY_LABEL[module.compatibility],
    )


def _pending(module: Module, library: ReviewedLibrary) -> ModuleCard:
    description = module.hal_description.strip()
    fields = {key: blank() for key in FIELD_KEYS}
    if description:
        fields["description"] = Evidence(
            description,
            "documentado",
            module.source_file or "Makefile.hal",
            "Descrição curta do Makefile.hal carregado com o catálogo. Os demais campos não foram revisados.",
        )
    fields["start"] = library.common_start
    fields["limitations"] = Evidence(
        "Módulo novo em relação às fichas revisadas. O comportamento não foi preenchido.",
        "nao_verificado",
        "",
        "O verificador marcou este identificador como ainda sem documentação revisada.",
    )
    return ModuleCard(
        module_id=module.id,
        friendly_name=description or module.id,
        review_state="pendente",
        frequency_band=_BAND.get(module.category.value, ""),
        generic_hardware=None,
        rdv4_exclusive=True if module.rdv4_only or "_RDV4" in module.id else None,
        requires_spi=True if module.requires_flash else None,
        fields=fields,
        references=(),
        reviewed_on="",
        checkout_commit=library.checkout_commit,
        catalog_compatibility=COMPATIBILITY_LABEL[module.compatibility],
    )


def _evidence(payload: object, label: str) -> Evidence:
    if not isinstance(payload, dict):
        raise GuideDataError(f"Evidência inválida em {label}.")
    origin = str(payload.get("origin") or "")
    if origin not in ORIGINS:
        raise GuideDataError(f"Procedência inválida em {label}.")
    value = _plain(str(payload.get("value") or ""))
    if not value:
        raise GuideDataError(f"Valor vazio em {label}.")
    return Evidence(
        value,
        origin,
        _plain(str(payload.get("source") or "")),
        _plain(str(payload.get("justification") or "")),
    )


def _reference(payload: object) -> Reference:
    if not isinstance(payload, dict):
        raise GuideDataError("Referência malformada.")
    url = str(payload.get("url") or "").strip()
    path = str(payload.get("path") or "").strip()
    label = _plain(str(payload.get("label") or path or url or "referência"))
    if url and not is_allowed(url):
        raise GuideDataError(f"URL não permitida: {label}")
    if path and not is_relative_source(path):
        raise GuideDataError(f"Caminho de fonte inválido: {label}")
    if not url and not path:
        raise GuideDataError("Referência sem destino.")
    return Reference(label, url, path)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise GuideDataError("Campo booleano opcional malformado.")


def _plain(value: str) -> str:
    return value.replace("\x00", "").replace("\r", "")
