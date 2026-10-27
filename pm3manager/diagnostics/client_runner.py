"""Abre o cliente oficial só com os três comandos de leitura."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from pm3manager.diagnostics.commands import SAFE_COMMANDS, render_script
from pm3manager.diagnostics.process import run_process
from pm3manager.errors import AppError
from pm3manager.models import Environment
from pm3manager.textutil import bash_invocation, batch_path, to_msys_path

CREATE_NO_WINDOW = 0x08000000


def run_client(
    env: Environment,
    port: str,
    *,
    work_dir: Path,
    timeout: float,
    cancel: threading.Event,
) -> tuple[int, str, bool, bool, str, tuple[str, ...]]:
    """Devolve código, saída, timeout, cancelamento, erro e os comandos usados."""
    try:
        script = render_script(env.repo_msys, port, SAFE_COMMANDS)
    except (AppError, ValueError) as exc:
        return 1, "", False, False, str(exc), ()
    work_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    script_path = work_dir / f"diag-{token}.sh"
    bat_path = work_dir / f"diag-{token}.bat"
    try:
        script_path.write_bytes(script.replace("\r\n", "\n").encode("utf-8"))
        invocation = bash_invocation(to_msys_path(script_path))
        bat_path.write_bytes(
            (
                "@echo off\r\n"
                f'cd /d "{batch_path(env.proxspace_root)}"\r\n'
                f'call "{batch_path(env.msys_shell)}" -mingw64 -defterm -no-start -c "{invocation}"\r\n'
                "exit /b %ERRORLEVEL%\r\n"
            ).encode("ascii")
        )
        result = run_process(
            ["cmd.exe", "/c", str(bat_path)],
            cwd=str(env.proxspace_root),
            timeout=timeout,
            cancel=cancel,
        )
        return result.exit_code, result.output, result.timed_out, result.cancelled, "", SAFE_COMMANDS
    except (OSError, ValueError) as exc:
        return 1, "", False, cancel.is_set(), str(exc), ()
    finally:
        for path in (script_path, bat_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
