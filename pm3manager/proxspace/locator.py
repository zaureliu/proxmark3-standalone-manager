"""Descobre o ProxSpace, o repositório Iceman e a versão já instalada.

Não atualiza o git e não escolhe um checkout só pelo nome da pasta: lê
``common/default_version_pm3.c``. O ``Makefile.platform`` em ``pm3/`` fica fora
dos repositórios e não é o arquivo incluído pelo make.

Não há caminho pessoal fixo. A preferência salva, quando existe, não cai
silenciosamente em outra instalação.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

from pm3manager.errors import ProxSpaceError
from pm3manager.messages import Msg
from pm3manager.models import Environment
from pm3manager.paths import project_root

_VERSION_STRINGS = re.compile(
    r'"([^"\\]*)"\s*,\s*"([^"\\]*)"\s*,\s*"([^"\\]*)"',
)
_FINGERPRINT_SUFFIXES = {".c", ".h", ".s", ".ld", ".mk"}
_FINGERPRINT_NAMES = {"Makefile", "Makefile.hal", "Makefile.inc", "Makefile.common", "Makefile.defs", "Makefile.host"}
_REPO_NAME = re.compile(r"proxmark3[A-Za-z0-9._-]*")


def _version_of(repo: Path) -> tuple[str, str, str]:
    path = repo / "common" / "default_version_pm3.c"
    if not path.is_file():
        raise ProxSpaceError("E002", "Versão do firmware não encontrada.", str(path))
    match = _VERSION_STRINGS.search(path.read_text(encoding="utf-8", errors="replace"))
    if not match:
        raise ProxSpaceError("E002", "Não foi possível ler a versão do firmware.", str(path))
    return match.group(1), match.group(2), match.group(3)


def _version_key(version: str) -> tuple[int, ...]:
    match = re.search(r"v(\d+(?:\.\d+)*)", version)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def _is_repo(path: Path) -> bool:
    return (
        path.is_dir()
        and not path.is_symlink()
        and (path / "Makefile").is_file()
        and (path / "armsrc" / "Standalone" / "Makefile.hal").is_file()
        and (path / "pm3-flash-fullimage").is_file()
        and (path / "pm3").is_file()
    )


def _accepted_repo(pm3: Path, repo: Path) -> bool:
    if not _REPO_NAME.fullmatch(repo.name) or not _is_repo(repo):
        return False
    try:
        resolved = repo.resolve()
        parent = pm3.resolve()
    except OSError:
        return False
    return parent in resolved.parents


def source_fingerprint(repo: Path) -> str:
    """Impressão do código que muda o firmware. Ignora objetos, imagens e links."""
    roots = [repo / "armsrc", repo / "common_arm", repo / "common", repo / "include", repo / "bootrom"]
    extras = [repo / "Makefile", repo / "Makefile.defs", repo / "Makefile.host"]
    files: list[Path] = []
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(repo)
            if "obj" in relative.parts or "deps" in relative.parts:
                continue
            if path.name in _FINGERPRINT_NAMES or path.suffix.lower() in _FINGERPRINT_SUFFIXES:
                files.append(path)
    for path in extras:
        if path.is_file() and not path.is_symlink():
            files.append(path)
    digest = hashlib.sha256()
    for path in sorted(set(files)):
        relative = path.relative_to(repo).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _forced_root() -> Path | None:
    for key in ("PM3MANAGER_PROXSPACE", "PROXSPACE"):
        value = os.environ.get(key, "").strip()
        if value:
            return Path(value)
    return None


def _candidate_roots() -> list[Path]:
    root = project_root()
    found = [root.parent / "ProxSpace", root / "ProxSpace"]
    if getattr(sys, "frozen", False):
        here = Path(sys.executable).resolve().parent
        found.extend((here / "ProxSpace", here.parent / "ProxSpace"))
    found.append(Path.cwd() / "ProxSpace")
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in found:
        try:
            key = str(candidate.resolve()).casefold()
        except OSError:
            key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _usable_root(root: Path) -> bool:
    try:
        if not root.exists():
            return False
    except OSError:
        return False
    if not (root / "runme64.bat").is_file() or not (root / "msys2" / "msys2_shell.cmd").is_file():
        return False
    pm3 = root / "pm3"
    if not pm3.is_dir() or pm3.is_symlink():
        return False
    try:
        children = list(pm3.iterdir())
    except OSError:
        return False
    return any(_accepted_repo(pm3, path) for path in children)


def _require_root(root: Path) -> Path:
    try:
        resolved = root.resolve()
    except OSError as exc:
        raise ProxSpaceError("E001", Msg.PROXSPACE_MISSING, f"Pasta inacessível: {root} ({exc})") from exc
    if _usable_root(resolved):
        return resolved
    raise ProxSpaceError(
        "E001",
        Msg.PROXSPACE_MISSING,
        f"A pasta informada não tem runme64.bat, msys2\\msys2_shell.cmd e um checkout em pm3: {resolved}",
    )


def discover_proxspace() -> Path:
    forced = _forced_root()
    if forced is not None:
        return _require_root(forced)
    tried: list[str] = []
    for candidate in _candidate_roots():
        tried.append(str(candidate))
        if _usable_root(candidate):
            return candidate.resolve()
    raise ProxSpaceError(
        "E001",
        Msg.PROXSPACE_MISSING,
        "Nenhuma instalação válida foi encontrada. Procurado em: " + "; ".join(tried),
    )


def locate(proxspace_root: Path | None = None, repo_dirname: str = "") -> Environment:
    root = _require_root(proxspace_root) if proxspace_root is not None else discover_proxspace()
    pm3 = root / "pm3"
    repos = [path for path in pm3.iterdir() if _accepted_repo(pm3, path)]
    if not repos:
        raise ProxSpaceError("E002", "Nenhum repositório Proxmark3 foi encontrado em pm3.", str(pm3))
    if repo_dirname and not _REPO_NAME.fullmatch(repo_dirname):
        raise ProxSpaceError("E002", "O repositório configurado não é um checkout Proxmark3.", repo_dirname)
    if repo_dirname:
        chosen = [path for path in repos if path.name == repo_dirname]
        if not chosen:
            raise ProxSpaceError("E002", "O repositório configurado não existe.", repo_dirname)
        repo = chosen[0]
    else:
        repo = max(repos, key=lambda path: _version_key(_version_of(path)[0]))
    version, build_time, commit = _version_of(repo)
    external = pm3 / "Makefile.platform"
    external_text = ""
    if external.is_file() and not external.is_symlink() and external.parent == pm3:
        external_text = external.read_text(encoding="utf-8", errors="replace")
    names = tuple(sorted(path.name for path in repos))
    return Environment(
        proxspace_root=root,
        repo_root=repo,
        repo_msys=f"/pm3/{repo.name}",
        msys_shell=root / "msys2" / "msys2_shell.cmd",
        version=version,
        commit=commit,
        build_time=build_time,
        external_makefile=external if external.is_file() and not external.is_symlink() else None,
        external_makefile_text=external_text,
        source_fingerprint=source_fingerprint(repo),
        available_repos=names,
    )


def assert_safe_repo(env: Environment) -> None:
    repo = env.repo_root.resolve()
    pm3 = (env.proxspace_root / "pm3").resolve()
    if pm3 not in repo.parents or not repo.name.startswith("proxmark3"):
        raise ProxSpaceError("E202", "O repositório identificado não está dentro de pm3.", str(repo))
    if not _is_repo(env.repo_root):
        raise ProxSpaceError("E002", "O repositório deixou de parecer uma árvore Proxmark3.", str(repo))
    if not re.fullmatch(r"/pm3/proxmark3[A-Za-z0-9._-]*", env.repo_msys):
        raise ProxSpaceError("E202", "Caminho MSYS do repositório recusado.", env.repo_msys)
