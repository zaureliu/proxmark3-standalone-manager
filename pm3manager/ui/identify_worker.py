"""Identificação fora da thread da interface."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class IdentifyWorker(QThread):
    finished_profile = Signal(object)

    def __init__(self, action) -> None:
        super().__init__()
        self._action = action

    def run(self) -> None:
        try:
            profile = self._action()
        except Exception:
            profile = None
        self.finished_profile.emit(profile)
