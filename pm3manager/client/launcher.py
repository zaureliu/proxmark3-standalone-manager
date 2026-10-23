"""Abre o cliente interativo numa janela própria, na porta detectada."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pm3manager.errors import AppError
from pm3manager.flash.flasher import client_command
from pm3manager.models import Environment
from pm3manager.proxspace.shell import CREATE_NO_WINDOW
from pm3manager.textutil import batch_path


def launch_client(env: Environment, port: str | None, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    command = client_command(env.repo_msys, port)
    root = batch_path(env.proxspace_root)
    shell_cmd = batch_path(env.msys_shell)
    bat = work_dir / "abrir-cliente.bat"
    bat.write_bytes(
        (
            "@echo off\r\n"
            "title Proxmark3\r\n"
            f'cd /d "{root}"\r\n'
            f'call "{shell_cmd}" -mingw64 -defterm -no-start -c "{command}"\r\n'
            "echo.\r\n"
            "echo Cliente encerrado. Codigo: %ERRORLEVEL%\r\n"
            "pause\r\n"
        ).encode("ascii")
    )
    completed = subprocess.run(
        ["cmd.exe", "/c", "start", "", str(bat)],
        cwd=str(env.proxspace_root),
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    if completed.returncode != 0:
        raise AppError("E302", "Não foi possível abrir o cliente Proxmark3.", f"código {completed.returncode}")
    return bat
