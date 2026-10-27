"""Executa um processo com timeout e cancelamento. Encerra a árvore de filhos."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from dataclasses import dataclass

CREATE_NO_WINDOW = 0x08000000


@dataclass
class ProcessResult:
    exit_code: int
    output: str
    timed_out: bool
    cancelled: bool


def run_process(
    command: list[str],
    *,
    cwd: str,
    timeout: float,
    cancel: threading.Event,
    popen=None,
) -> ProcessResult:
    """A leitura da saída fica noutra thread para o timeout não depender de uma linha nova."""
    factory = popen or subprocess.Popen
    process = factory(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def _read() -> None:
        try:
            stream = process.stdout
            if stream is None:
                return
            while True:
                line = stream.readline()
                if not line:
                    break
                lines.put(line)
        finally:
            lines.put(None)

    reader = threading.Thread(target=_read, name="pm3-diag-read", daemon=True)
    reader.start()
    chunks: list[str] = []
    started = time.monotonic()
    timed_out = False
    cancelled = False
    try:
        while True:
            if cancel.is_set():
                cancelled = True
                _kill_tree(process.pid)
                break
            if time.monotonic() - started > timeout:
                timed_out = True
                _kill_tree(process.pid)
                break
            try:
                line = lines.get(timeout=0.05)
            except queue.Empty:
                if process.poll() is not None:
                    try:
                        line = lines.get(timeout=0.2)
                    except queue.Empty:
                        break
                else:
                    continue
            if line is None:
                break
            chunks.append(line)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _kill_tree(process.pid)
            process.wait(timeout=5)
    finally:
        if process.poll() is None:
            _kill_tree(process.pid)
        reader.join(timeout=2)
    output = "".join(chunks)
    if timed_out:
        output += "\nTempo esgotado.\n"
    if cancelled:
        output += "\nDiagnóstico cancelado.\n"
    return ProcessResult(process.returncode or 0, output, timed_out, cancelled)


def _kill_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
