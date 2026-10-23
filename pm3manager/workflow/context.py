"""Carrega o ambiente real uma vez e entrega as peças para a interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pm3manager.cache.store import FirmwareCache
from pm3manager.models import Environment, Module
from pm3manager.modules.catalog import export_catalog, load_modules

from pm3manager.paths import data_dir, is_development_tree, project_root
from pm3manager.preferences import Preferences
from pm3manager.proxspace.locator import locate
from pm3manager.proxspace.makefile import recover_interrupted
from pm3manager.proxspace.shell import ProxSpaceShell
from pm3manager.workflow.lock import OperationLock


def export_development_catalog(modules: list[Module]) -> None:
    """Grava o catálogo na árvore de código só no desenvolvimento.

    O executável copiado para outra pasta não escreve ao lado do .exe.
    """
    if not is_development_tree():
        return
    try:
        export_catalog(modules, project_root() / "catalog" / "modulos.json")
    except OSError:
        pass


@dataclass
class AppContext:
    env: Environment
    prefs: Preferences
    modules: list[Module]
    shell: ProxSpaceShell
    cache: FirmwareCache
    lock: OperationLock
    recovery_note: str = ""

    @classmethod
    def load(cls) -> "AppContext":
        prefs = Preferences.load()
        note = recover_interrupted(data_dir() / "state") or ""
        saved = prefs.proxspace_root.strip()
        env = locate(Path(saved) if saved else None, repo_dirname=prefs.repo_dirname)
        modules = load_modules(env)
        export_catalog(modules, data_dir() / "catalog.json")
        export_development_catalog(modules)
        return cls(
            env=env,
            prefs=prefs,
            modules=modules,
            shell=ProxSpaceShell(env, data_dir() / "tmp"),
            cache=FirmwareCache(data_dir() / "cache"),
            lock=OperationLock(),
            recovery_note=note,
        )
