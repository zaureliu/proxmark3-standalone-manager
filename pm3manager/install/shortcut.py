"""Cria o atalho usando a pasta Desktop real do usuário, inclusive OneDrive."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from pm3manager.errors import AppError
from pm3manager.proxspace.shell import CREATE_NO_WINDOW

SHORTCUT_NAME = "Proxmark3 Standalone Manager.lnk"


def desktop_directory() -> Path:
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )
    path = Path((completed.stdout or "").strip())
    if completed.returncode != 0 or not path.is_dir():
        raise AppError("E400", "Não foi possível localizar a área de trabalho.", completed.stderr.strip())
    return path


def create_shortcut(exe: Path, lnk: Path, working_directory: Path, icon: Path | None = None) -> Path:
    exe = exe.resolve()
    working_directory = working_directory.resolve()
    lnk = Path(lnk)
    icon_file = (icon or exe).resolve()
    for path in (exe, working_directory, lnk, icon_file):
        text = str(path)
        if any(character in text for character in ('"', "\n", "\r", "'")):
            raise AppError("E400", "Caminho inválido para o atalho.", text)
    if exe.suffix.lower() != ".exe" or not exe.is_file():
        raise AppError("E400", "O executável do atalho não existe.", str(exe))
    lnk.parent.mkdir(parents=True, exist_ok=True)
    script_dir = Path(tempfile.mkdtemp())
    script = script_dir / "criar_atalho.ps1"
    script.write_text(
        "\n".join(
            [
                "$shell = New-Object -ComObject WScript.Shell",
                f"$shortcut = $shell.CreateShortcut('{lnk}')",
                f"$shortcut.TargetPath = '{exe}'",
                f"$shortcut.WorkingDirectory = '{working_directory}'",
                f"$shortcut.IconLocation = '{icon_file},0'",
                "$shortcut.WindowStyle = 1",
                "$shortcut.Description = 'Troca o modulo Standalone do Proxmark3'",
                "$shortcut.Save()",
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )
    shutil.rmtree(script_dir, ignore_errors=True)
    if completed.returncode != 0 or not lnk.is_file():
        raise AppError("E400", "Não foi possível criar o atalho.", completed.stderr.strip() or completed.stdout.strip())
    return lnk


def read_shortcut(lnk: Path) -> dict[str, str]:
    script_dir = Path(tempfile.mkdtemp())
    script = script_dir / "ler_atalho.ps1"
    script.write_text(
        "\n".join(
            [
                "$shell = New-Object -ComObject WScript.Shell",
                f"$shortcut = $shell.CreateShortcut('{lnk}')",
                'Write-Output ("TARGET=" + $shortcut.TargetPath)',
                'Write-Output ("WORKDIR=" + $shortcut.WorkingDirectory)',
                'Write-Output ("ICON=" + $shortcut.IconLocation)',
                'Write-Output ("STYLE=" + $shortcut.WindowStyle)',
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )
    shutil.rmtree(script_dir, ignore_errors=True)
    values: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values
