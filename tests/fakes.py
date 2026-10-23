from __future__ import annotations

from pathlib import Path

from pm3manager.models import Confidence, Device, Environment, Module, ShellResult
from pm3manager.models import Category, Compatibility

VERSION = "Iceman/master/v4.23346"


def device(port="COM5", vid=0x9AC4, pid=0x4B8F, serial="ABC", confidence=Confidence.HIGH) -> Device:
    name = "Proxmark3 Easy" if (vid, pid) == (0x502D, 0x502D) else "Proxmark3"
    return Device(
        port=port,
        hardware_name=name,
        confidence=confidence,
        vid=vid,
        pid=pid,
        serial_number=serial,
        description=name,
        manufacturer="proxmark.org",
        hwid=f"USB VID:PID={vid:04X}:{pid:04X}",
        reason="teste",
    )


def module(module_id="LF_SAMYRUN", compatibility=Compatibility.COMPATIBLE) -> Module:
    return Module(
        id=module_id,
        name=module_id,
        description="descricao",
        frequency="LF",
        category=Category.LF,
        compatibility=compatibility,
        hardware_requirements="Generic",
        limitations=(),
        hal_description="",
        doc_hardware="",
        requires_flash=compatibility == Compatibility.REQUIRES_FLASH,
        requires_bt=False,
        requires_smartcard=False,
        rdv4_only=compatibility == Compatibility.INCOMPATIBLE,
    )


def make_env(root: Path) -> Environment:
    proxspace = root / "ProxSpace"
    repo = proxspace / "pm3" / "proxmark3-test"
    (repo / "armsrc" / "Standalone").mkdir(parents=True, exist_ok=True)
    (repo / "common").mkdir(exist_ok=True)
    (repo / "client").mkdir(exist_ok=True)
    (repo / "Makefile").write_text("all:\n", encoding="utf-8")
    (repo / "armsrc" / "Standalone" / "Makefile.hal").write_text("hal\n", encoding="utf-8")
    (repo / "pm3").write_text("#!/bin/bash\n", encoding="utf-8")
    (repo / "pm3-flash-fullimage").write_text("#!/bin/bash\n", encoding="utf-8")
    (proxspace / "msys2").mkdir(parents=True, exist_ok=True)
    (proxspace / "runme64.bat").write_text("@echo off\n", encoding="utf-8")
    (proxspace / "msys2" / "msys2_shell.cmd").write_text("@echo off\n", encoding="utf-8")
    return Environment(
        proxspace_root=proxspace,
        repo_root=repo,
        repo_msys="/pm3/proxmark3-test",
        msys_shell=proxspace / "msys2" / "msys2_shell.cmd",
        version=VERSION,
        commit="9ce8a4b6c",
        build_time="2026-09-18 00:22:18",
        external_makefile=None,
        external_makefile_text="",
        source_fingerprint="fingerprint-teste",
    )


class FakeShell:
    def __init__(self, repo: Path, version: str = VERSION) -> None:
        self.repo = repo
        self.version = version
        self.scripts: list[str] = []
        self.fail_build = False
        self.omit_elf = False
        self.fail_flash = False
        self.flash_exit = None
        self.flash_output = None
        self.banner_platform = ""
        self.hw_output = f"[ Proxmark3 ]\nFirmware.................. PM3 GENERIC\n{version}\n"
        self.hw_exit = 0

    def run_script(self, script: str, *, timeout: float, on_line=None) -> ShellResult:
        self.scripts.append(script)
        if on_line:
            on_line(script[:120] + "\n")
        if "arm-none-eabi-gcc" in script:
            return ShellResult(0, "arm-none-eabi-gcc.exe (GCC) 12.2.0\n", 0.01)
        if "make -j" in script:
            if self.fail_build:
                return ShellResult(2, "error: falha simulada\n", 0.01)
            if not self.omit_elf:
                elf = self.repo / "armsrc" / "obj" / "fullimage.elf"
                elf.parent.mkdir(parents=True, exist_ok=True)
                elf.write_bytes(b"\x7fELF" + b"\x00" * 20000 + self.version.encode("utf-8"))
                client = self.repo / "client" / "proxmark3.exe"
                client.parent.mkdir(parents=True, exist_ok=True)
                client.write_bytes(b"MZ" + b"\x00" * 200_000)
            return ShellResult(0, self._banner() + "compilacao simulada\n", 0.01)
        if "pm3-flash-fullimage" in script:
            if self.fail_flash:
                return ShellResult(1, "Could not find Proxmark3\n", 0.01)
            if self.flash_exit is not None:
                return ShellResult(self.flash_exit, self.flash_output or "", 0.01)
            return ShellResult(0, "All done\n", 0.01)
        if "hw version" in script:
            return ShellResult(self.hw_exit, self.hw_output, 0.01)
        return ShellResult(0, "ok\n", 0.01)

    def _banner(self) -> str:
        text = ""
        path = self.repo / "Makefile.platform"
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
        values: dict[str, str] = {}
        for line in text.splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        platform = self.banner_platform or values.get("PLATFORM", "PM3RDV4")
        standalone = values.get("STANDALONE", "LF_SAMYRUN")
        extras = values.get("PLATFORM_EXTRAS", "")
        size = values.get("PLATFORM_SIZE", "") or "512"
        led = values.get("LED_ORDER", "")
        if platform == "PM3GENERIC" and led == "PM3EASY":
            name = "Proxmark3 generic target"
            options = "-DLED_ORDER_PM3EASY -DCHIP_AT91SAM7S"
            if extras:
                options += " " + extras
        elif platform == "PM3RDV4":
            name = "Proxmark3 RDV4"
            options = "-DWITH_SMARTCARD -DWITH_FLASH -DRDV4 -DCHIP_AT91SAM7S"
        else:
            name = platform
            options = ""
        extras_line = extras if extras else "No extra selected"
        return (
            f"Platform name:     {name}\n"
            f"PLATFORM:          {platform}\n"
            f"PLATFORM_SIZE:     {size}\n"
            f"Platform extras:   {extras_line}\n"
            f"Included options:  {options}\n"
            f"Standalone mode:   {standalone}\n"
        )
