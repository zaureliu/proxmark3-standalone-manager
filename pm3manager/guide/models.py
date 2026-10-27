"""Fichas do manual. Campo sem evidência fica explícito."""

from __future__ import annotations

from dataclasses import dataclass

NOT_DOCUMENTED = "Não documentado"
NOT_VERIFIED = "Não verificado"

RESPONSIBLE_USE = (
    "Use apenas cartões, tags e sistemas próprios ou com autorização. "
    "Esta ficha é informativa e não executa leitura, emulação nem clonagem."
)

FIELD_KEYS = (
    "description",
    "frequency",
    "functions",
    "hardware",
    "dependencies",
    "memory",
    "spi_flash",
    "leds",
    "buttons",
    "start",
    "stop",
    "persistence",
    "limitations",
)

FIELD_LABELS = {
    "description": "Descrição",
    "frequency": "Frequência ou tecnologia",
    "functions": "Funções principais",
    "hardware": "Hardware suportado",
    "dependencies": "Dependências especiais",
    "memory": "Requisitos conhecidos de memória",
    "spi_flash": "Flash SPI",
    "leds": "LEDs",
    "buttons": "Botão físico",
    "start": "Como iniciar o modo Standalone",
    "stop": "Como encerrar ou alternar",
    "persistence": "Persistência após desligar",
    "limitations": "Limitações e advertências",
}

ORIGINS = {
    "detectado",
    "configurado",
    "documentado",
    "inferido",
    "nao_documentado",
    "nao_verificado",
    "indisponivel",
}

ORIGIN_LABEL = {
    "detectado": "Detectado",
    "configurado": "Configurado",
    "documentado": "Documentado",
    "inferido": "Inferido",
    "nao_documentado": "Não documentado",
    "nao_verificado": "Não verificado",
    "indisponivel": "Indisponível",
}

REVIEW_LABEL = {
    "completa": "Documentação completa",
    "parcial": "Documentação parcial",
    "pendente": "Sem revisão",
}


class GuideDataError(ValueError):
    pass


@dataclass(frozen=True)
class Evidence:
    value: str
    origin: str
    source: str
    justification: str


@dataclass(frozen=True)
class Reference:
    label: str
    url: str = ""
    path: str = ""


@dataclass(frozen=True)
class ModuleCard:
    module_id: str
    friendly_name: str
    review_state: str
    frequency_band: str
    generic_hardware: bool | None
    rdv4_exclusive: bool | None
    requires_spi: bool | None
    fields: dict[str, Evidence]
    references: tuple[Reference, ...]
    reviewed_on: str
    checkout_commit: str
    catalog_compatibility: str
    responsible_use: str = RESPONSIBLE_USE

    @property
    def pending_fields(self) -> tuple[str, ...]:
        return tuple(
            key
            for key in FIELD_KEYS
            if self.fields[key].origin in {"nao_documentado", "nao_verificado", "indisponivel"}
        )

    @property
    def confirmed_fields(self) -> tuple[str, ...]:
        return tuple(key for key in FIELD_KEYS if key not in self.pending_fields)


def unknown(value: str, origin: str, source: str = "", justification: str = "") -> Evidence:
    return Evidence(value, origin, source, justification)


def blank(origin: str = "nao_documentado") -> Evidence:
    value = NOT_DOCUMENTED if origin == "nao_documentado" else NOT_VERIFIED
    return Evidence(value, origin, "", "Sem evidência revisada para este campo.")
