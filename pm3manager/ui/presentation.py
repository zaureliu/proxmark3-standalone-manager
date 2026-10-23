"""Como cada resultado aparece no painel, sem esconder o texto técnico."""

from __future__ import annotations

from dataclasses import dataclass

from pm3manager.models import OperationResult


KIND_LABELS = {
    "informacao": "Informação",
    "aviso": "Aviso",
    "erro": "Erro operacional",
    "critico": "Falha crítica",
    "teste": "Evento de teste",
    "parcial": "Validação parcial",
    "concluida": "Validação concluída",
}


@dataclass(frozen=True)
class ResultPresentation:
    kind: str
    label: str
    status: str
    dialog: str
    pending: bool


def present_result(result: OperationResult, *, environment: str = "producao") -> ResultPresentation:
    if result.outcome == "flash_partial_validation" or result.code == "OK210":
        kind = "parcial"
        status = "Validação parcial"
        dialog = "warning"
        pending = True
    elif result.outcome == "flashed_validated" or result.code == "OK200":
        kind = "concluida"
        status = "Validação concluída"
        dialog = "information"
        pending = False
    elif result.code == "E400":
        kind = "critico"
        status = "Falha crítica"
        dialog = "critical"
        pending = True
    elif result.code == "E010":
        kind = "aviso"
        status = "Aviso"
        dialog = "warning"
        pending = True
    elif not result.ok:
        kind = "erro"
        status = "Erro"
        dialog = "critical"
        pending = True
    elif result.outcome == "verified_restricted" or result.code == "OK202":
        kind = "aviso"
        status = "Aviso"
        dialog = "warning"
        pending = False
    elif result.outcome == "verified":
        kind = "informacao"
        status = "Pronto"
        dialog = "information"
        pending = False
    else:
        kind = "informacao"
        status = ""
        dialog = "information"
        pending = False
    label = KIND_LABELS[kind]
    color_kind = kind
    if environment == "teste":
        label = f"Evento de teste · {label}"
        if kind == "informacao":
            color_kind = "teste"
    return ResultPresentation(
        kind=color_kind,
        label=label,
        status=status,
        dialog=dialog,
        pending=pending,
    )
