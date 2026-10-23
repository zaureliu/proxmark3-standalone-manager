"""Prepara ``./pm3-flash-fullimage``. Bootrom e ``pm3-flash-all`` não são usados."""

from __future__ import annotations

from dataclasses import dataclass

from pm3manager.hardware.detector import SCRIPT_VIDS
from pm3manager.messages import Msg
from pm3manager.models import Confidence, Device
from pm3manager.textutil import normalize_com, strip_ansi


@dataclass(frozen=True)
class FlashPlan:
    allowed: bool
    code: str
    message: str
    port_arg: str | None
    device: Device | None


def plan_flash(devices: list[Device], selected: Device | None) -> FlashPlan:
    if selected is None:
        highs = [device for device in devices if device.confidence == Confidence.HIGH]
        if not highs:
            return FlashPlan(False, "E100", Msg.NOT_FOUND, None, None)
        if len(highs) > 1:
            return FlashPlan(False, "E102", "Há mais de um Proxmark3. Selecione o dispositivo.", None, None)
        selected = highs[0]
    if selected.confidence != Confidence.HIGH:
        return FlashPlan(False, "E103", Msg.MODEL_UNCONFIRMED, None, selected)
    visible = [
        device
        for device in devices
        if device.confidence == Confidence.HIGH and (device.vid, device.pid) in SCRIPT_VIDS
    ]
    # Sem -p o script oficial reencontra o aparelho se a COM mudar no bootloader.
    # O VID 502D:502D não entra nessa busca, então a porta precisa ser informada.
    if (selected.vid, selected.pid) in SCRIPT_VIDS and len(visible) == 1:
        return FlashPlan(True, "OK", Msg.PREPARE_FLASH, None, selected)
    try:
        port = normalize_com(selected.port)
    except ValueError:
        return FlashPlan(False, "E103", Msg.MODEL_UNCONFIRMED, None, selected)
    return FlashPlan(True, "OK", Msg.PREPARE_FLASH, port, selected)


def flash_script(repo_msys: str, port: str | None) -> str:
    from pm3manager.build.compiler import assert_repo_msys

    assert_repo_msys(repo_msys)
    argument = ""
    if port:
        argument = f" -p {normalize_com(port)}"
    return f"""#!/bin/bash
set -eu
cd {repo_msys}
if command -v stdbuf >/dev/null 2>&1; then
  stdbuf -oL -eL ./pm3-flash-fullimage{argument}
else
  ./pm3-flash-fullimage{argument}
fi
"""


def verify_script(repo_msys: str, port: str | None) -> str:
    from pm3manager.build.compiler import assert_repo_msys

    assert_repo_msys(repo_msys)
    argument = f" -p {normalize_com(port)}" if port else ""
    return f"""#!/bin/bash
set -eu
cd {repo_msys}
./pm3{argument} -c 'hw version'
./pm3{argument} -c 'hw status'
"""


def client_command(repo_msys: str, port: str | None) -> str:
    from pm3manager.build.compiler import assert_repo_msys

    assert_repo_msys(repo_msys)
    if port:
        return f"cd {repo_msys}; ./pm3 -p {normalize_com(port)}"
    return f"cd {repo_msys}; ./pm3"


def classify_flash_output(exit_code: int, output: str) -> str:
    text = strip_ansi(output or "")
    if exit_code == 0 and "All done" in text:
        return "command_ok"
    return "not_confirmed"
