"""Três níveis de compatibilidade. Ausência de evidência não vira compatibilidade."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pm3manager.compatibility.rules import CheckoutRules
from pm3manager.hardware.profile import (
    Family,
    HardwareProfile,
    IdConfidence,
    Model,
    OperationalSupport,
    ResourceState,
)
from pm3manager.models import Compatibility, Module

_FAVORABLE = (
    "Compatibilidade técnica potencialmente favorável. "
    "Compilação e flashing indisponíveis neste aplicativo."
)


class Verdict(str, Enum):
    COMPATIBLE = "compativel"
    NEEDS_CONFIRMATION = "requer_confirmacao"
    INCOMPATIBLE = "incompativel"
    INSUFFICIENT = "insuficiente"
    UNAVAILABLE = "indisponivel"


VERDICT_MARKER = {
    Verdict.COMPATIBLE: "✓ Compatível segundo verificações",
    Verdict.NEEDS_CONFIRMATION: "? Requer confirmação",
    Verdict.INCOMPATIBLE: "✕ Incompatível",
    Verdict.INSUFFICIENT: "○ Informações insuficientes",
    Verdict.UNAVAILABLE: "– Indisponível neste firmware",
}

FILTERS = (
    ("recomendados", "Recomendados para este dispositivo"),
    ("compativeis", "Compatíveis"),
    ("confirmacao", "Requerem confirmação"),
    ("incompativeis", "Incompatíveis"),
    ("todos", "Todos"),
)


@dataclass(frozen=True)
class GuideConstraint:
    origin: str = ""
    documented_rdv4: bool | None = None
    documented_flash: bool | None = None
    inferred: bool = False


@dataclass(frozen=True)
class ModuleAssessment:
    module_id: str
    hardware: Verdict
    firmware: Verdict
    operational: OperationalSupport
    overall: Verdict
    summary: str
    reasons: tuple[str, ...]
    conflicts: tuple[str, ...] = ()
    stale: bool = False

    def marker(self) -> str:
        return VERDICT_MARKER[self.overall]


def passes_filter(assessment: ModuleAssessment | None, selected: str) -> bool:
    if selected in {"", "todos"}:
        return True
    if assessment is None or assessment.stale:
        return False
    if selected == "recomendados":
        return (
            assessment.overall == Verdict.COMPATIBLE
            and assessment.hardware == Verdict.COMPATIBLE
            and assessment.firmware == Verdict.COMPATIBLE
            and assessment.operational == OperationalSupport.VALIDADO
        )
    if selected == "compativeis":
        return assessment.overall == Verdict.COMPATIBLE
    if selected == "confirmacao":
        return assessment.overall == Verdict.NEEDS_CONFIRMATION
    if selected == "incompativeis":
        return assessment.overall in {Verdict.INCOMPATIBLE, Verdict.UNAVAILABLE}
    return True


def evaluate_all(
    modules: list[Module],
    profile: HardwareProfile | None,
    rules: CheckoutRules,
    *,
    guides: dict[str, GuideConstraint] | None = None,
    spi_checkbox: bool = False,
) -> dict[str, ModuleAssessment]:
    hints = guides or {}
    return {
        module.id: evaluate(
            module,
            profile,
            rules,
            guide=hints.get(module.id),
            spi_checkbox=spi_checkbox,
        )
        for module in modules
    }


def evaluate(
    module: Module,
    profile: HardwareProfile | None,
    rules: CheckoutRules,
    *,
    guide: GuideConstraint | None = None,
    spi_checkbox: bool = False,
) -> ModuleAssessment:
    reasons: list[str] = []
    conflicts: list[str] = []
    if profile is not None and profile.stale:
        reasons.append("A avaliação anterior é de outro momento e não foi reutilizada.")
    current = None if profile is None or profile.stale else profile
    if current is None:
        current = HardwareProfile(
            family=Family.DESCONHECIDA,
            model=Model.DESCONHECIDO,
            confidence=IdConfidence.NAO_IDENTIFICADO,
            operational=OperationalSupport.NAO_AVALIADO,
        )
        reasons.append("Não há perfil de hardware para este módulo.")
    hardware, firmware, operational = _levels(module, current, rules, reasons, conflicts, spi_checkbox)
    guide_conflicts: list[str] = []
    _guide(module, rules, guide, reasons, guide_conflicts)
    for note in rules.warnings:
        if note not in reasons:
            reasons.append(note)
    if current.version_mismatch:
        reasons.append("O firmware instalado e o checkout local não têm correspondência comprovada.")
    for note in current.conflicts:
        if note not in conflicts:
            conflicts.append(note)
    overall = _overall(hardware, firmware)
    if guide_conflicts and overall == Verdict.COMPATIBLE:
        overall = Verdict.NEEDS_CONFIRMATION
        reasons.append("Há conflito entre o manual e o Makefile. Isso não foi tratado como compatibilidade resolvida.")
    if module.compatibility == Compatibility.UNCERTAIN and overall == Verdict.COMPATIBLE:
        overall = Verdict.NEEDS_CONFIRMATION
        reasons.append(
            "O catálogo revisado ainda pede confirmação para este modo. "
            "Essa divergência não foi tratada como compatibilidade."
        )
    conflicts.extend(guide_conflicts)
    if not rules.complete and overall == Verdict.COMPATIBLE:
        overall = Verdict.INSUFFICIENT
        reasons.append("As regras do checkout não foram lidas por completo. O módulo não foi promovido a compatível.")
    summary = _summary(overall, operational)
    if "100%" in summary or any("100%" in item for item in reasons):
        raise RuntimeError("a avaliação não pode afirmar 100%")
    return ModuleAssessment(
        module_id=module.id,
        hardware=hardware,
        firmware=firmware,
        operational=operational,
        overall=overall,
        summary=summary,
        reasons=tuple(reasons),
        conflicts=tuple(conflicts),
        stale=bool(profile is not None and profile.stale),
    )


def _levels(
    module: Module,
    profile: HardwareProfile,
    rules: CheckoutRules,
    reasons: list[str],
    conflicts: list[str],
    spi_checkbox: bool,
) -> tuple[Verdict, Verdict, OperationalSupport]:
    operational = profile.operational
    if _is_pm5(profile):
        reasons.append("O perfil PM5 não herda os requisitos físicos dos modos PM3.")
        hardware = Verdict.INSUFFICIENT
        if rules.pm5_standalone == "blocked":
            reasons.append("Standalone não habilitado no firmware PM5 analisado.")
            firmware = Verdict.UNAVAILABLE
        elif not rules.complete:
            reasons.append(rules.reason or "As regras do checkout PM5 não foram lidas com segurança.")
            firmware = Verdict.INSUFFICIENT
        else:
            reasons.append("Não há evidência de que este firmware PM5 ofereça o modo Standalone pedido.")
            firmware = Verdict.INSUFFICIENT
        return hardware, firmware, operational
    if not rules.complete:
        reasons.append(rules.reason or "Makefile.hal não foi interpretado com segurança.")
        firmware = Verdict.INSUFFICIENT
    elif module.id not in rules.modes:
        reasons.append("O checkout selecionado não contém este modo.")
        firmware = Verdict.UNAVAILABLE
    else:
        firmware = _firmware_for_known(module, profile, rules, reasons)
        if (
            firmware == Verdict.COMPATIBLE
            and module.compatibility == Compatibility.INCOMPATIBLE
            and profile.model != Model.RDV4
        ):
            reasons.append("O catálogo desta instalação marca o modo como incompatível com PM3GENERIC.")
            firmware = Verdict.INCOMPATIBLE
    hardware = _hardware(module, profile, rules, reasons, spi_checkbox)
    if rules.complete and module.id in rules.modes:
        _catalog_conflict(module, rules, conflicts)
    return hardware, firmware, operational


def _is_pm5(profile: HardwareProfile) -> bool:
    return profile.family == Family.PM5 or profile.model == Model.PM5


def _firmware_for_known(
    module: Module,
    profile: HardwareProfile,
    rules: CheckoutRules,
    reasons: list[str],
) -> Verdict:
    rdv4_mode = module.id in rules.rdv4_only
    needs_bt = module.id in rules.bluetooth
    needs_card = module.id in rules.smartcard
    identified_rdv4 = profile.model == Model.RDV4
    if (rdv4_mode or needs_bt or needs_card) and not identified_rdv4:
        if profile.confidence == IdConfidence.NAO_IDENTIFICADO or profile.family == Family.DESCONHECIDA:
            reasons.append("O modo depende de RDV4, Bluetooth ou smartcard, e o hardware não foi identificado.")
            return Verdict.INSUFFICIENT
        reasons.append("Modo associado à plataforma RDV4. O dispositivo conectado não foi identificado como RDV4.")
        return Verdict.INCOMPATIBLE
    if identified_rdv4 or profile.family == Family.PM3:
        reasons.append("O checkout selecionado inclui este modo.")
        return Verdict.COMPATIBLE
    reasons.append("O checkout inclui o modo, mas a família do aparelho não foi confirmada.")
    return Verdict.INSUFFICIENT


def _hardware(
    module: Module,
    profile: HardwareProfile,
    rules: CheckoutRules,
    reasons: list[str],
    spi_checkbox: bool,
) -> Verdict:
    if profile.confidence == IdConfidence.NAO_IDENTIFICADO or not profile.reading_ok and profile.model not in {
        Model.RDV4,
        Model.PM5,
    }:
        if profile.family == Family.PM3 and not profile.reading_ok:
            reasons.append("A família PM3 veio do USB. Os recursos físicos deste modo ainda não foram lidos.")
            return Verdict.NEEDS_CONFIRMATION
        reasons.append("Não há leitura de hardware suficiente para decidir este modo.")
        return Verdict.INSUFFICIENT
    if profile.confidence == IdConfidence.INCONCLUSIVA or profile.model == Model.DESCONHECIDO and profile.family != Family.PM3:
        reasons.append("A identificação está inconclusiva. O modo não foi dado como compatível.")
        return Verdict.INSUFFICIENT
    if not rules.complete:
        if module.requires_flash and profile.spi == ResourceState.AUSENTE:
            reasons.append(
                "O Makefile não foi lido com segurança. A leitura mesmo assim informou flash externa ausente."
            )
            return Verdict.INCOMPATIBLE
        reasons.append("O Makefile não foi lido com segurança. O modo não foi classificado como compatível.")
        return Verdict.INSUFFICIENT
    if (
        module.compatibility == Compatibility.INCOMPATIBLE
        and profile.model != Model.RDV4
        and profile.family == Family.PM3
        and profile.reading_ok
    ):
        reasons.append("Módulo incompatível com PM3GENERIC nesta instalação.")
        return Verdict.INCOMPATIBLE
    requires_flash = module.id in rules.flash
    requires_bt = rules.complete and module.id in rules.bluetooth
    requires_card = rules.complete and module.id in rules.smartcard
    rdv4_mode = rules.complete and module.id in rules.rdv4_only
    identified_rdv4 = profile.model == Model.RDV4
    if (rdv4_mode or requires_bt or requires_card) and not identified_rdv4:
        reasons.append("Modo associado à plataforma RDV4. O dispositivo conectado não foi identificado como RDV4.")
        return Verdict.INCOMPATIBLE
    parts: list[Verdict] = []
    if requires_flash:
        parts.append(_spi(profile, reasons, spi_checkbox))
    if requires_bt:
        parts.append(_resource_needed(profile.bluetooth, "Bluetooth", reasons))
    if requires_card:
        parts.append(_resource_needed(profile.smartcard, "smartcard", reasons))
    if not parts:
        if profile.family == Family.PM3 or identified_rdv4:
            reasons.append("Nenhum requisito físico adicional deste modo foi contradito pela leitura.")
            return Verdict.COMPATIBLE
        reasons.append("Não há evidência suficiente sobre o hardware.")
        return Verdict.INSUFFICIENT
    return _strictest(parts)


def _spi(profile: HardwareProfile, reasons: list[str], spi_checkbox: bool) -> Verdict:
    if profile.spi == ResourceState.PRESENTE:
        reasons.append("Este modo requer flash SPI. O dispositivo conectado informou memória SPI presente.")
        if not spi_checkbox:
            reasons.append("A confirmação da flash SPI na interface continua obrigatória antes de compilar.")
        return Verdict.COMPATIBLE
    if profile.spi == ResourceState.AUSENTE:
        reasons.append("Este modo requer flash SPI. A leitura informou flash externa ausente.")
        return Verdict.INCOMPATIBLE
    reasons.append("Este modo requer flash SPI. A memória SPI ainda não foi confirmada.")
    return Verdict.NEEDS_CONFIRMATION


def _resource_needed(state: ResourceState, label: str, reasons: list[str]) -> Verdict:
    if state == ResourceState.PRESENTE:
        reasons.append(f"Este modo requer {label}. A leitura informou o recurso presente.")
        return Verdict.COMPATIBLE
    if state == ResourceState.AUSENTE:
        reasons.append(f"Este modo requer {label}. A leitura informou o recurso ausente.")
        return Verdict.INCOMPATIBLE
    reasons.append(f"Este modo requer {label}. O recurso ainda não foi confirmado.")
    return Verdict.NEEDS_CONFIRMATION


def _catalog_conflict(module: Module, rules: CheckoutRules, conflicts: list[str]) -> None:
    expects_flash = module.requires_flash
    parsed_flash = module.id in rules.flash
    if expects_flash != parsed_flash:
        conflicts.append(
            "O catálogo e a leitura estrita do Makefile.hal divergem sobre flash SPI. A leitura do Makefile prevalece."
        )
    expects_rdv4 = module.rdv4_only or module.requires_bt or module.requires_smartcard
    parsed_rdv4 = module.id in rules.rdv4_only or module.id in rules.bluetooth or module.id in rules.smartcard
    if expects_rdv4 != parsed_rdv4:
        conflicts.append(
            "O catálogo e a leitura estrita do Makefile.hal divergem sobre RDV4 ou acessório. A leitura do Makefile prevalece."
        )


def _guide(
    module: Module,
    rules: CheckoutRules,
    guide: GuideConstraint | None,
    reasons: list[str],
    conflicts: list[str],
) -> None:
    if guide is None:
        return
    if guide.inferred or guide.origin == "inferido":
        reasons.append("Um campo inferido do manual não foi usado como requisito físico.")
        return
    if guide.origin != "documentado":
        return
    parsed_rdv4 = rules.complete and (module.id in rules.rdv4_only or module.id in rules.bluetooth)
    parsed_flash = rules.complete and module.id in rules.flash
    if guide.documented_rdv4 is True and rules.complete and not parsed_rdv4:
        conflicts.append(
            "O manual documenta restrição RDV4, mas o Makefile.hal não a impõe. A restrição do sistema de compilação prevalece."
        )
    if guide.documented_rdv4 is False and parsed_rdv4:
        conflicts.append(
            "O manual não marca RDV4, mas o Makefile.hal marca. A restrição do Makefile prevalece."
        )
    if guide.documented_flash is True and rules.complete and not parsed_flash:
        conflicts.append(
            "O manual documenta flash SPI, mas o Makefile.hal não a exige. O Makefile prevalece."
        )
    if guide.documented_flash is False and parsed_flash:
        conflicts.append(
            "O manual não exige flash SPI, mas o Makefile.hal exige. O Makefile prevalece."
        )


def _strictest(parts: list[Verdict]) -> Verdict:
    order = (
        Verdict.INCOMPATIBLE,
        Verdict.UNAVAILABLE,
        Verdict.INSUFFICIENT,
        Verdict.NEEDS_CONFIRMATION,
        Verdict.COMPATIBLE,
    )
    for item in order:
        if item in parts:
            return item
    return Verdict.INSUFFICIENT


def _overall(hardware: Verdict, firmware: Verdict) -> Verdict:
    if hardware == Verdict.INCOMPATIBLE or firmware == Verdict.INCOMPATIBLE:
        return Verdict.INCOMPATIBLE
    if hardware == Verdict.UNAVAILABLE or firmware == Verdict.UNAVAILABLE:
        return Verdict.UNAVAILABLE
    if hardware == Verdict.INSUFFICIENT or firmware == Verdict.INSUFFICIENT:
        return Verdict.INSUFFICIENT
    if hardware == Verdict.NEEDS_CONFIRMATION or firmware == Verdict.NEEDS_CONFIRMATION:
        return Verdict.NEEDS_CONFIRMATION
    return Verdict.COMPATIBLE


def _summary(overall: Verdict, operational: OperationalSupport) -> str:
    if overall == Verdict.COMPATIBLE and operational in {
        OperationalSupport.CONSULTIVO,
        OperationalSupport.EXPERIMENTAL,
    }:
        return _FAVORABLE
    labels = {
        Verdict.COMPATIBLE: "Compatível segundo as verificações disponíveis.",
        Verdict.NEEDS_CONFIRMATION: "Requer confirmação. Ainda há requisito sem evidência.",
        Verdict.INCOMPATIBLE: "Incompatível com a plataforma ou com o hardware lido.",
        Verdict.INSUFFICIENT: "Informações insuficientes. A ausência de evidência não foi tratada como compatibilidade.",
        Verdict.UNAVAILABLE: "Indisponível neste firmware ou nesta plataforma.",
    }
    return labels[overall]


def device_notice(profile: HardwareProfile | None, assessment: ModuleAssessment | None = None) -> str:
    if profile is None:
        return "Dispositivo não identificado com segurança."
    if profile.stale:
        return "A avaliação anterior está desatualizada."
    if profile.active_deferred:
        return "Identificação ativa adiada enquanto a porta está em uso."
    if profile.confidence == IdConfidence.NAO_IDENTIFICADO:
        return "Dispositivo não identificado com segurança."
    if profile.confidence == IdConfidence.INCONCLUSIVA:
        return "A identificação está inconclusiva. Nenhum modelo foi escolhido automaticamente."
    if profile.conflicts:
        return profile.conflicts[0]
    if assessment is not None and assessment.overall == Verdict.UNAVAILABLE and _is_pm5(profile):
        return "Standalone indisponível no firmware PM5 analisado."
    if assessment is not None and assessment.reasons:
        for reason in assessment.reasons:
            if "flash SPI" in reason and "não foi confirmada" in reason:
                return "Módulo exige flash SPI ainda não confirmada."
            if "não foi identificado como RDV4" in reason:
                return "Módulo específico para RDV4."
            if "não contém este modo" in reason:
                return "O checkout não contém o módulo solicitado."
    if profile.version_mismatch:
        return "Firmware instalado e checkout local não possuem correspondência comprovada."
    return ""
