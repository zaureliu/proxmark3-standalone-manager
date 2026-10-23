"""Exclusão mútua entre compilação e gravação."""

from __future__ import annotations

import threading


class OperationLock:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.owner = ""

    def acquire(self, owner: str) -> bool:
        if not self._lock.acquire(blocking=False):
            return False
        self.owner = owner
        return True

    def release(self) -> None:
        self.owner = ""
        self._lock.release()

    @property
    def locked(self) -> bool:
        return self._lock.locked()
