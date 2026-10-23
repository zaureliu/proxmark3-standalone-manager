"""Log persistente. Um processo de teste não abre o arquivo operacional."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pm3manager.paths import data_dir, project_root

_LOGGER_NAME = "pm3manager"
_BOUND_PATH: Path | None = None
_BOUND_ENV: str | None = None
_FALLBACK_DIR: Path | None = None
_LOCK = threading.Lock()

# O campo do LogRecord se chama module_id porque "module" é reservado pelo logging.
_FORMAT = (
    "%(asctime)s utc=%(timestamp)s %(levelname)s "
    "env=%(environment)s component=%(component)s operation=%(operation)s "
    "code=%(code)s module=%(module_id)s stage=%(stage)s result=%(result)s "
    "%(message)s"
)

_USER_PATH = re.compile(r"(?i)([A-Za-z]:[\\/]+Users[\\/]+)[^\\/\s:]+")
_UNIX_USER = re.compile(r"(/(?:home|Users)/)[^/\s]+")
_UNIQUE = re.compile(r"(?i)(unique\s*id\s*[:=]\s*)(\S+)")
_SECRET = re.compile(
    r"(?i)((?:serial(?:\s*number)?|password|token|secret|api[_-]?key)\s*[:=]\s*)(\S+)"
)


class LogIsolationError(RuntimeError):
    """O processo de teste tentou abrir o log operacional."""


def environment_name() -> str:
    forced = os.environ.get("PM3MANAGER_ENV", "").strip().lower()
    if forced in {"teste", "producao"}:
        return forced
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return "teste"
    return "producao"


def pytest_running() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def redact(text: str) -> str:
    if not text:
        return ""
    cleaned = _USER_PATH.sub(r"\1<usuario>", text)
    cleaned = _UNIX_USER.sub(r"\1<usuario>", cleaned)
    cleaned = _UNIQUE.sub(r"\1<oculto>", cleaned)
    cleaned = _SECRET.sub(r"\1<oculto>", cleaned)
    return cleaned


def redact_value(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    return value


def operational_log_dir() -> Path:
    return (project_root() / "var" / "logs").resolve()


def _is_operational_log_path(path: Path) -> bool:
    try:
        candidate = path.resolve()
    except OSError:
        return False
    operational = operational_log_dir()
    if candidate == operational or candidate == operational / "app.log":
        return True
    try:
        candidate.relative_to(operational)
        return True
    except ValueError:
        return False


def _fallback_test_dir() -> Path:
    global _FALLBACK_DIR
    if _FALLBACK_DIR is None:
        _FALLBACK_DIR = Path(tempfile.mkdtemp(prefix="pm3manager-logs-teste-"))
    return _FALLBACK_DIR


def _testing_process() -> bool:
    return pytest_running() or environment_name() == "teste"


def resolve_log_dir() -> Path:
    override = os.environ.get("PM3MANAGER_LOG_DIR", "").strip()
    if override:
        path = Path(override)
        if _testing_process() and _is_operational_log_path(path):
            raise LogIsolationError(
                "O processo de teste recusou o diretório de log operacional."
            )
        return path
    if _testing_process():
        candidate = data_dir() / "logs"
        if not _is_operational_log_path(candidate):
            return candidate
        return _fallback_test_dir()
    return data_dir() / "logs"


class _EventContext(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        defaults = {
            "code": "-",
            "environment": environment_name(),
            "component": "app",
            "operation": "-",
            "module_id": "-",
            "stage": "-",
            "result": "-",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for name, default in defaults.items():
            if not getattr(record, name, ""):
                setattr(record, name, default)
        return True


def reset_logging() -> None:
    global _BOUND_PATH, _BOUND_ENV
    with _LOCK:
        logger = logging.getLogger(_LOGGER_NAME)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        _BOUND_PATH = None
        _BOUND_ENV = None


def setup_logging() -> logging.Logger:
    global _BOUND_PATH, _BOUND_ENV
    with _LOCK:
        logger = logging.getLogger(_LOGGER_NAME)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        target_dir = resolve_log_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = (target_dir / "app.log").resolve()
        env = environment_name()
        if logger.handlers and _BOUND_PATH == target and _BOUND_ENV == env:
            return logger
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        handler = RotatingFileHandler(
            target,
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
        handler.addFilter(_EventContext())
        logger.addHandler(handler)
        _BOUND_PATH = target
        _BOUND_ENV = env
        return logger


def _blank(value: str) -> str:
    text = (value or "").strip()
    return text or "-"


def log(
    level: int,
    code: str,
    message: str,
    technical: str = "",
    *,
    component: str = "app",
    operation: str = "",
    module: str = "",
    stage: str = "",
    result: str = "",
    environment: str = "",
) -> None:
    logger = setup_logging()
    safe_message = redact(message)
    safe_technical = redact(technical)
    text = safe_message
    if safe_technical and safe_technical != safe_message:
        text = f"{safe_message} | {safe_technical}"
    logger.log(
        level,
        "%s",
        text,
        extra={
            "code": code or "-",
            "environment": environment or environment_name(),
            "component": _blank(component),
            "operation": _blank(operation),
            "module_id": _blank(module),
            "stage": _blank(stage),
            "result": _blank(result),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def audit(event: dict) -> None:
    path = resolve_log_dir() / "operations.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "at": datetime.now(timezone.utc).isoformat(),
        "environment": environment_name(),
    }
    payload.update(redact_value(event))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def latest_log_file() -> Path:
    return resolve_log_dir() / "app.log"
