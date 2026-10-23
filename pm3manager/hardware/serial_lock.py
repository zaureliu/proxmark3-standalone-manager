"""Vê se outro processo já abriu a porta, sem mantê-la ocupada."""

from __future__ import annotations

import serial


def port_is_free(port: str) -> tuple[bool, str]:
    try:
        handle = serial.Serial(port, baudrate=115200, timeout=0.2)
    except serial.SerialException as exc:
        text = str(exc).lower()
        if any(token in text for token in ("access", "denied", "permission", "em uso", "being used")):
            return False, f"A porta {port} está em uso por outro processo."
        return False, f"Não foi possível abrir {port}: {exc}"
    else:
        handle.close()
        return True, ""
