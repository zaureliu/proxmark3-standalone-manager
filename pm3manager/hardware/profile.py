"""Perfil de hardware. Não compila, não grava e não altera o Makefile."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from pm3manager.hardware.identity import model_signals, parse_identity
from pm3manager.messages import Msg
from pm3manager.models import Confidence, Device, IdentityReport

_PLATFORM = re.compile(r"^(PLATFORM|LED_ORDER)\s*[:?]?=\s*(\S+)\s*$")


class IdConfidence(str, Enum):
    CONFIRMADA = "confirmada"
    PROVAVEL = "provavel"
    FAMILIA_CONHECIDA = "familia_conhecida"
    INCONCLUSIVA = "inconclusiva"
    NAO_IDENTIFICADO = "nao_identificado"


class Family(str, Enum):
    PM3 = "PM3"
    PM5 = "PM5"
    DESCONHECIDA = "desconhecida"


class Model(str, Enum):
    NAO_CONFIRMADO = "nao_confirmado"
    RDV4 = "RDV4"
    PM5 = "PM5"
    DESCONHECIDO = "desconhecido"


class ResourceState(str, Enum):
    PRESENTE = "presente"
    AUSENTE = "ausente"
    DESCONHECIDO = "desconhecido"


class OperationalSupport(str, Enum):
    VALIDADO = "validado"
    CONSULTIVO = "consultivo"
    EXPERIMENTAL = "experimental"
    INDISPONIVEL = "indisponivel"
    NAO_AVALIADO = "nao_avaliado"


@dataclass
class HardwareProfile:
    family: Family
    model: Model
    confidence: IdConfidence
    operational: OperationalSupport
    configured_platform: str = ""
    led_order: str = ""
    reported_firmware: str = ""
    mcu: str = ""
    spi: ResourceState = ResourceState.DESCONHECIDO
    smartcard: ResourceState = ResourceState.DESCONHECIDO
    bluetooth: ResourceState = ResourceState.DESCONHECIDO
    evidence: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    context_key: str = ""
    identity_key: str = ""
    source: str = "nenhum"
    version_mismatch: bool = False
    block_pipeline: bool = False
    block_reason: str = ""
    stale: bool = False
    active_deferred: bool = False
    reading_ok: bool = False
    device_count: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def compact_label(self) -> str:
        if self.confidence == IdConfidence.NAO_IDENTIFICADO:
            return "Dispositivo: não identificado"
        if self.model == Model.RDV4 and self.confidence == IdConfidence.CONFIRMADA:
            return "Dispositivo: Proxmark3 RDV4 | Identificação confirmada"
        if self.model == Model.RDV4 and self.confidence == IdConfidence.PROVAVEL:
            return "Dispositivo: Proxmark3 RDV4 | Identificação provável"
        if self.model == Model.PM5 and self.confidence == IdConfidence.CONFIRMADA:
            return "Dispositivo: Proxmark5 | Identificação confirmada"
        if self.model == Model.PM5 and self.confidence == IdConfidence.PROVAVEL:
            return "Dispositivo: Proxmark5 | Identificação provável"
        if self.confidence == IdConfidence.INCONCLUSIVA:
            return "Dispositivo: Proxmark | Família: inconclusiva | Modelo: não confirmado"
        if self.family == Family.PM3:
            return "Dispositivo: Proxmark3 | Família: PM3 | Modelo: não confirmado"
        if self.family == Family.PM5:
            return "Dispositivo: Proxmark5 | Família: PM5 | Modelo: não confirmado"
        return "Dispositivo: não identificado"


@dataclass(frozen=True)
class IdentifyInput:
    device: Device | None
    device_count: int = 0
    client_text: str = ""
    client_exit: int = 0
    expected_version: str = ""
    configured_platform: str = ""
    led_order: str = ""
    prefs_kind: str = ""
    source: str = ""


def context_key(device: Device | None) -> str:
    if device is None:
        return ""
    vid = f"{device.vid:04X}" if device.vid is not None else ""
    pid = f"{device.pid:04X}" if device.pid is not None else ""
    return "|".join((device.port, vid, pid))


def read_make_assignments(text: str) -> tuple[str, str, tuple[str, ...]]:
    """Lê PLATFORM e LED_ORDER. Não executa make e não escolhe um modelo."""
    found: dict[str, list[str]] = {"PLATFORM": [], "LED_ORDER": []}
    notes: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _PLATFORM.match(line)
        if match is None:
            continue
        found[match.group(1)].append(match.group(2))
    platform = _single(found["PLATFORM"], "PLATFORM", notes)
    led = _single(found["LED_ORDER"], "LED_ORDER", notes)
    return platform, led, tuple(notes)


def _single(values: list[str], name: str, notes: list[str]) -> str:
    unique = list(dict.fromkeys(values))
    if len(unique) > 1:
        notes.append(f"O Makefile tem mais de um valor para {name}. Nenhum foi escolhido como fato.")
        return ""
    return unique[0] if unique else ""


def blocks_pipeline(profile: HardwareProfile | None) -> str:
    if profile is None or profile.stale or not profile.block_pipeline:
        return ""
    return profile.block_reason


def operation_block(profile: HardwareProfile | None, stored_kind: str = "") -> str:
    """Bloqueio de compilação e gravação. Leitura nova de PM3 genérico prevalece sobre preferência antiga."""
    if profile is not None and not profile.stale:
        denied = blocks_pipeline(profile)
        if denied:
            return denied
        fresh_generic = (
            profile.source in {"cliente", "diagnostico"}
            and profile.family == Family.PM3
            and profile.model == Model.NAO_CONFIRMADO
            and not profile.block_pipeline
        )
        if fresh_generic:
            return ""
    if stored_kind == "RDV4":
        return Msg.FLASH_RDV4_BLOCKED
    if stored_kind == "PM5":
        return Msg.FLASH_PM5_BLOCKED
    if stored_kind in {"GENERIC", "conflito"}:
        return Msg.FLASH_IDENTITY_BLOCKED
    return ""


def authorization_invalidated(previous_key: str, current_key: str) -> bool:
    return bool(previous_key) and previous_key != current_key


def identify(observation: IdentifyInput) -> HardwareProfile:
    device = observation.device
    evidence: list[str] = []
    conflicts: list[str] = []
    warnings: list[str] = []
    key = device.identity_key if device is not None else ""
    stamp = context_key(device)
    if observation.device_count > 1:
        evidence.append("Há mais de um dispositivo. A avaliação usa somente o selecionado.")
    if device is None:
        return _finish(
            family=Family.DESCONHECIDA,
            model=Model.DESCONHECIDO,
            confidence=IdConfidence.NAO_IDENTIFICADO,
            operational=OperationalSupport.NAO_AVALIADO,
            evidence=("Nenhum Proxmark foi selecionado.",),
            identity_key="",
            context_key="",
            source="nenhum",
            device_count=observation.device_count,
        )
    family, model, confidence = _from_usb(device, evidence)
    if "easy" in (device.hardware_name or "").lower() or "easy" in (device.description or "").lower():
        evidence.append("O rótulo USB menciona Easy. Isso não confirma o modelo nem 256 KB.")
    if "rdv4" in (device.description or "").lower() or "rdv4" in (device.hardware_name or "").lower():
        evidence.append("O nome USB menciona RDV4. Isso, sozinho, não confirma o modelo.")
    report = _report(observation)
    source = observation.source or ("cliente" if observation.client_text.strip() else "usb")
    reported = ""
    version_mismatch = False
    mcu = ""
    spi = ResourceState.DESCONHECIDO
    smartcard = ResourceState.DESCONHECIDO
    bluetooth = ResourceState.DESCONHECIDO
    reading_ok = False
    if report is not None and observation.client_text.strip():
        reported = report.firmware_kind
        version_mismatch = report.version_mismatch
        mcu = report.mcu
        spi = _resource(report.external_flash)
        smartcard = _resource(report.smartcard)
        bluetooth = _resource(report.bt_addon)
        reading_ok = bool(report.communication_ok and reported not in {"", "desconhecido"})
        family, model, confidence = _from_client(
            report,
            observation.client_text,
            family,
            model,
            confidence,
            evidence,
            conflicts,
        )
        if version_mismatch:
            warnings.append(
                "A versão do firmware não tem correspondência comprovada com o checkout. "
                "Essa diferença não é usada como evidência de modelo."
            )
        if not report.communication_ok:
            evidence.append("O cliente não confirmou a comunicação. A resposta não eleva o modelo.")
            if confidence == IdConfidence.CONFIRMADA:
                confidence = IdConfidence.PROVAVEL
    elif not observation.client_text.strip():
        evidence.append("Ainda não há leitura do cliente para este dispositivo.")
    _preference_note(observation.prefs_kind, reported, evidence)
    _configured_note(observation.configured_platform, observation.led_order, model, family, evidence, conflicts)
    operational, block, reason = _support(family, model, confidence, conflicts)
    return _finish(
        family=family,
        model=model,
        confidence=confidence,
        operational=operational,
        configured_platform=observation.configured_platform,
        led_order=observation.led_order,
        reported_firmware=reported,
        mcu=mcu,
        spi=spi,
        smartcard=smartcard,
        bluetooth=bluetooth,
        evidence=tuple(evidence),
        conflicts=tuple(conflicts),
        warnings=tuple(warnings),
        context_key=stamp,
        identity_key=key,
        source=source,
        version_mismatch=version_mismatch,
        block_pipeline=block,
        block_reason=reason,
        reading_ok=reading_ok,
        device_count=observation.device_count,
    )


def _finish(**kwargs: object) -> HardwareProfile:
    profile = HardwareProfile(**kwargs)  # type: ignore[arg-type]
    _reject_secrets(profile)
    return profile


def _reject_secrets(profile: HardwareProfile) -> None:
    blob = " ".join(profile.evidence + profile.conflicts + profile.warnings + (profile.compact_label(), profile.block_reason))
    lowered = blob.lower()
    if "unique id" in lowered or "serial:" in lowered:
        raise RuntimeError("o perfil expôs um identificador único")


def _report(observation: IdentifyInput) -> IdentityReport | None:
    if not observation.client_text.strip():
        return None
    return parse_identity(
        observation.client_text,
        exit_code=observation.client_exit,
        expected_version=observation.expected_version,
    )


def _from_usb(device: Device, evidence: list[str]) -> tuple[Family, Model, IdConfidence]:
    if device.confidence == Confidence.HIGH:
        evidence.append(
            "O VID/PID conhecido indica a família Proxmark3. Ele não identifica RDV4, PM5 nem Easy."
        )
        return Family.PM3, Model.NAO_CONFIRMADO, IdConfidence.FAMILIA_CONHECIDA
    blob = " ".join((device.description or "", device.manufacturer or "", device.hardware_name or "")).lower()
    if "proxmark" in blob or device.confidence == Confidence.MEDIUM:
        evidence.append("O texto USB menciona Proxmark, mas o VID/PID não confirma a família.")
        return Family.DESCONHECIDA, Model.DESCONHECIDO, IdConfidence.INCONCLUSIVA
    evidence.append("A porta não trouxe evidência de Proxmark.")
    return Family.DESCONHECIDA, Model.DESCONHECIDO, IdConfidence.NAO_IDENTIFICADO


def _from_client(
    report: IdentityReport,
    text: str,
    family: Family,
    model: Model,
    confidence: IdConfidence,
    evidence: list[str],
    conflicts: list[str],
) -> tuple[Family, Model, IdConfidence]:
    signals = model_signals(text)
    kind = report.firmware_kind
    if kind == "conflito" or "conflito" in signals or _contradicts(signals):
        conflicts.append("As respostas do cliente se contradizem. Nenhum modelo específico foi escolhido.")
        evidence.append("Identificação inconclusiva por evidência conflitante.")
        return Family.DESCONHECIDA, Model.DESCONHECIDO, IdConfidence.INCONCLUSIVA
    if kind == "GENERIC":
        conflicts.append(
            "O cliente informou Target GENERIC. No Iceman isso é a assinatura genérica do firmware RDV4, não PM3 GENERIC."
        )
        evidence.append("A assinatura GENERIC não foi tratada como PM3GENERIC.")
        return Family.DESCONHECIDA, Model.DESCONHECIDO, IdConfidence.INCONCLUSIVA
    if kind == "PM5" or "PM5" in signals:
        return _pm5(text, report, evidence)
    if kind == "RDV4" or "RDV4" in signals:
        return _rdv4(text, evidence)
    if kind == "PM3 GENERIC" or "PM3 GENERIC" in signals:
        evidence.append(
            "O cliente informou PM3 GENERIC. Isso indica a família PM3, não um modelo comercial e não uma placa Easy."
        )
        if "at91sam7s" in (report.mcu or "").lower():
            evidence.append("O microcontrolador informado é AT91SAM7S. O modelo comercial continua não confirmado.")
        return Family.PM3, Model.NAO_CONFIRMADO, IdConfidence.FAMILIA_CONHECIDA
    if kind == "Proxmark3":
        evidence.append("O banner Proxmark3 não informa o modelo.")
        if confidence == IdConfidence.FAMILIA_CONHECIDA:
            return Family.PM3, Model.NAO_CONFIRMADO, IdConfidence.FAMILIA_CONHECIDA
        return family, Model.NAO_CONFIRMADO, IdConfidence.INCONCLUSIVA
    evidence.append("A resposta do cliente não identificou família nem modelo.")
    return family, model, confidence if confidence != IdConfidence.NAO_IDENTIFICADO else IdConfidence.INCONCLUSIVA


def _contradicts(signals: set[str]) -> bool:
    concrete = {item for item in signals if item != "conflito"}
    return len(concrete) > 1


def _pm5(text: str, report: IdentityReport, evidence: list[str]) -> tuple[Family, Model, IdConfidence]:
    lowered = text.lower()
    count = 0
    if any(label.strip().lower() == "pm5" for label in _labels(text)):
        count += 1
        evidence.append("O cliente informou Target PM5.")
    if "at32f437" in (report.mcu or "").lower() or "at32f437" in lowered:
        count += 1
        evidence.append("O microcontrolador informado é AT32F437.")
    if "proxmark5" in lowered:
        count += 1
        evidence.append("O banner indica Proxmark5.")
    if count >= 2:
        evidence.append("PM5 identificado por mais de um sinal. Os modos Standalone de PM3 não são assumidos.")
        return Family.PM5, Model.PM5, IdConfidence.CONFIRMADA
    if count == 1:
        evidence.append("Há um sinal de PM5. A identificação fica provável, não confirmada.")
        return Family.PM5, Model.PM5, IdConfidence.PROVAVEL
    evidence.append("A família PM5 apareceu sem sinal suficiente de modelo.")
    return Family.PM5, Model.DESCONHECIDO, IdConfidence.FAMILIA_CONHECIDA


def _labels(text: str) -> list[str]:
    from pm3manager.hardware.identity import _target_labels

    return _target_labels(text)


def _rdv4(text: str, evidence: list[str]) -> tuple[Family, Model, IdConfidence]:
    lowered = text.lower()
    target = any(label.strip().lower() == "rdv4" for label in _labels(text))
    firmware_line = "firmware.................. rdv4" in lowered or "device.................... rdv4" in lowered
    if target and firmware_line:
        evidence.append("Target RDV4 e a linha de firmware concordam. A identificação do RDV4 fica confirmada.")
        return Family.PM3, Model.RDV4, IdConfidence.CONFIRMADA
    if target:
        evidence.append("O cliente informou Target RDV4. Sem outra evidência concordante, a identificação fica provável.")
        return Family.PM3, Model.RDV4, IdConfidence.PROVAVEL
    if firmware_line:
        evidence.append("A linha de firmware informa RDV4. Sem Target concordante, a identificação fica provável.")
        return Family.PM3, Model.RDV4, IdConfidence.PROVAVEL
    evidence.append("RDV4 foi mencionado sem evidência suficiente para escolher o modelo.")
    return Family.PM3, Model.DESCONHECIDO, IdConfidence.FAMILIA_CONHECIDA


def _preference_note(prefs_kind: str, reported: str, evidence: list[str]) -> None:
    if not prefs_kind:
        return
    evidence.append("Uma preferência antiga não eleva esta identificação a confirmada.")
    if reported and prefs_kind != reported:
        evidence.append("A preferência antiga discorda da leitura atual e foi ignorada como prova.")


def _configured_note(
    platform: str,
    led_order: str,
    model: Model,
    family: Family,
    evidence: list[str],
    conflicts: list[str],
) -> None:
    if led_order:
        evidence.append(
            f"LED_ORDER={led_order} é configuração de compilação. Não identifica a placa como Easy nem como outro modelo."
        )
    if not platform:
        return
    evidence.append(f"A plataforma configurada é {platform}. Ela não substitui a leitura do hardware.")
    configured_rdv4 = platform.upper() in {"PM3RDV4", "RDV4"}
    configured_generic = platform.upper() == "PM3GENERIC"
    if model == Model.RDV4 and configured_generic:
        conflicts.append("A plataforma configurada é PM3GENERIC e o hardware foi identificado como RDV4.")
    elif model == Model.PM5 and platform.upper() != "PM5":
        conflicts.append("A plataforma configurada não é PM5, mas o hardware foi identificado como Proxmark5.")
    elif configured_rdv4 and model != Model.RDV4:
        conflicts.append(
            "O Makefile cita plataforma RDV4. Isso não identifica o aparelho conectado como RDV4."
        )
    elif configured_generic and family == Family.PM3 and model == Model.NAO_CONFIRMADO:
        evidence.append("PLATFORM=PM3GENERIC não promove o aparelho a um modelo comercial.")


def _support(
    family: Family,
    model: Model,
    confidence: IdConfidence,
    conflicts: list[str],
) -> tuple[OperationalSupport, bool, str]:
    if model == Model.RDV4:
        return OperationalSupport.CONSULTIVO, True, Msg.RDV4_PIPELINE_BLOCKED
    if model == Model.PM5 or family == Family.PM5:
        return OperationalSupport.EXPERIMENTAL, True, Msg.FLASH_PM5_BLOCKED
    if confidence == IdConfidence.INCONCLUSIVA and conflicts:
        return OperationalSupport.INDISPONIVEL, True, Msg.FLASH_IDENTITY_BLOCKED
    if family == Family.PM3 and model == Model.NAO_CONFIRMADO:
        return OperationalSupport.VALIDADO, False, ""
    if confidence == IdConfidence.NAO_IDENTIFICADO:
        return OperationalSupport.NAO_AVALIADO, False, ""
    return OperationalSupport.NAO_AVALIADO, False, ""


def _resource(value: str) -> ResourceState:
    if value in {"presente", "present"}:
        return ResourceState.PRESENTE
    if value in {"ausente", "absent"}:
        return ResourceState.AUSENTE
    return ResourceState.DESCONHECIDO
