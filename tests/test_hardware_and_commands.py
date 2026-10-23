from pm3manager.build.compiler import build_script, validate_fullimage
from pm3manager.errors import BuildError, SecurityError
from pm3manager.flash.flasher import classify_flash_output, flash_script, plan_flash, verify_script
from pm3manager.hardware.detector import classify_ports, connection_change, match_after_reboot
from pm3manager.hardware.identity import parse_identity
from pm3manager.models import Confidence, PortView
from pm3manager.proxspace.shell import ProxSpaceShell
from pm3manager.textutil import strip_ansi
from tests.fakes import VERSION, device


def _port(device_name, vid=None, pid=None, description="", manufacturer="", serial=""):
    return PortView(device_name, description, "", manufacturer, serial, vid, pid)


def test_detecta_pm3_e_ignora_serial_generica():
    ports = [
        _port("COM4", 0x0403, 0x6001, "USB Serial Device", "FTDI"),
        _port("COM5", 0x9AC4, 0x4B8F, "Proxmark3", "proxmark.org", "SER1"),
        _port("COM6", description="Arduino Uno", manufacturer="Arduino"),
    ]
    found = classify_ports(ports)
    assert [item.port for item in found] == ["COM5"]
    assert found[0].confidence == Confidence.HIGH
    assert found[0].label == "Proxmark3 — COM5"


def test_varios_proxmark_e_easy_502d():
    ports = [
        _port("COM7", 0x9AC4, 0x4B8F, serial="A"),
        _port("COM8", 0x502D, 0x502D, description="Proxmark3 Easy", serial="B"),
        _port("COM9", description="Proxmark3 bootloader", manufacturer="desconhecido"),
    ]
    found = classify_ports(ports)
    assert len(found) == 3
    assert found[2].confidence == Confidence.MEDIUM
    easy = next(item for item in found if item.port == "COM8")
    assert easy.hardware_name == "Proxmark3"
    assert "502D" in easy.reason
    assert "não prova" in easy.reason
    assert plan_flash(found, None).code == "E102"
    plan = plan_flash(found, easy)
    assert plan.allowed and plan.port_arg == "COM8"


def test_autodetect_quando_so_ha_um_vid_oficial():
    only = [device()]
    plan = plan_flash(only, only[0])
    assert plan.allowed
    assert plan.port_arg is None
    script = flash_script("/pm3/proxmark3-v4.23346", plan.port_arg)
    assert "./pm3-flash-fullimage" in script
    assert "-p " not in script
    assert "pm3-flash-all" not in script
    assert "bootrom" not in script


def test_conexao_e_redescoberta():
    first = [device(port="COM5", serial="ABC")]
    assert connection_change([], first) == "connected"
    assert connection_change(first, []) == "disconnected"
    moved = [device(port="COM12", serial="ABC")]
    assert connection_change(first, moved) == "stable"
    assert match_after_reboot(first[0], moved).port == "COM12"
    other = [device(port="COM3", serial="X"), device(port="COM4", serial="Y")]
    assert match_after_reboot(device(serial=""), other) is None


def test_comandos_de_build_e_verificacao():
    script = build_script("/pm3/proxmark3-v4.23346")
    assert script.find("cd /pm3/proxmark3-v4.23346") < script.find("make clean")
    assert "make -j" in script
    verify = verify_script("/pm3/proxmark3-v4.23346", "COM10")
    assert "-p COM10" in verify
    assert "hw version" in verify
    assert "hw status" in verify


def test_shell_recusa_comando_destrutivo():
    try:
        ProxSpaceShell._guard("#!/bin/bash\n./pm3-flash-all\n")
    except SecurityError as exc:
        assert exc.code == "E304"
    else:
        raise AssertionError("comando destrutivo foi aceito")


def test_classifica_gravação_e_identidade():
    colored = strip_ansi("\x1b[32mAll done\x1b[0m")
    assert classify_flash_output(0, colored) == "command_ok"
    assert classify_flash_output(1, "Could not find Proxmark3\n") == "not_confirmed"
    text = f"[ Proxmark3 ]\nFirmware.................. PM3 GENERIC\n{VERSION}\nExternal flash............ absent\n"
    report = parse_identity(text, exit_code=0, expected_version=VERSION)
    assert report.communication_ok
    assert not report.version_mismatch
    assert report.firmware_kind == "PM3 GENERIC"
    mismatch = parse_identity(
        text + "\nARM firmware does not match the source\n",
        exit_code=0,
        expected_version=VERSION,
    )
    assert mismatch.version_mismatch
    rdv4 = parse_identity("Firmware.................. RDV4\nProxmark3\n", exit_code=0, expected_version=VERSION)
    assert rdv4.firmware_kind == "RDV4"
    missing = parse_identity("", exit_code=1, expected_version=VERSION)
    assert not missing.communication_ok
    live = parse_identity(
        "[ Proxmark3 ]\n"
        " External flash............ present\n"
        " --= uC: AT91SAM7S512 Rev A\n"
        " --= Embedded flash memory 512K bytes ( 94% used )\n"
        "[#] Installed StandAlone Mode\n"
        "[#]   LF HID26 standalone - aka SamyRun (Samy Kamkar)\n"
        "[#]   Memory size............. 2048 Kb ( 32 pages * 64k )\n"
        " Smartcard reader.......... absent\n"
        " FPC USART for BT add-on... absent\n"
        + VERSION,
        exit_code=0,
        expected_version=VERSION,
    )
    assert live.external_flash == "presente"
    assert live.external_flash_size == "2048 Kb"
    assert live.smartcard == "ausente"
    assert live.bt_addon == "ausente"
    assert live.mcu == "AT91SAM7S512 512K bytes"
    assert "512 KB" in live.summary
    assert "Easy" in live.summary
    assert live.standalone_banner == "LF HID26 standalone - aka SamyRun (Samy Kamkar)"


def test_elf_ausente(tmp_path):
    try:
        validate_fullimage(tmp_path / "nao-existe.elf", VERSION)
    except BuildError as exc:
        assert exc.code == "E201"
    else:
        raise AssertionError("elf ausente foi aceito")
