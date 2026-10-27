"""Busca e filtros. Um filtro só usa um campo confirmado."""

from __future__ import annotations

from pm3manager.guide.models import FIELD_LABELS, ModuleCard

FILTERS = (
    "Todas",
    "HF",
    "LF",
    "Hardware genérico",
    "RDV4",
    "Requer flash SPI",
    "Documentação completa",
    "Documentação parcial",
    "Informações não verificadas",
)


def filter_cards(cards: list[ModuleCard], query: str, selected: str) -> list[ModuleCard]:
    needle = (query or "").casefold().strip()
    found: list[ModuleCard] = []
    for card in cards:
        if needle and needle not in _blob(card):
            continue
        if not _filter_matches(card, selected):
            continue
        found.append(card)
    return found


def _filter_matches(card: ModuleCard, selected: str) -> bool:
    if not selected or selected == "Todas":
        return True
    if selected == "HF":
        return card.frequency_band == "HF"
    if selected == "LF":
        return card.frequency_band == "LF"
    if selected == "Hardware genérico":
        return card.generic_hardware is True
    if selected == "RDV4":
        return card.rdv4_exclusive is True
    if selected == "Requer flash SPI":
        return card.requires_spi is True
    if selected == "Documentação completa":
        return card.review_state == "completa"
    if selected == "Documentação parcial":
        return card.review_state == "parcial"
    if selected == "Informações não verificadas":
        return bool(card.pending_fields) or card.review_state == "pendente"
    return False


def _blob(card: ModuleCard) -> str:
    parts = [card.module_id, card.friendly_name, card.catalog_compatibility]
    for key, field in card.fields.items():
        parts.append(FIELD_LABELS.get(key, key))
        parts.append(field.value)
    return " ".join(parts).casefold()
