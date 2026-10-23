"""Preferências locais.

A autorização de gravação existe só na memória, para a operação que o
usuário acabou de confirmar. Ela não é lida de volta do disco e o arquivo
nunca a regrava como habilitada.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pm3manager.paths import data_dir


def _stored_flash_enabled(value: object) -> bool:
    """Reconhece uma autorização antiga no JSON, só para apagá-la."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "sim"}
    return value is True or value == 1


@dataclass
class Preferences:
    last_module_id: str = ""
    flash_autorizado: bool = False
    spi_flash_confirmada: bool = False
    spi_flash_recusada: bool = False
    platform_size_256: bool = False
    confirmed_uncertain_modules: list[str] = field(default_factory=list)
    selected_serial: str = ""
    repo_dirname: str = ""
    proxspace_root: str = ""
    detected_firmware_kind: str = ""
    detected_mcu: str = ""
    detected_external_flash: str = ""
    detected_flash_size: str = ""
    detected_standalone: str = ""
    detected_smartcard: str = ""
    detected_bt_addon: str = ""

    @staticmethod
    def path() -> Path:
        return data_dir() / "preferences.json"

    @classmethod
    def load(cls) -> "Preferences":
        path = cls.path()
        if not path.is_file():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {item.name for item in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        data = {key: value for key, value in raw.items() if key in known}
        prefs = cls(**data)
        prefs._preserved = {key: value for key, value in raw.items() if key not in known}
        prefs.confirmed_uncertain_modules = [str(item) for item in prefs.confirmed_uncertain_modules]
        stored_flash = _stored_flash_enabled(raw.get("flash_autorizado", False))
        prefs.flash_autorizado = False
        prefs.spi_flash_confirmada = bool(prefs.spi_flash_confirmada)
        prefs.spi_flash_recusada = bool(prefs.spi_flash_recusada)
        prefs.platform_size_256 = bool(prefs.platform_size_256)
        for name in (
            "detected_mcu",
            "detected_external_flash",
            "detected_flash_size",
            "detected_standalone",
            "detected_smartcard",
            "detected_bt_addon",
            "repo_dirname",
            "proxspace_root",
            "detected_firmware_kind",
            "selected_serial",
            "last_module_id",
        ):
            setattr(prefs, name, str(getattr(prefs, name) or ""))
        if stored_flash:
            prefs.save()
        return prefs

    def save(self) -> None:
        """Grava as preferências. A autorização de gravação sai sempre desligada."""
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        preserved = getattr(self, "_preserved", {})
        if isinstance(preserved, dict):
            for key, value in preserved.items():
                if key not in payload:
                    payload[key] = value
        payload["flash_autorizado"] = False
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
