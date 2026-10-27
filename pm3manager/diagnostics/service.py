"""Orquestra a coleta. A análise fica em outro módulo e não grava firmware."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime

from pm3manager import __version__
from pm3manager.diagnostics.analyze import analyze
from pm3manager.diagnostics.client_runner import run_client
from pm3manager.diagnostics.environment import essential_files, git_snapshot, read_makefile, toolchain_found
from pm3manager.diagnostics.models import Observation
from pm3manager.hardware.detector import detect_devices
from pm3manager.hardware.serial_lock import port_is_free
from pm3manager.models import Device, Module
from pm3manager.workflow.context import AppContext
from pm3manager.workflow.lock import OperationLock
from pm3manager.workflow.service import build_config

Collect = Callable[[str, threading.Event], Observation]


class DiagnosticService:
    def __init__(self, lock: OperationLock, collect: Collect, clock: Callable[[], str] | None = None) -> None:
        self.lock = lock
        self.collect = collect
        self.clock = clock or (lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self, mode: str = "full"):
        if mode not in {"full", "refresh"}:
            mode = "full"
        if not self.lock.acquire("diagnostics"):
            observation = Observation(
                generated_at=self.clock(),
                app_version=__version__,
                mode=mode,
                blocked_reason=f"lock:{self.lock.owner or 'ocupado'}",
            )
            return analyze(observation)
        self._cancel = threading.Event()
        try:
            try:
                observation = self.collect(mode, self._cancel)
            except Exception as exc:
                observation = Observation(
                    generated_at=self.clock(),
                    app_version=__version__,
                    mode=mode,
                    client_error=str(exc),
                )
            observation.generated_at = observation.generated_at or self.clock()
            observation.app_version = observation.app_version or __version__
            observation.mode = mode
            return analyze(observation)
        finally:
            self.lock.release()


def live_collect(context: AppContext, device: Device | None, module: Module | None, work_dir, timeout: float = 60):
    """Fecha sobre o contexto atual. A porta ocupada não recebe o cliente."""

    def collect(mode: str, cancel: threading.Event) -> Observation:
        env = context.env
        prefs = context.prefs
        selected = device() if callable(device) else device
        chosen = module() if callable(module) else module
        free: bool | None = None
        message = ""
        attempted = False
        output = ""
        exit_code = 0
        timed_out = False
        cancelled = False
        error = ""
        commands: tuple[str, ...] = ()
        if mode == "full" and selected is not None and not cancel.is_set():
            free, message = port_is_free(selected.port)
            if free:
                attempted = True
                exit_code, output, timed_out, cancelled, error, commands = run_client(
                    env,
                    selected.port,
                    work_dir=work_dir,
                    timeout=timeout,
                    cancel=cancel,
                )
            else:
                error = message
        elif mode == "full" and selected is None:
            error = "Nenhum dispositivo selecionado."
        intended_platform = ""
        intended_standalone = ""
        intended_extras = ""
        intended_led = ""
        intended_size = ""
        if chosen is not None:
            try:
                config = build_config(chosen.id, prefs)
            except Exception as exc:
                error = error or str(exc)
            else:
                intended_platform = config.platform
                intended_standalone = config.standalone
                intended_extras = " ".join(config.extras)
                intended_led = config.led_order
                intended_size = config.platform_size
        makefile_present, makefile = read_makefile(env.repo_root if env is not None else None)
        git = git_snapshot(env.repo_root if env is not None else None)
        proxspace_ok = bool(env is not None and env.proxspace_root.is_dir() and (env.proxspace_root / "runme64.bat").is_file())
        checkout_ok = bool(env is not None and env.repo_root.is_dir() and (env.repo_root / "Makefile").is_file())
        return Observation(
            generated_at="",
            app_version=__version__,
            mode=mode,
            devices=detect_devices(),
            selected=selected,
            port_free=free,
            port_message=message,
            client_attempted=attempted,
            client_output=output,
            client_exit=exit_code,
            client_timed_out=timed_out,
            client_cancelled=cancelled,
            client_error=error,
            commands=commands,
            env_present=env is not None,
            proxspace_present=proxspace_ok,
            checkout_present=checkout_ok,
            checkout_name=env.repo_root.name if env is not None else "",
            version_file=env.version if env is not None else "",
            version_token=env.commit if env is not None else "",
            essential=essential_files(env),
            toolchain_found=toolchain_found(env.proxspace_root if env is not None else None),
            git_state=str(git["git_state"]),
            git_commit=str(git["git_commit"]),
            git_shallow=git["git_shallow"],  # type: ignore[arg-type]
            git_dirty=git["git_dirty"],  # type: ignore[arg-type]
            git_dirty_count=int(git["git_dirty_count"]),
            makefile_present=makefile_present,
            makefile=makefile,
            intended_platform=intended_platform,
            intended_standalone=intended_standalone,
            intended_extras=intended_extras,
            intended_led_order=intended_led,
            intended_platform_size=intended_size,
            prefs_mcu=prefs.detected_mcu,
            prefs_firmware_kind=prefs.detected_firmware_kind,
            prefs_external_flash=prefs.detected_external_flash,
            spi_confirmed=bool(prefs.spi_flash_confirmada),
            module=chosen,
            module_confirmed_uncertain=bool(chosen and chosen.id in prefs.confirmed_uncertain_modules),
        )

    return collect
