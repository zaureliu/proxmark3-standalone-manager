"""Interpreta ``hw version`` / ``hw status``. Não considera o módulo Standalone provado só por esses comandos."""

from __future__ import annotations

import re

from pm3manager.models import IdentityReport
from pm3manager.textutil import strip_ansi

_BANNER_PREFIX = re.compile(r"^\s*(?:\[#\]\s*)+")
_TARGET_LINE = re.compile(r"(?i)target\.{4,}\s*([^\r\n]+)")
_MCU = re.compile(r"uC:\s*([A-Za-z0-9]+)")
_MCU_SIZE = re.compile(r"Embedded flash memory\s+(\d+K bytes)", re.IGNORECASE)
_FLASH_SIZE = re.compile(r"Memory size\.+\s*(\d+)\s*Kb", re.IGNORECASE)
_SMARTCARD = re.compile(r"Smartcard reader\.+\s*([A-Za-z]+)", re.IGNORECASE)
_BT_ADDON = re.compile(r"FPC USART for BT add-on\.+\s*([A-Za-z]+)", re.IGNORECASE)


def _target_labels(text: str) -> list[str]:
    labels: list[str] = []
    for match in _TARGET_LINE.finditer(text or ""):
        label = re.sub(r"\s+", " ", match.group(1)).strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def _target_kind(label: str) -> str:
    """Uma linha Target do cliente. GENERIC exato não é PM3 GENERIC."""
    cleaned = label.strip().lower()
    if "mismatch" in cleaned:
        return "conflito"
    if cleaned == "pm5":
        return "PM5"
    if cleaned == "rdv4":
        return "RDV4"
    if cleaned in {"pm3 generic", "pm3generic"}:
        return "PM3 GENERIC"
    if cleaned == "generic":
        return "GENERIC"
    return ""


def model_signals(text: str) -> set[str]:
    """Sinais de modelo. Não promove preferência, VID nem LED_ORDER."""
    lowered = (text or "").lower()
    found: set[str] = set()
    for label in _target_labels(text or ""):
        kind = _target_kind(label)
        if kind:
            found.add(kind)
    if "firmware.................. rdv4" in lowered or "device.................... rdv4" in lowered:
        found.add("RDV4")
    if "pm3 generic" in lowered:
        found.add("PM3 GENERIC")
    if "pm3generic firmware on a rdv4" in lowered or "pm3_rdv4 firmware on a generic" in lowered:
        found.add("conflito")
    return found


def _firmware_kind(text: str) -> str:
    found = model_signals(text)
    concrete = {item for item in found if item != "conflito"}
    lowered = (text or "").lower()
    banner_pm5 = "proxmark5" in lowered
    banner_pm3 = "proxmark3" in lowered
    if "conflito" in found or len(concrete) > 1:
        return "conflito"
    if len(concrete) == 1:
        kind = next(iter(concrete))
        if banner_pm5 and kind != "PM5":
            return "conflito"
        return kind
    if banner_pm5 and banner_pm3:
        return "conflito"
    if banner_pm5:
        return "PM5"
    if banner_pm3:
        return "Proxmark3"
    return "desconhecido"


def parse_identity(output: str, *, exit_code: int, expected_version: str) -> IdentityReport:
    text = strip_ansi(output or "")
    lowered = text.lower()
    missing = exit_code != 0 or any(
        token in lowered
        for token in (
            "could not find proxmark",
            "waiting for proxmark3",
            "no port found",
            "status command timeout",
            "cannot communicate",
        )
    )
    has_banner = "[ proxmark3 ]" in lowered or "[ proxmark5 ]" in lowered or "client" in lowered
    if not text.strip() or (not has_banner and missing):
        return IdentityReport(
            communication_ok=False,
            version_mismatch=False,
            firmware_kind="desconhecido",
            external_flash="desconhecido",
            summary="Sem resposta utilizável do cliente.",
            raw=text,
        )
    mismatch = "does not match" in lowered or "não corresponde" in lowered
    kind = _firmware_kind(text)
    if kind == "desconhecido" and "proxmark3" in lowered and not missing:
        kind = "Proxmark3"
    if "external flash............ present" in lowered or "external flash............ presente" in lowered:
        flash = "presente"
    elif "external flash............ absent" in lowered or "external flash............ ausente" in lowered:
        flash = "ausente"
    else:
        flash = "não informado"
    version_seen = (not expected_version) or (expected_version in text)
    communication_ok = (not missing) and ("proxmark" in lowered)
    parts = []
    if communication_ok:
        parts.append("Cliente comunicou com o dispositivo.")
    else:
        parts.append("A comunicação não foi confirmada.")
    if version_seen and expected_version:
        parts.append(f"A versão {expected_version} aparece na resposta.")
    elif expected_version:
        parts.append("A versão esperada do repositório não apareceu na resposta.")
    if mismatch:
        parts.append("O cliente avisou que o firmware ARM não corresponde ao cliente.")
    parts.append(f"Firmware identificado: {kind}.")
    if flash != "não informado":
        parts.append(f"Flash externa: {flash}.")
    banner = _standalone_banner(text)
    mcu = _mcu_label(text)
    flash_size = _flash_size(text)
    smartcard = _presence(_SMARTCARD.search(text))
    bt_addon = _presence(_BT_ADDON.search(text))
    if mcu:
        parts.append(f"Microcontrolador: {mcu}.")
    if "512" in mcu:
        parts.append("A flash interna tem 512 KB. PLATFORM_SIZE=256 não se aplica e o modelo não é tratado como Easy.")
    if flash_size:
        parts.append(f"Tamanho da flash SPI: {flash_size}.")
    if smartcard:
        parts.append(f"Leitor de smartcard: {smartcard}.")
    if bt_addon:
        parts.append(f"Add-on Bluetooth: {bt_addon}.")
    if banner:
        parts.append(f"Modo Standalone informado pelo firmware: {banner}.")
        parts.append("Esse texto não confirma o módulo compilado nem substitui um teste com tag de laboratório.")
    else:
        parts.append("O hw version e o hw status não informaram o modo Standalone.")
    parts.append(
        "hw version e hw status desta versão do Iceman não identificam de forma inequívoca o módulo Standalone ativo."
    )
    return IdentityReport(
        communication_ok=communication_ok,
        version_mismatch=mismatch or not version_seen,
        firmware_kind=kind,
        external_flash=flash,
        summary=" ".join(parts),
        raw=text,
        standalone_banner=banner,
        mcu=mcu,
        external_flash_size=flash_size,
        smartcard=smartcard,
        bt_addon=bt_addon,
    )


def _standalone_banner(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "installed standalone mode" not in line.lower():
            continue
        for follow in lines[index + 1:index + 6]:
            cleaned = _BANNER_PREFIX.sub("", follow).strip()
            if cleaned and "installed standalone" not in cleaned.lower():
                return cleaned
    return ""


def _presence(match: re.Match[str] | None) -> str:
    if match is None:
        return ""
    word = match.group(1).lower()
    if word in {"present", "presente", "yes", "ok"}:
        return "presente"
    if word in {"absent", "ausente", "no", "fail", "failed"}:
        return "ausente"
    return word


def _flash_size(text: str) -> str:
    match = _FLASH_SIZE.search(text)
    if not match:
        return ""
    return f"{match.group(1)} Kb"


def _mcu_label(text: str) -> str:
    chip = _MCU.search(text)
    size = _MCU_SIZE.search(text)
    if chip and size:
        return f"{chip.group(1)} {size.group(1)}"
    if chip:
        return chip.group(1)
    return ""
