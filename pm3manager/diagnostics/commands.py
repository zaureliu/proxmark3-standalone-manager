"""Comandos de diagnóstico permitidos nesta versão do cliente Iceman.

`hw version`, `hw status` e `hw ping` foram conferidos em
``client/src/cmdhw.c`` do checkout v4.23346. Os três apenas consultam.
`hw ping` sem argumentos usa o exemplo documentado no próprio comando.
`hw bootloader`, `hw reset`, `hw readmem`, `hw tearoff` e qualquer
comando RFID ficam de fora.
"""

from __future__ import annotations

from pm3manager.errors import SecurityError

SAFE_COMMANDS = ("hw version", "hw status", "hw ping")

_FORBIDDEN = (
    "pm3-flash",
    "hw bootloader",
    "hw reset",
    "hw readmem",
    "hw tearoff",
    "hw tia",
    "--unlock-bootloader",
    " lf ",
    " hf ",
    "git ",
    "make ",
)


def validate_commands(commands: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    chosen = tuple(commands)
    if not chosen or any(item not in SAFE_COMMANDS for item in chosen):
        raise SecurityError(
            "E304",
            "O diagnóstico só executa hw version, hw status e hw ping.",
            " ".join(chosen),
        )
    return chosen


def render_script(repo_msys: str, port: str, commands: tuple[str, ...] | None = None) -> str:
    """Script bash sem ``set -e``, para uma falha não esconder a resposta seguinte."""
    from pm3manager.build.compiler import assert_repo_msys
    from pm3manager.textutil import normalize_com

    assert_repo_msys(repo_msys)
    com = normalize_com(port)
    selected = validate_commands(commands or SAFE_COMMANDS)
    lines = ["#!/bin/bash", f"cd {repo_msys}"]
    for command in selected:
        lines.append(
            f"./pm3 -p {com} -c '{command}' || echo \"PM3MANAGER_CMD_FAIL {command} $?\""
        )
    script = "\n".join(lines) + "\n"
    lowered = f" {script.lower()} "
    for token in _FORBIDDEN:
        if token in lowered:
            raise SecurityError("E304", "Comando de diagnóstico recusado.", token.strip())
    return script
