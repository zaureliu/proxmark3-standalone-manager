"""Acorda só quando a compilação de auditoria termina ou o processo morre."""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PID_FILE = ROOT / "var" / "audit-pid.txt"
STATUS = ROOT / "var" / "audit-status.txt"
TRACE = ROOT / "var" / "audit-watch.log"


def alive(pid: int) -> bool:
    if pid <= 0:
        return False
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def emit(line: str, code: int) -> int:
    print(line, flush=True)
    return code


def main() -> int:
    TRACE.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 50 * 60
    pid = 0
    while time.monotonic() < deadline:
        if STATUS.is_file():
            text = STATUS.read_text(encoding="utf-8", errors="replace").strip() or "sem mensagem"
            if text.startswith("SUCCESS"):
                return emit("DONE: " + text, 0)
            return emit("FAILED: " + text, 1)
        if pid == 0 and PID_FILE.is_file():
            try:
                pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            except ValueError:
                pid = 0
        if pid and not alive(pid):
            time.sleep(3)
            if STATUS.is_file():
                text = STATUS.read_text(encoding="utf-8", errors="replace").strip() or "sem mensagem"
                if text.startswith("SUCCESS"):
                    return emit("DONE: " + text, 0)
                return emit("FAILED: " + text, 1)
            return emit("FAILED: a compilação encerrou sem escrever o status", 1)
        with TRACE.open("a", encoding="utf-8") as handle:
            handle.write(f"pid={pid} waiting\n")
        time.sleep(30)
    return emit("FAILED: a compilação passou de 50 minutos", 1)


if __name__ == "__main__":
    sys.exit(main())
