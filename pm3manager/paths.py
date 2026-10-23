"""Diretórios do aplicativo. O código não fica dentro da árvore do firmware."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _frozen_search_roots() -> tuple[Path, ...]:
    """Pasta do executável, o pai e o avô.

    O one-file de desenvolvimento fica em ``dist\\``. O one-dir fica em
    ``dist\\<nome>\\``. Três níveis acham ``.pm3manager-root`` nos dois
    formatos e não sobem mais: uma cópia fora da árvore não herda o marcador.
    """
    here = Path(sys.executable).resolve().parent
    roots = [here]
    parent = here.parent
    if parent != here:
        roots.append(parent)
        grandparent = parent.parent
        if grandparent != parent:
            roots.append(grandparent)
    return tuple(roots)


def _marked_development_root() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    for candidate in _frozen_search_roots():
        marker = candidate / ".pm3manager-root"
        if marker.is_file() and not marker.is_symlink():
            return candidate
    return None


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        marked = _marked_development_root()
        if marked is not None:
            return marked
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def is_development_tree() -> bool:
    """Árvore de código, ou executável ainda dentro dela.

    Uma pasta copiada para outro disco não tem o marcador e não é tratada
    como instalação de desenvolvimento.
    """
    if not getattr(sys, "frozen", False):
        return True
    return _marked_development_root() is not None


def user_config_dir() -> Path:
    """Configuração do executável distribuído. Não depende do nome do usuário."""
    base = os.environ.get("LOCALAPPDATA", "").strip()
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / "Proxmark3StandaloneManager"


def _dev_marker_root() -> Path | None:
    if not getattr(sys, "frozen", False):
        return project_root()
    return _marked_development_root()


def data_dir() -> Path:
    override = os.environ.get("PM3MANAGER_DATA_DIR", "").strip()
    if override:
        path = Path(override)
    else:
        marker = _dev_marker_root()
        # A instalação de desenvolvimento continua em var/, junto dos backups.
        # O executável copiado para outro computador usa LOCALAPPDATA.
        path = (marker / "var") if marker is not None else user_config_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base = project_root()
    return base.joinpath(*parts)
