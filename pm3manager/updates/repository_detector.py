"""Identifica a instalação selecionada. Não escreve no checkout nem no ProxSpace."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from pm3manager.models import Environment
from pm3manager.proxspace.makefile import active_assignments
from pm3manager.updates.models import UNKNOWN_VERSION, LocalInstall
from pm3manager.updates.version_comparator import parse_version

_GIT_COMMANDS = {"rev-parse", "status", "describe", "rev-list", "remote", "diff"}
_VERSION_FILES = (
    "VERSION",
    "version.txt",
    "PROXSPACE_VERSION",
    "setup/VERSION",
    "setup/version.txt",
)
_CREATE_NO_WINDOW = 0x08000000


def inspect_iceman(env: Environment | None, runner=None) -> LocalInstall:
    if env is None:
        return LocalInstall()
    install = inspect_git_checkout(env.repo_root, runner=runner)
    version = (env.version or install.version or "").strip()
    label = version if parse_version(version).known or version else UNKNOWN_VERSION
    platform, standalone, extras = _read_platform(env.repo_root)
    notes = list(install.notes)
    if platform or standalone:
        notes.append(_platform_note(platform, standalone, extras))
    fingerprint = (env.commit or "").strip()
    if fingerprint:
        notes.append(
            f"Identificador no arquivo de versão: {fingerprint}. Não é o Git HEAD."
        )
    return LocalInstall(
        present=True,
        kind=install.kind or "checkout",
        path=str(env.repo_root),
        version=version,
        version_label=label,
        commit=install.commit,
        branch=install.branch,
        tag=install.tag,
        detached=install.detached,
        dirty=install.dirty,
        unpushed=install.unpushed,
        remote_url=install.remote_url,
        platform=platform,
        standalone=standalone,
        extras=extras,
        firmware_commit=(env.commit or "").strip(),
        notes=tuple(notes),
    )


def inspect_proxspace(root: Path | None, runner=None) -> LocalInstall:
    if root is None:
        return LocalInstall(version_label=UNKNOWN_VERSION)
    try:
        resolved = root.resolve()
    except OSError:
        return LocalInstall(path=str(root), version_label=UNKNOWN_VERSION)
    if not resolved.is_dir():
        return LocalInstall(path=str(resolved), version_label=UNKNOWN_VERSION)
    git_present = (resolved / ".git").exists()
    if git_present:
        install = inspect_git_checkout(resolved, runner=runner)
        version = install.tag or _read_version_file(resolved) or install.version
        label = version if version else UNKNOWN_VERSION
        return LocalInstall(
            present=True,
            kind="checkout",
            path=str(resolved),
            version=version,
            version_label=label,
            commit=install.commit,
            branch=install.branch,
            tag=install.tag,
            detached=install.detached,
            dirty=install.dirty,
            unpushed=install.unpushed,
            remote_url=install.remote_url,
            notes=install.notes,
        )
    version = _read_version_file(resolved)
    kind = "pacote" if (resolved / "runme64.bat").is_file() else "desconhecido"
    return LocalInstall(
        present=True,
        kind=kind,
        path=str(resolved),
        version=version,
        version_label=version or UNKNOWN_VERSION,
        notes=("Instalação sem checkout Git." if kind == "pacote" else "Origem da instalação não identificada.",),
    )


def inspect_git_checkout(path: Path, runner=None) -> LocalInstall:
    run = runner or default_git
    try:
        resolved = path.resolve()
    except OSError:
        return LocalInstall(path=str(path), kind="desconhecido", version_label=UNKNOWN_VERSION)
    if not resolved.is_dir() or resolved.is_symlink():
        return LocalInstall(path=str(resolved), kind="desconhecido", version_label=UNKNOWN_VERSION)
    # Sem um .git neste diretório, o Git subiria para um repositório pai.
    marker = resolved / ".git"
    if not marker.exists() or marker.is_symlink():
        return LocalInstall(
            path=str(resolved),
            kind="desconhecido",
            version_label=UNKNOWN_VERSION,
            present=True,
        )
    inside = _git(run, resolved, ["rev-parse", "--is-inside-work-tree"])
    if inside is None or inside.strip() != "true":
        return LocalInstall(path=str(resolved), kind="desconhecido", version_label=UNKNOWN_VERSION, present=resolved.is_dir())
    head = (_git(run, resolved, ["rev-parse", "HEAD"]) or "").strip()
    branch = (_git(run, resolved, ["rev-parse", "--abbrev-ref", "HEAD"]) or "").strip()
    detached = branch == "HEAD"
    tag = (_git(run, resolved, ["describe", "--tags", "--exact-match", "HEAD"]) or "").strip()
    dirty = _is_dirty(run, resolved)
    remote = (_git(run, resolved, ["remote", "get-url", "origin"]) or "").strip()
    unpushed = _unpushed(run, resolved)
    notes: list[str] = []
    if detached:
        notes.append("HEAD desanexado.")
    if dirty:
        notes.append("Há alterações locais não commitadas.")
    if unpushed:
        notes.append(f"Commits locais à frente da referência já registrada neste clone: {unpushed}.")
    version = tag
    return LocalInstall(
        present=True,
        kind="checkout",
        path=str(resolved),
        version=version,
        version_label=version or UNKNOWN_VERSION,
        commit=head,
        branch="" if detached else branch,
        tag=tag,
        detached=detached,
        dirty=dirty,
        unpushed=unpushed,
        remote_url=remote,
        notes=tuple(notes),
    )


def default_git(repo: Path, args: list[str]) -> tuple[int, str]:
    if not args or args[0] not in _GIT_COMMANDS:
        raise ValueError("comando git não permitido")
    if any(item == "--" or str(item).startswith("-c") for item in args[1:]):
        raise ValueError("argumento git não permitido")
    command = ["git", "-C", str(repo), *args]
    flags = _CREATE_NO_WINDOW if os.name == "nt" else 0
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
        shell=False,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
    )
    output = completed.stdout or ""
    if completed.returncode != 0 and not output:
        output = ""
    return completed.returncode, output


def _git(run, repo: Path, args: list[str]) -> str | None:
    try:
        code, output = run(repo, args)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    if code != 0:
        return None
    return output


def _is_dirty(run, repo: Path) -> bool:
    porcelain = _git(run, repo, ["status", "--porcelain"])
    if porcelain is not None:
        return bool(porcelain.strip())
    tracked = _git(run, repo, ["diff", "--name-only"])
    staged = _git(run, repo, ["diff", "--cached", "--name-only"])
    return bool((tracked or "").strip() or (staged or "").strip())


def _unpushed(run, repo: Path) -> int | None:
    upstream = _git(run, repo, ["rev-parse", "--abbrev-ref", "@{upstream}"])
    if not upstream:
        return None
    count = _git(run, repo, ["rev-list", "--count", "@{upstream}..HEAD"])
    if count is None:
        return None
    try:
        return int(count.strip() or "0")
    except ValueError:
        return None


def _read_platform(repo: Path) -> tuple[str, str, str]:
    path = repo / "Makefile.platform"
    try:
        if not path.is_file() or path.is_symlink():
            return "", "", ""
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", "", ""
    found = active_assignments(text)
    platform = found["PLATFORM"][-1] if found["PLATFORM"] else ""
    standalone = found["STANDALONE"][-1] if found["STANDALONE"] else ""
    extras = found["PLATFORM_EXTRAS"][-1] if found["PLATFORM_EXTRAS"] else ""
    return platform, standalone, extras


def _platform_note(platform: str, standalone: str, extras: str) -> str:
    parts = [item for item in (platform, f"STANDALONE={standalone}" if standalone else "", extras) if item]
    return "Plataforma lida: " + ", ".join(parts)


def _read_version_file(root: Path) -> str:
    for relative in _VERSION_FILES:
        path = root.joinpath(*relative.split("/"))
        try:
            if not path.is_file() or path.is_symlink():
                continue
            if path.stat().st_size > 4096:
                continue
            line = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        except OSError:
            continue
        if not line:
            continue
        candidate = line[0].strip()
        if candidate and len(candidate) <= 80 and "://" not in candidate:
            return candidate
    return ""
