"""Identifica Proxmark3 pela enumeração serial do Windows.

VID/PID aceitos como confiança alta, os mesmos do driver e do script oficial,
mais o VID 502D:502D que o ``proxmark3.inf`` desta instalação chama de Easy.
O script ``pm3`` do Iceman não procura esse terceiro VID; a gravação precisa
então fixar a porta COM. Porta serial genérica não é tratada como Proxmark3.
"""

from __future__ import annotations

from pm3manager.models import Confidence, Device, PortView

# (vid, pid) -> (nome, motivo)
_KNOWN = {
    (0x9AC4, 0x4B8F): ("Proxmark3", "VID/PID Iceman 9AC4:4B8F, reconhecido pelo cliente oficial."),
    (0x2D2D, 0x504D): ("Proxmark3", "VID/PID legado proxmark.org 2D2D:504D."),
    (0x502D, 0x502D): (
        "Proxmark3",
        "VID/PID 502D:502D. O driver local chama esse perfil de Easy; isso não prova o modelo nem 256 KB.",
    ),
}
SCRIPT_VIDS = {(0x9AC4, 0x4B8F), (0x2D2D, 0x504D)}


def classify_port(port: PortView) -> Device | None:
    vidpid = (port.vid, port.pid)
    description = port.description or ""
    if vidpid in _KNOWN:
        name, reason = _KNOWN[vidpid]
        return Device(
            port=port.device,
            hardware_name=name,
            confidence=Confidence.HIGH,
            vid=port.vid,
            pid=port.pid,
            serial_number=port.serial_number or "",
            description=description,
            manufacturer=port.manufacturer or "",
            hwid=port.hwid or "",
            reason=reason,
        )
    blob = " ".join((description, port.manufacturer or "", port.hwid or "")).lower()
    if "proxmark" in blob:
        return Device(
            port=port.device,
            hardware_name="Proxmark3",
            confidence=Confidence.MEDIUM,
            vid=port.vid,
            pid=port.pid,
            serial_number=port.serial_number or "",
            description=description,
            manufacturer=port.manufacturer or "",
            hwid=port.hwid or "",
            reason="O texto menciona Proxmark, mas o VID/PID não é conhecido. A gravação fica bloqueada.",
        )
    return None


def classify_ports(ports: list[PortView]) -> list[Device]:
    devices = [device for device in (classify_port(port) for port in ports) if device is not None]
    devices.sort(key=lambda item: (item.confidence != Confidence.HIGH, item.port))
    return devices


def list_serial_ports() -> list[PortView]:
    from serial.tools import list_ports

    found: list[PortView] = []
    for port in list_ports.comports():
        found.append(
            PortView(
                device=port.device,
                description=port.description or "",
                hwid=port.hwid or "",
                manufacturer=port.manufacturer or "",
                serial_number=port.serial_number or "",
                vid=port.vid,
                pid=port.pid,
            )
        )
    return found


def detect_devices() -> list[Device]:
    return classify_ports(list_serial_ports())


def connection_change(previous: list[Device], current: list[Device]) -> str:
    if previous and not current:
        return "disconnected"
    if not previous and current:
        return "connected"
    previous_keys = {device.identity_key for device in previous}
    current_keys = {device.identity_key for device in current}
    if previous_keys != current_keys:
        return "changed"
    return "stable"


def match_after_reboot(previous: Device, devices: list[Device]) -> Device | None:
    highs = [device for device in devices if device.confidence == Confidence.HIGH]
    if previous.serial_number:
        for device in highs:
            if device.serial_number == previous.serial_number:
                return device
    if len(highs) == 1:
        return highs[0]
    same = [device for device in highs if (device.vid, device.pid) == (previous.vid, previous.pid)]
    if len(same) == 1:
        return same[0]
    return None
