"""Fatos com procedência. Um valor configurado não é tratado como detecção."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pm3manager.models import Device, Module


class Origin(str, Enum):
    DETECTED = "detectado"
    CONFIGURED = "configurado"
    DOCUMENTED = "documentado"
    INFERRED = "inferido"
    UNVERIFIED = "nao_verificado"
    UNAVAILABLE = "indisponivel"


class Severity(str, Enum):
    INFO = "informacao"
    PASS = "aprovado"
    WARNING = "aviso"
    BLOCKING = "impeditivo"
    UNKNOWN = "desconhecido"


class Verdict(str, Enum):
    COMPATIBLE = "compativel_segundo_verificacoes"
    PARTIAL = "compatibilidade_parcial"
    NEEDS_CONFIRMATION = "requer_confirmacao"
    INCOMPATIBLE = "incompatibilidade_identificada"
    INSUFFICIENT = "informacoes_insuficientes"


ORIGIN_LABEL = {
    Origin.DETECTED: "Detectado",
    Origin.CONFIGURED: "Configurado",
    Origin.DOCUMENTED: "Documentado",
    Origin.INFERRED: "Inferido",
    Origin.UNVERIFIED: "Não verificado",
    Origin.UNAVAILABLE: "Indisponível",
}

SEVERITY_LABEL = {
    Severity.INFO: "Informação",
    Severity.PASS: "Verificação aprovada",
    Severity.WARNING: "Aviso",
    Severity.BLOCKING: "Problema impeditivo",
    Severity.UNKNOWN: "Desconhecido",
}

VERDICT_LABEL = {
    Verdict.COMPATIBLE: "Compatível segundo verificações disponíveis",
    Verdict.PARTIAL: "Compatibilidade parcial",
    Verdict.NEEDS_CONFIRMATION: "Requer confirmação",
    Verdict.INCOMPATIBLE: "Incompatibilidade identificada",
    Verdict.INSUFFICIENT: "Informações insuficientes",
}

DISCLAIMER = (
    "Este resultado é um diagnóstico consultivo. Não certifica compatibilidade, "
    "não altera o Makefile e não autoriza gravação."
)

NOT_IDENTIFIED = "Não identificado"
NOT_VERIFIED = "Não verificado"
NOT_DOCUMENTED = "Não documentado"
UNAVAILABLE = "Indisponível"


@dataclass(frozen=True)
class Fact:
    key: str
    label: str
    value: str
    origin: Origin
    justification: str

    def export(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "origin": self.origin.value,
            "origin_label": ORIGIN_LABEL[self.origin],
            "justification": self.justification,
        }


@dataclass(frozen=True)
class Check:
    code: str
    title: str
    severity: Severity
    message: str
    origin: Origin
    justification: str

    def export(self) -> dict[str, str]:
        return {
            "code": self.code,
            "title": self.title,
            "severity": self.severity.value,
            "severity_label": SEVERITY_LABEL[self.severity],
            "message": self.message,
            "origin": self.origin.value,
            "origin_label": ORIGIN_LABEL[self.origin],
            "justification": self.justification,
        }


@dataclass
class Observation:
    """Entrada já coletada. A análise não abre porta, não chama o cliente e não grava."""

    generated_at: str
    app_version: str
    mode: str = "full"
    blocked_reason: str = ""
    devices: list[Device] = field(default_factory=list)
    selected: Device | None = None
    port_free: bool | None = None
    port_message: str = ""
    client_attempted: bool = False
    client_output: str = ""
    client_exit: int = 0
    client_timed_out: bool = False
    client_cancelled: bool = False
    client_error: str = ""
    commands: tuple[str, ...] = ()
    env_present: bool = False
    proxspace_present: bool = False
    checkout_present: bool = False
    checkout_name: str = ""
    version_file: str = ""
    version_token: str = ""
    essential: dict[str, bool] = field(default_factory=dict)
    toolchain_found: bool | None = None
    git_state: str = "indisponivel"
    git_commit: str = ""
    git_shallow: bool | None = None
    git_dirty: bool | None = None
    git_dirty_count: int = 0
    makefile_present: bool | None = None
    makefile: dict[str, list[str]] = field(default_factory=dict)
    intended_platform: str = ""
    intended_standalone: str = ""
    intended_extras: str = ""
    intended_led_order: str = ""
    intended_platform_size: str = ""
    prefs_mcu: str = ""
    prefs_firmware_kind: str = ""
    prefs_external_flash: str = ""
    spi_confirmed: bool = False
    module: Module | None = None
    module_confirmed_uncertain: bool = False


@dataclass
class DiagnosticReport:
    generated_at: str
    app_version: str
    mode: str
    context_key: str
    verdict: Verdict
    summary: str
    facts: list[Fact] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    commands: tuple[str, ...] = ()
    technical: str = ""
    cancelled: bool = False
    timed_out: bool = False
    client_attempted: bool = False

    @property
    def verdict_label(self) -> str:
        return VERDICT_LABEL[self.verdict]

    def facts_by_origin(self, origin: Origin) -> list[Fact]:
        return [item for item in self.facts if item.origin is origin]

    def checks_by_severity(self, severity: Severity) -> list[Check]:
        return [item for item in self.checks if item.severity is severity]
