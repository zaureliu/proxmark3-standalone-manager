"""Gera e executa ``make clean`` e ``make -j`` somente no repositório identificado."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from pm3manager.errors import BuildError
from pm3manager.models import BuildConfig, Environment, ShellResult
from pm3manager.proxspace.locator import assert_safe_repo
from pm3manager.proxspace.shell import ProxSpaceShell
from pm3manager.textutil import sha256_file

FULLIMAGE_REL = Path("armsrc") / "obj" / "fullimage.elf"
BOOTROM_REL = Path("bootrom") / "obj" / "bootrom.elf"
CLIENT_REL = Path("client") / "proxmark3.exe"
_MIN_ELF = 16_384
_MIN_CLIENT = 100_000


def build_script(repo_msys: str) -> str:
    assert_repo_msys(repo_msys)
    return f"""#!/bin/bash
set -eu
cd {repo_msys}
run() {{
  if command -v stdbuf >/dev/null 2>&1; then
    stdbuf -oL -eL "$@"
  else
    "$@"
  fi
}}
run make clean
run make -j
"""


def assert_repo_msys(repo_msys: str) -> None:
    from pm3manager.errors import SecurityError

    if not __import__("re").fullmatch(r"/pm3/proxmark3[A-Za-z0-9._-]*", repo_msys):
        raise SecurityError("E202", "make clean recusado fora do repositório Proxmark3.", repo_msys)


def client_ready(repo: Path) -> bool:
    path = repo / CLIENT_REL
    return path.is_file() and path.stat().st_size >= _MIN_CLIENT


def validate_fullimage(path: Path, version_token: str) -> str:
    if not path.is_file():
        raise BuildError("E201", "O artefato fullimage.elf não foi encontrado.", str(path))
    data = path.read_bytes()
    if len(data) < _MIN_ELF or not data.startswith(b"\x7fELF"):
        raise BuildError("E201", "fullimage.elf não é um ELF válido.", str(path))
    token = version_token.encode("utf-8")
    if token and token not in data:
        raise BuildError(
            "E201",
            "fullimage.elf não contém a versão esperada do repositório.",
            version_token,
        )
    return sha256_file(path)


def snapshot_artifacts(repo: Path, backup_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"prebuild-{stamp}"
    destination.mkdir(parents=True, exist_ok=True)
    relatives = (
        FULLIMAGE_REL,
        BOOTROM_REL,
        CLIENT_REL,
        Path(".Makefile.options.cache"),
        Path("recovery") / "bootrom.bin",
        Path("recovery") / "recovery.bin",
    )
    for relative in relatives:
        _copy_file(repo / relative, destination / relative)
    bootrom_obj = repo / "bootrom" / "obj"
    if bootrom_obj.is_dir():
        shutil.copytree(bootrom_obj, destination / "bootrom" / "obj", dirs_exist_ok=True)
    return destination


def restore_snapshot(repo: Path, snapshot: Path) -> None:
    if not snapshot.is_dir():
        return
    for path in snapshot.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(snapshot)
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def preserve_bootrom(repo: Path, snapshot: Path) -> None:
    """O ``make -j`` recompila o bootrom, mas esta etapa não pode deixá-lo alterado."""
    _mirror_tree(snapshot / "bootrom" / "obj", repo / "bootrom" / "obj")
    for name in ("bootrom.bin", "recovery.bin"):
        _mirror_file(snapshot / "recovery" / name, repo / "recovery" / name)


def _copy_file(source: Path, target: Path) -> None:
    if not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _mirror_file(source: Path, target: Path) -> None:
    if source.is_file():
        _copy_file(source, target)
    elif target.is_file():
        target.unlink()


def _mirror_tree(source: Path, target: Path) -> None:
    if not source.is_dir():
        if target.is_dir():
            shutil.rmtree(target)
        return
    target.mkdir(parents=True, exist_ok=True)
    expected = {path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()}
    for path in list(target.rglob("*")):
        if path.is_file() and path.relative_to(target).as_posix() not in expected:
            path.unlink()
    for path in source.rglob("*"):
        if path.is_file():
            _copy_file(path, target / path.relative_to(source))


def _inside(path: Path, root: Path) -> bool:
    if path.is_symlink():
        return False
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def publish_fullimage(repo: Path, source: Path, backup_dir: Path) -> Path | None:
    destination = repo / FULLIMAGE_REL
    if source.is_symlink() or not _inside(destination, repo):
        raise BuildError("E201", "O destino da fullimage não é seguro.", str(destination))
    if destination.is_symlink() or destination.parent.is_symlink():
        raise BuildError("E201", "A pasta da fullimage é um link. A imagem não foi copiada.", str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if destination.is_file():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = backup_dir / f"fullimage-previous-{stamp}.elf"
        if backup.is_symlink() or backup_dir.is_symlink():
            raise BuildError("E201", "O backup da fullimage é um link. A imagem não foi copiada.", str(backup))
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destination, backup)
    shutil.copy2(source, destination)
    return backup


def assert_make_accepted(output: str, config: BuildConfig) -> None:
    """O make imprime a configuração efetiva antes de compilar. Ela precisa bater."""
    from pm3manager.textutil import strip_ansi

    text = strip_ansi(output or "")
    problems: list[str] = []
    if f"PLATFORM:          {config.platform}" not in text:
        problems.append("PLATFORM")
    if f"Standalone mode:   {config.standalone}" not in text:
        problems.append("STANDALONE")
    if "Proxmark3 RDV4" in text:
        problems.append("o make ainda anunciou PM3RDV4")
    if "-DCHIP_AT91SAM7S" not in text:
        problems.append("CHIP_AT91SAM7S ausente; PM3GENERIC nesta versão exige LED_ORDER=PM3EASY")
    if config.extras:
        extras = " ".join(config.extras)
        if f"Platform extras:   {extras}" not in text:
            problems.append("PLATFORM_EXTRAS")
    elif "Platform extras:   No extra selected" not in text:
        problems.append("PLATFORM_EXTRAS")
    size = config.platform_size or "512"
    if f"PLATFORM_SIZE:     {size}" not in text:
        problems.append("PLATFORM_SIZE")
    if problems:
        raise BuildError(
            "E202",
            "O make não aplicou a configuração pedida. A compilação foi interrompida.",
            "; ".join(problems),
        )


def run_build(
    env: Environment,
    shell: ProxSpaceShell,
    config: BuildConfig,
    *,
    timeout: float,
    on_line=None,
) -> ShellResult:
    assert_safe_repo(env)
    config.validate()
    script = build_script(env.repo_msys)
    if "make clean" not in script or "make -j" not in script:
        raise BuildError("E202", "Script de compilação incompleto.")
    if script.find(f"cd {env.repo_msys}") > script.find("make clean"):
        raise BuildError("E202", "make clean ficaria fora do diretório do repositório.")
    return shell.run_script(script, timeout=timeout, on_line=on_line)
