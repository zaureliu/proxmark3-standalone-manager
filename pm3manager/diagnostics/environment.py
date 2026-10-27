"""Leitura do ProxSpace, do checkout e do Git. Não altera nenhum dos três."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pm3manager.models import Environment
from pm3manager.proxspace.makefile import active_assignments

CREATE_NO_WINDOW = 0x08000000
_GIT_ALLOWED = {
    ("rev-parse", "--is-inside-work-tree"),
    ("rev-parse", "HEAD"),
    ("rev-parse", "--is-shallow-repository"),
    ("status", "--porcelain"),
}
_TOOLCHAIN = (
    Path("msys2") / "mingw64" / "bin" / "arm-none-eabi-gcc.exe",
    Path("msys2") / "usr" / "bin" / "arm-none-eabi-gcc.exe",
    Path("gcc-arm-none-eabi") / "bin" / "arm-none-eabi-gcc.exe",
)


def essential_files(env: Environment | None) -> dict[str, bool]:
    if env is None:
        return {}
    mapping = {
        "runme64.bat": env.proxspace_root / "runme64.bat",
        "msys2_shell.cmd": env.msys_shell,
        "Makefile": env.repo_root / "Makefile",
        "Makefile.hal": env.repo_root / "armsrc" / "Standalone" / "Makefile.hal",
        "pm3": env.repo_root / "pm3",
    }
    return {name: path.is_file() for name, path in mapping.items()}


def toolchain_found(proxspace_root: Path | None) -> bool | None:
    if proxspace_root is None or not proxspace_root.exists():
        return None
    return any((proxspace_root / relative).is_file() for relative in _TOOLCHAIN)


def read_makefile(repo_root: Path | None) -> tuple[bool | None, dict[str, list[str]]]:
    if repo_root is None or not repo_root.exists():
        return None, {}
    target = repo_root / "Makefile.platform"
    if not target.is_file() or target.is_symlink():
        return False, {}
    text = target.read_text(encoding="utf-8", errors="replace")
    return True, active_assignments(text)


def git_snapshot(repo_root: Path | None, runner=None) -> dict[str, object]:
    """Consulta Git com uma lista fechada de argumentos. Não faz fetch nem checkout."""
    empty = {
        "git_state": "indisponivel",
        "git_commit": "",
        "git_shallow": None,
        "git_dirty": None,
        "git_dirty_count": 0,
    }
    if repo_root is None or not repo_root.exists():
        return empty
    run = runner or _git
    try:
        code, output, _error = run(repo_root, ("rev-parse", "--is-inside-work-tree"))
    except OSError:
        return empty
    if code != 0 or output.strip().lower() != "true":
        empty["git_state"] = "not_repo"
        return empty
    state = dict(empty)
    state["git_state"] = "repo"
    head_code, head, _error = run(repo_root, ("rev-parse", "HEAD"))
    if head_code == 0 and len(head.strip()) >= 7:
        state["git_commit"] = head.strip()
    shallow_code, shallow, _error = run(repo_root, ("rev-parse", "--is-shallow-repository"))
    if shallow_code == 0:
        state["git_shallow"] = shallow.strip().lower() == "true"
    status_code, status, _error = run(repo_root, ("status", "--porcelain"))
    if status_code == 0:
        rows = [line for line in status.splitlines() if line.strip()]
        state["git_dirty"] = bool(rows)
        state["git_dirty_count"] = len(rows)
    return state


def _git(repo: Path, args: tuple[str, ...]) -> tuple[int, str, str]:
    if args not in _GIT_ALLOWED:
        raise OSError("argumento Git fora da lista somente leitura")
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr
