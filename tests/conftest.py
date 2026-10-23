import os
from pathlib import Path

import pytest

from pm3manager.paths import project_root


def _watched_paths() -> tuple[Path, ...]:
    paths = [
        project_root() / "var" / "logs" / "app.log",
        project_root() / "var" / "logs" / "operations.jsonl",
    ]
    pm3 = project_root().parent / "ProxSpace" / "pm3"
    repos = sorted(path for path in pm3.glob("proxmark3*") if path.is_dir()) if pm3.is_dir() else []
    preferred = [path for path in repos if path.name == "proxmark3-v4.23346"]
    repo = preferred[0] if preferred else (repos[-1] if repos else None)
    if repo is not None:
        paths.append(repo / "Makefile.platform")
        paths.append(repo / ".Makefile.options.cache")
    return tuple(paths)


_WATCHED = _watched_paths()


def _snapshot(paths) -> dict[Path, bytes | None]:
    found = {}
    for path in paths:
        found[path] = path.read_bytes() if path.exists() else None
    return found


@pytest.fixture(autouse=True)
def isolate_process_logs(tmp_path, monkeypatch):
    """Cada teste escreve em diretório próprio e não pode alterar o log operacional."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PM3MANAGER_ENV", "teste")
    monkeypatch.setenv("PM3MANAGER_LOG_DIR", str(log_dir))
    from pm3manager.logging_setup import reset_logging

    reset_logging()
    before = _snapshot(_WATCHED)
    yield log_dir
    reset_logging()
    after = _snapshot(_WATCHED)
    changed = [str(path) for path, old in before.items() if after[path] != old]
    if changed:
        raise AssertionError(
            "Um teste alterou o log operacional ou a configuração de plataforma já validada: "
            + "; ".join(changed)
        )


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setattr("pm3manager.workflow.service.data_dir", lambda: tmp_path)
    monkeypatch.setattr("pm3manager.logging_setup.data_dir", lambda: tmp_path)
    monkeypatch.setattr("pm3manager.preferences.data_dir", lambda: tmp_path)
    monkeypatch.setattr("pm3manager.paths.data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    yield application
