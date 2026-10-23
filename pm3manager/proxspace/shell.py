"""Executa bash dentro do MSYS2 do ProxSpace.

``runme64.bat`` chama ``setup\\setup.cmd`` em toda abertura. Esse setup reescreve
o fstab e apaga ``/etc/passwd``. O ambiente já está instalado, então os comandos
usam o mesmo ``msys2_shell.cmd -mingw64 -defterm -no-start`` que o ``runme64.bat``
dispara depois do setup, sem repetir essa rotina.

O corpo do comando vai para um arquivo ``.sh``. O ``cmd.exe`` só recebe
``bash`` e um caminho sem espaços, então ``shell=True`` não é necessário e
caracteres como ``!`` não passam pelo delayed expansion do batch.
"""

from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path

from pm3manager.errors import SecurityError
from pm3manager.models import Environment, ShellResult
from pm3manager.textutil import bash_invocation, batch_path, to_msys_path

CREATE_NO_WINDOW = 0x08000000
_FORBIDDEN = (
    "pm3-flash-all",
    "pm3-flash-bootrom",
    "--unlock-bootloader",
    "git ",
    "git\t",
    "rm -rf",
    "pacman",
    "mkfs",
    "shutdown",
)


class ProxSpaceShell:
    def __init__(self, env: Environment, work_dir: Path) -> None:
        self.env = env
        self.work_dir = work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def run_script(self, script: str, *, timeout: float, on_line=None) -> ShellResult:
        self._guard(script)
        token = uuid.uuid4().hex
        script_path = self.work_dir / f"task-{token}.sh"
        bat_path = self.work_dir / f"task-{token}.bat"
        script_path.write_bytes(script.replace("\r\n", "\n").encode("utf-8"))
        msys_script = to_msys_path(script_path)
        invocation = bash_invocation(msys_script)
        root = batch_path(self.env.proxspace_root)
        shell_cmd = batch_path(self.env.msys_shell)
        bat_path.write_bytes(
            (
                "@echo off\r\n"
                f'cd /d "{root}"\r\n'
                f'call "{shell_cmd}" -mingw64 -defterm -no-start -c "{invocation}"\r\n'
                "exit /b %ERRORLEVEL%\r\n"
            ).encode("ascii")
        )
        started = time.monotonic()
        process = subprocess.Popen(
            ["cmd.exe", "/c", str(bat_path)],
            cwd=str(self.env.proxspace_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        chunks: list[str] = []
        pending: list[str] = []
        last_emit = time.monotonic()
        assert process.stdout is not None
        try:
            for line in process.stdout:
                chunks.append(line)
                pending.append(line)
                now = time.monotonic()
                if on_line and (now - last_emit >= 0.15 or len(pending) >= 30):
                    on_line("".join(pending))
                    pending.clear()
                    last_emit = now
            if on_line and pending:
                on_line("".join(pending))
            try:
                process.wait(timeout=max(1.0, timeout - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                _kill_tree(process.pid)
                process.wait(timeout=15)
                output = "".join(chunks) + "\nTempo esgotado.\n"
                return ShellResult(124, output, time.monotonic() - started)
        finally:
            for path in (script_path, bat_path):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        return ShellResult(process.returncode or 0, "".join(chunks), time.monotonic() - started)

    @staticmethod
    def _guard(script: str) -> None:
        lowered = script.lower()
        for token in _FORBIDDEN:
            if token in lowered:
                raise SecurityError(
                    "E304",
                    "Comando recusado por segurança.",
                    f"O script contém '{token.strip()}', que este aplicativo não executa.",
                )


def _kill_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
