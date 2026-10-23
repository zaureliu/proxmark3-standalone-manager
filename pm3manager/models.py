"""Estruturas compartilhadas entre interface, compilação, cache e testes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Confidence(str, Enum):
    HIGH = "alta"
    MEDIUM = "media"


class Compatibility(str, Enum):
    COMPATIBLE = "compativel"
    REQUIRES_FLASH = "requer_flash"
    UNCERTAIN = "incerta"
    INCOMPATIBLE = "incompativel"


class Category(str, Enum):
    LF = "Low Frequency (LF)"
    HF = "High Frequency (HF)"
    MULTI = "Multimodo"
    OTHER = "Outros"


COMPATIBILITY_LABEL = {
    Compatibility.COMPATIBLE: "Compatível",
    Compatibility.REQUIRES_FLASH: "Requer flash SPI",
    Compatibility.UNCERTAIN: "Compatibilidade incerta",
    Compatibility.INCOMPATIBLE: "Incompatível",
}


@dataclass(frozen=True)
class PortView:
    device: str
    description: str = ""
    hwid: str = ""
    manufacturer: str = ""
    serial_number: str = ""
    vid: int | None = None
    pid: int | None = None


@dataclass(frozen=True)
class Device:
    port: str
    hardware_name: str
    confidence: Confidence
    vid: int | None
    pid: int | None
    serial_number: str
    description: str
    manufacturer: str
    hwid: str
    reason: str

    @property
    def label(self) -> str:
        return f"{self.hardware_name} — {self.port}"

    @property
    def identity_key(self) -> str:
        if self.serial_number:
            return f"serial:{self.serial_number}"
        vid = f"{self.vid:04X}" if self.vid is not None else "----"
        pid = f"{self.pid:04X}" if self.pid is not None else "----"
        return f"port:{vid}:{pid}:{self.port}"


@dataclass(frozen=True)
class Module:
    id: str
    name: str
    description: str
    frequency: str
    category: Category
    compatibility: Compatibility
    hardware_requirements: str
    limitations: tuple[str, ...]
    hal_description: str
    doc_hardware: str
    requires_flash: bool
    requires_bt: bool
    requires_smartcard: bool
    rdv4_only: bool
    source_file: str = ""


@dataclass
class BuildConfig:
    platform: str
    standalone: str
    extras: tuple[str, ...] = ()
    led_order: str = "PM3EASY"
    platform_size: str = ""

    def validate(self) -> None:
        from pm3manager.errors import SecurityError

        if self.platform != "PM3GENERIC":
            raise SecurityError("E303", "A plataforma de compilação precisa ser PM3GENERIC.")
        if not self.standalone or not self.standalone.replace("_", "").isalnum() or not self.standalone.isupper():
            raise SecurityError("E104", "Identificador de módulo Standalone inválido.")
        allowed_extras = {"FLASH"}
        if any(item not in allowed_extras for item in self.extras):
            raise SecurityError("E303", "Recurso extra não autorizado. Só FLASH pode ser habilitado.")
        if self.led_order != "PM3EASY":
            raise SecurityError("E303", "LED_ORDER precisa ser PM3EASY neste aplicativo.")
        if self.platform_size not in {"", "256"}:
            raise SecurityError("E003", "PLATFORM_SIZE não suportado.")

    def identity(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "standalone": self.standalone,
            "extras": list(self.extras),
            "led_order": self.led_order,
            "platform_size": self.platform_size,
        }


@dataclass
class Environment:
    proxspace_root: Path
    repo_root: Path
    repo_msys: str
    msys_shell: Path
    version: str
    commit: str
    build_time: str
    external_makefile: Path | None
    external_makefile_text: str
    source_fingerprint: str
    available_repos: tuple[str, ...] = ()


@dataclass
class ShellResult:
    exit_code: int
    output: str
    duration_s: float


@dataclass
class OperationResult:
    ok: bool
    code: str
    message: str
    outcome: str
    technical: str = ""
    stage: str = ""
    details: dict[str, str] = field(default_factory=dict)


@dataclass
class IdentityReport:
    communication_ok: bool
    version_mismatch: bool
    firmware_kind: str
    external_flash: str
    summary: str
    raw: str
    standalone_banner: str = ""
    mcu: str = ""
    external_flash_size: str = ""
    smartcard: str = ""
    bt_addon: str = ""
