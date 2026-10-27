"""Decide se a identificação ativa pode rodar. Não altera preferências nem o Makefile."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pm3manager.diagnostics.sanitize import sanitize
from pm3manager.hardware.profile import HardwareProfile, IdentifyInput, identify
from pm3manager.models import Device, Environment
from pm3manager.workflow.lock import OperationLock


class ProbeAction(str, Enum):
    NONE = "none"
    DEFER = "defer"
    REUSE = "reuse"
    PROBE = "probe"
    SKIP_TEST = "skip_test"


@dataclass(frozen=True)
class ProbeRequest:
    has_device: bool
    locked: bool
    port_free: bool
    cache_fresh: bool
    under_test: bool = False


def automatic_probe_allowed() -> bool:
    return "PYTEST_CURRENT_TEST" not in os.environ


def choose_probe(request: ProbeRequest) -> ProbeAction:
    if not request.has_device:
        return ProbeAction.NONE
    if request.under_test:
        return ProbeAction.SKIP_TEST
    if request.locked or not request.port_free:
        return ProbeAction.DEFER
    if request.cache_fresh:
        return ProbeAction.REUSE
    return ProbeAction.PROBE


def cache_key(identity_key: str, commit: str) -> str:
    return f"{commit}\n{identity_key}"


@dataclass
class _CacheEntry:
    key: str
    profile: HardwareProfile


class IdentificationCache:
    """Resultado de uma leitura. Não serve para outro aparelho."""

    def __init__(self) -> None:
        self._entry: _CacheEntry | None = None

    def store(self, identity_key: str, commit: str, profile: HardwareProfile) -> None:
        self._entry = _CacheEntry(cache_key(identity_key, commit), profile)

    def lookup(self, identity_key: str, commit: str) -> HardwareProfile | None:
        entry = self._entry
        if entry is None or entry.key != cache_key(identity_key, commit):
            return None
        if entry.profile.stale:
            return None
        return entry.profile

    def invalidate(self) -> None:
        if self._entry is not None:
            self._entry.profile.stale = True
            self._entry = None


def probe_profile(
    *,
    env: Environment,
    device: Device,
    lock: OperationLock,
    port_free,
    cancel: threading.Event,
    device_count: int,
    configured_platform: str = "",
    led_order: str = "",
    prefs_kind: str = "",
    work_dir: Path,
    timeout: float = 25.0,
    runner=None,
) -> HardwareProfile:
    """Leitura só dos três comandos seguros. Descarta saída parcial."""
    base = IdentifyInput(
        device=device,
        device_count=device_count,
        expected_version=env.version,
        configured_platform=configured_platform,
        led_order=led_order,
        prefs_kind=prefs_kind,
        source="usb",
    )
    usb_only = identify(base)
    if cancel.is_set():
        usb_only.evidence = usb_only.evidence + ("A identificação foi cancelada antes da leitura.",)
        return usb_only
    if not lock.acquire("identification"):
        usb_only.active_deferred = True
        usb_only.evidence = usb_only.evidence + (
            "Identificação ativa adiada: já existe operação usando a porta.",
        )
        return usb_only
    try:
        if cancel.is_set():
            usb_only.evidence = usb_only.evidence + ("A identificação foi cancelada.",)
            return usb_only
        free, _reason = port_free(device.port)
        if not free:
            usb_only.active_deferred = True
            usb_only.evidence = usb_only.evidence + (
                "Identificação ativa adiada: a porta não está livre.",
            )
            return usb_only
        call = runner or _default_runner
        code, output, timed_out, cancelled, _error, _commands = call(
            env,
            device.port,
            work_dir=work_dir,
            timeout=timeout,
            cancel=cancel,
        )
        if timed_out or cancelled or cancel.is_set():
            usb_only.evidence = usb_only.evidence + (
                "A leitura foi cancelada ou expirou. A resposta parcial foi descartada.",
            )
            return usb_only
        text = sanitize(output or "", _secrets(device))
        if not text.strip():
            usb_only.evidence = usb_only.evidence + ("O cliente não devolveu texto utilizável.",)
            return usb_only
        return identify(
            IdentifyInput(
                device=device,
                device_count=device_count,
                client_text=text,
                client_exit=code,
                expected_version=env.version,
                configured_platform=configured_platform,
                led_order=led_order,
                prefs_kind=prefs_kind,
                source="cliente",
            )
        )
    finally:
        if lock.owner == "identification":
            lock.release()


def _secrets(device: Device) -> tuple[str, ...]:
    serial = (device.serial_number or "").strip()
    if len(serial) < 6:
        return ()
    return (serial,)


def _default_runner(env, port, *, work_dir, timeout, cancel):
    from pm3manager.diagnostics.client_runner import run_client

    return run_client(env, port, work_dir=work_dir, timeout=timeout, cancel=cancel)
