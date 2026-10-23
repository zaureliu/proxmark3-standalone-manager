"""Executa compilação e gravação fora da thread da interface."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from pm3manager.models import OperationResult


class ServiceWorker(QThread):
    log_ready = Signal(str)
    stage_changed = Signal(str, str)
    completed = Signal(object)

    def __init__(self, action) -> None:
        super().__init__()
        self._action = action

    def run(self) -> None:
        try:
            result = self._action(
                on_log=self.log_ready.emit,
                on_stage=self.stage_changed.emit,
            )
        except Exception:
            result = OperationResult(
                False,
                "E400",
                "Falha inesperada.",
                "error",
                technical=traceback.format_exc(),
            )
        self.completed.emit(result)
