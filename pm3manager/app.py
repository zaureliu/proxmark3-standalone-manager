"""Ponto de entrada. ``--self-check`` não abre a janela e não grava firmware."""

from __future__ import annotations

import json
import sys

from pm3manager.errors import AppError
from pm3manager.hardware.detector import detect_devices
from pm3manager.logging_setup import log, setup_logging
from pm3manager.models import Compatibility, Confidence
from pm3manager.paths import data_dir
from pm3manager.workflow.context import AppContext


def _load_qt() -> str | None:
    """Importa Qt sem abrir janela. Devolve o erro, ou None se as DLLs carregaram."""
    try:
        import PySide6.QtCore  # noqa: F401
        import PySide6.QtGui  # noqa: F401
        import PySide6.QtWidgets  # noqa: F401
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def self_check() -> int:
    setup_logging()
    qt_error = _load_qt()
    if qt_error:
        payload = {
            "ok": False,
            "code": "E000",
            "message": "A interface Qt não carregou.",
            "technical": qt_error,
            "qt_loaded": False,
        }
        _write_check(payload)
        log(40, "E000", payload["message"], qt_error, component="app", stage="autoverificacao", result="erro")
        return 1
    try:
        context = AppContext.load()
    except AppError as exc:
        payload = {
            "ok": False,
            "code": exc.code,
            "message": exc.message,
            "technical": exc.technical,
            "qt_loaded": True,
        }
        _write_check(payload)
        log(40, exc.code, exc.message, exc.technical, component="app", stage="autoverificacao", result="erro")
        return 1
    devices = detect_devices()
    counts = {item.value: 0 for item in Compatibility}
    for module in context.modules:
        counts[module.compatibility.value] += 1
    payload = {
        "ok": bool(context.modules),
        "proxspace": str(context.env.proxspace_root),
        "repo": str(context.env.repo_root),
        "version": context.env.version,
        "commit": context.env.commit,
        "build_time": context.env.build_time,
        "modules": len(context.modules),
        "compatibility": counts,
        "makefile_platform_in_repo": (context.env.repo_root / "Makefile.platform").is_file(),
        "external_makefile": str(context.env.external_makefile or ""),
        "external_has_flash": "PLATFORM_EXTRAS=FLASH" in context.env.external_makefile_text,
        "devices_high": sum(1 for device in devices if device.confidence == Confidence.HIGH),
        "devices_medium": sum(1 for device in devices if device.confidence == Confidence.MEDIUM),
        "flash_authorized": context.prefs.flash_autorizado,
        "recovery_note": context.recovery_note,
        "qt_loaded": True,
    }
    _write_check(payload)
    log(
        20,
        "OK000",
        "Autoverificação concluída.",
        json.dumps(payload, ensure_ascii=False),
        component="app",
        stage="autoverificacao",
        result="ok",
    )
    return 0 if payload["ok"] else 1


def _write_check(payload: dict) -> None:
    path = data_dir() / "self-check.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-check" in args:
        return self_check()
    from pm3manager.ui.main_window import run_gui

    return run_gui()
