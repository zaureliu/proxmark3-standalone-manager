"""Fluxo completo: configurar, compilar ou reutilizar cache, gravar e validar.

A gravação real só acontece quando ``flash_authorized`` é verdadeiro. Este
módulo não chama ``pm3-flash-all`` nem grava bootrom.
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from pm3manager.build.compiler import (
    assert_make_accepted,
    client_ready,
    preserve_bootrom,
    publish_fullimage,
    restore_snapshot,
    run_build,
    snapshot_artifacts,
    validate_fullimage,
)
from pm3manager.cache.store import FirmwareCache
from pm3manager.errors import AppError
from pm3manager.flash.flasher import (
    classify_flash_output,
    flash_script,
    plan_flash,
    verify_script,
)
from pm3manager.hardware.detector import match_after_reboot
from pm3manager.hardware.identity import parse_identity
from pm3manager.hardware.serial_lock import port_is_free
from pm3manager.logging_setup import audit, log
from pm3manager.messages import Msg
from pm3manager.models import BuildConfig, Device, Environment, IdentityReport, Module, OperationResult
from pm3manager.textutil import normalize_com
from pm3manager.modules.catalog import can_apply
from pm3manager.paths import data_dir
from pm3manager.preferences import Preferences
from pm3manager.proxspace.makefile import MakefileSession
from pm3manager.proxspace.shell import ProxSpaceShell
from pm3manager.workflow.lock import OperationLock

StageCallback = Callable[[str, str], None]
LogCallback = Callable[[str], None]


def size_option_allowed(prefs: Preferences) -> bool:
    """PLATFORM_SIZE=256 só vale para um MCU que o hw version mostrou como 256 KB."""
    mcu = prefs.detected_mcu or ""
    return "256" in mcu and "512" not in mcu


def flash_steps(**updates: str) -> dict[str, str]:
    """Etapas da gravação. Ausência de prova fica explícita; nada é preenchido por suposição."""
    details = {
        "etapa_comando": "nao_confirmada",
        "etapa_all_done": "nao_confirmada",
        "etapa_reconexao": "nao_confirmada",
        "etapa_comunicacao": "nao_confirmada",
        "etapa_versao": "nao_confirmada",
        "etapa_plataforma": "nao_confirmada",
        "etapa_modulo": "nao_confirmado",
        "etapa_laboratorio": "nao_realizado",
        "validacao": "nao_concluida",
    }
    details.update(updates)
    return details


def incompatible_flash(
    prefs: Preferences,
    config: BuildConfig,
    report: IdentityReport | None = None,
) -> str:
    """Mensagem que impede a gravação. Vazio quando a imagem pode seguir.

    MCU desconhecido não bloqueia o caminho PM3GENERIC de 512 KB já validado.
    Leitura e diagnóstico não passam por aqui.
    """
    kind = (report.firmware_kind if report is not None else "") or prefs.detected_firmware_kind or ""
    mcu = (report.mcu if report is not None and report.mcu else "") or prefs.detected_mcu or ""
    if kind == "RDV4":
        return Msg.FLASH_RDV4_BLOCKED
    small = "256" in mcu and "512" not in mcu
    if small and config.platform_size != "256":
        return Msg.FLASH_SIZE_BLOCKED
    if "512" in mcu and config.platform_size == "256":
        return Msg.FLASH_SIZE_BLOCKED
    return ""


def build_config(module_id: str, prefs: Preferences) -> BuildConfig:
    platform_size = "256" if size_option_allowed(prefs) else ""
    config = BuildConfig(
        platform="PM3GENERIC",
        standalone=module_id,
        extras=("FLASH",) if prefs.spi_flash_confirmada else (),
        led_order="PM3EASY",
        platform_size=platform_size,
    )
    config.validate()
    return config


class ManagerService:
    def __init__(
        self,
        env: Environment,
        prefs: Preferences,
        shell: ProxSpaceShell,
        cache: FirmwareCache,
        lock: OperationLock,
        detect: Callable[[], list[Device]] | None = None,
        port_free: Callable[[str], tuple[bool, str]] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.env = env
        self.prefs = prefs
        self.shell = shell
        self.cache = cache
        self.lock = lock
        self.detect = detect or (lambda: [])
        self.port_free = port_free or port_is_free
        self.sleeper = sleeper or time.sleep
        self.toolchain = ""

    def apply(
        self,
        module: Module,
        device: Device | None,
        *,
        force_rebuild: bool,
        flash_authorized: bool,
        on_stage: StageCallback | None = None,
        on_log: LogCallback | None = None,
    ) -> OperationResult:
        return self._guarded(
            "apply",
            lambda: self._apply(module, device, force_rebuild, flash_authorized, on_stage, on_log),
            module_id=module.id,
        )

    def recompile(
        self,
        module: Module,
        *,
        on_stage: StageCallback | None = None,
        on_log: LogCallback | None = None,
    ) -> OperationResult:
        return self._guarded(
            "recompile",
            lambda: self._compile_only(module, force_rebuild=True, on_stage=on_stage, on_log=on_log),
            module_id=module.id,
        )

    def verify(
        self,
        device: Device | None,
        *,
        on_stage: StageCallback | None = None,
        on_log: LogCallback | None = None,
    ) -> OperationResult:
        return self._guarded("verify", lambda: self._verify(device, on_stage, on_log))

    def ensure_toolchain(self) -> str:
        if self.toolchain:
            return self.toolchain
        result = self.shell.run_script(
            "#!/bin/bash\nset -eu\narm-none-eabi-gcc --version\n",
            timeout=60,
        )
        for line in result.output.splitlines():
            if "gcc" in line.lower():
                self.toolchain = line.strip()
                break
        if not self.toolchain:
            self.toolchain = "desconhecida"
        return self.toolchain

    def _guarded(
        self,
        owner: str,
        action: Callable[[], OperationResult],
        module_id: str = "",
    ) -> OperationResult:
        self._operation_id = f"{owner}-{uuid.uuid4().hex[:12]}"
        self._current_module = module_id
        if not self.lock.acquire(owner):
            result = OperationResult(False, "E010", Msg.BUSY, "busy", stage="concorrencia")
            self._record(result, module_id)
            return result
        try:
            return action()
        except AppError as exc:
            message = Msg.COMPILE_FAIL if exc.code in {"E200", "E201", "E202"} else exc.message
            stage = {
                "E200": "Compilação",
                "E201": "Validando artefatos",
                "E202": "Compilação",
            }.get(exc.code, "erro")
            result = OperationResult(
                False,
                exc.code,
                message,
                "error",
                technical=exc.technical,
                stage=stage,
            )
            self._record(result, self._current_module)
            return result
        except Exception as exc:
            result = OperationResult(
                False,
                "E400",
                "Falha inesperada.",
                "error",
                technical=str(exc),
                stage="erro",
            )
            self._record(result, self._current_module)
            return result
        finally:
            self.lock.release()

    def _apply(
        self,
        module: Module,
        device: Device | None,
        force_rebuild: bool,
        flash_authorized: bool,
        on_stage: StageCallback | None,
        on_log: LogCallback | None,
    ) -> OperationResult:
        allowed, reason = can_apply(module, self.prefs)
        if not allowed:
            code = "E104" if "incompatível" in reason.lower() else "E105"
            result = OperationResult(False, code, reason, "blocked", stage="bloqueio")
            self._record(result, module.id)
            return result
        config = build_config(module.id, self.prefs)
        if flash_authorized:
            plan = plan_flash(self.detect(), device)
            if not plan.allowed:
                result = OperationResult(False, plan.code, plan.message, "blocked", stage="gravação")
                self._record(result, module.id)
                return result
            device = plan.device
            blocked = incompatible_flash(self.prefs, config)
            if blocked:
                result = OperationResult(False, "E303", blocked, "blocked", stage="gravação")
                self._record(result, module.id)
                return result
        compiled = self._compile_only(
            module,
            force_rebuild=force_rebuild,
            on_stage=on_stage,
            on_log=on_log,
            record=False,
        )
        if not compiled.ok:
            self._record(compiled, module.id)
            return compiled
        if not flash_authorized:
            result = OperationResult(
                True,
                "OK100",
                Msg.FLASH_NOT_AUTHORIZED,
                compiled.outcome if compiled.outcome == "cache_hit" else "compile_only",
                stage=compiled.stage or "Compilação concluída",
                details=compiled.details,
            )
            self._record(result, module.id)
            return result
        if device is not None:
            report = self._preflight(device, on_log)
            if report is not None:
                # A imagem já compilada não muda de tamanho só porque o hw version chegou agora.
                blocked = incompatible_flash(self.prefs, config, report)
                if blocked:
                    result = OperationResult(
                        False,
                        "E303",
                        blocked,
                        "blocked",
                        technical=report.summary,
                        stage="gravação",
                        details=self._identity_details(report, {"module": module.id, "port": device.port}),
                    )
                    self._record(result, module.id)
                    return result
        return self._flash(module, device, on_stage, on_log)

    def _compile_only(
        self,
        module: Module,
        *,
        force_rebuild: bool,
        on_stage: StageCallback | None,
        on_log: LogCallback | None,
        record: bool = True,
    ) -> OperationResult:
        allowed, reason = can_apply(module, self.prefs)
        if not allowed:
            code = "E104" if "incompatível" in reason.lower() else "E105"
            result = OperationResult(False, code, reason, "blocked", stage="bloqueio")
            if record:
                self._record(result, module.id)
            return result
        config = build_config(module.id, self.prefs)
        self._stage(on_stage, "Consultando ferramentas", "Compilando")
        toolchain = self.ensure_toolchain()
        backup_dir = data_dir() / "backups"
        image = self.env.repo_root / "armsrc" / "obj" / "fullimage.elf"
        if not force_rebuild:
            cached = self.cache.lookup(self.env, config, toolchain)
            if cached and client_ready(self.env.repo_root):
                self._stage(on_stage, "Reutilizando cache", "Compilando")
                self._log(on_log, f"Cache válido para {module.id}. A compilação não será repetida.\n")
                backup = publish_fullimage(self.env.repo_root, cached.image, backup_dir)
                try:
                    digest = validate_fullimage(image, self.env.version)
                except Exception:
                    if backup is not None and backup.is_file():
                        shutil.copy2(backup, image)
                    raise
                with MakefileSession(
                    self.env.repo_root,
                    data_dir() / "state",
                    backup_dir,
                    config,
                ) as session:
                    session.keep()
                result = OperationResult(
                    True,
                    "OK100",
                    Msg.COMPILE_OK,
                    "cache_hit",
                    stage="Cache reutilizado",
                    details={"sha256": digest, "module": module.id, "cache": str(cached.directory)},
                )
                if record:
                    self._record(result, module.id)
                return result
        self._stage(on_stage, "Configurando compilação", "Compilando")
        snapshot = snapshot_artifacts(self.env.repo_root, backup_dir)
        log_path = data_dir() / "logs" / f"build-{module.id}.log"
        try:
            with MakefileSession(
                self.env.repo_root,
                data_dir() / "state",
                backup_dir,
                config,
            ) as session:
                self._stage(on_stage, "Compilando firmware", "Compilando")
                extras = " ".join(config.extras) if config.extras else "nenhum"
                size = config.platform_size or "512, padrão do make"
                self._log(
                    on_log,
                    f"Compilando {module.id} com PLATFORM={config.platform}, "
                    f"PLATFORM_EXTRAS={extras}, PLATFORM_SIZE={size}, LED_ORDER={config.led_order}.\n",
                )
                built = run_build(
                    self.env,
                    self.shell,
                    config,
                    timeout=2700,
                    on_line=self._file_and_ui(log_path, on_log),
                )
                if built.exit_code != 0:
                    raise AppError("E200", Msg.COMPILE_FAIL, built.output[-4000:])
                assert_make_accepted(built.output, config)
                self._stage(on_stage, "Validando artefatos", "Compilando")
                digest = validate_fullimage(image, self.env.version)
                if not client_ready(self.env.repo_root):
                    raise AppError("E201", Msg.COMPILE_FAIL, "proxmark3.exe não foi gerado.")
                preserve_bootrom(self.env.repo_root, snapshot)
                stored = self.cache.store(self.env, config, toolchain, image)
                session.keep()
        except Exception:
            restore_snapshot(self.env.repo_root, snapshot)
            preserve_bootrom(self.env.repo_root, snapshot)
            raise
        result = OperationResult(
            True,
            "OK100",
            Msg.COMPILE_OK,
            "compiled",
            stage="Compilação concluída",
            details={"sha256": digest, "module": module.id, "cache": str(stored.directory)},
        )
        if record:
            self._record(result, module.id)
        return result

    def _flash(
        self,
        module: Module,
        device: Device | None,
        on_stage: StageCallback | None,
        on_log: LogCallback | None,
    ) -> OperationResult:
        devices = self.detect()
        plan = plan_flash(devices, device)
        if not plan.allowed or plan.device is None:
            result = OperationResult(False, plan.code, plan.message, "blocked", stage=Msg.PREPARE_FLASH)
            self._record(result, module.id)
            return result
        self._stage(on_stage, Msg.PREPARE_FLASH, "Gravando")
        try:
            validate_fullimage(self.env.repo_root / "armsrc" / "obj" / "fullimage.elf", self.env.version)
        except AppError as exc:
            result = OperationResult(
                False,
                exc.code,
                exc.message,
                "error",
                technical=exc.technical,
                stage="Validando artefatos",
            )
            self._record(result, module.id)
            return result
        self._log(
            on_log,
            "Somente a fullimage será gravada. O bootloader não será alterado. "
            "Se o aparelho pedir o botão, desconecte o USB, segure o botão, "
            "conecte o cabo e solte o botão. O aplicativo não pressiona o botão.\n",
        )
        port = ""
        if plan.device is not None:
            try:
                port = normalize_com(plan.port_arg or plan.device.port)
            except ValueError:
                port = ""
        if port:
            free, reason = self.port_free(port)
            if not free and "em uso" in reason.lower():
                result = OperationResult(False, "E106", reason, "blocked")
                self._record(result, module.id)
                return result
        script = flash_script(self.env.repo_msys, plan.port_arg)
        log_path = data_dir() / "logs" / f"flash-{module.id}.log"
        flashed = self.shell.run_script(script, timeout=300, on_line=self._file_and_ui(log_path, on_log))
        if classify_flash_output(flashed.exit_code, flashed.output) != "command_ok":
            result = OperationResult(
                False,
                "E300",
                Msg.FLASH_UNCONFIRMED,
                "flash_unconfirmed",
                technical=flashed.output[-4000:],
                stage="Gravação não confirmada",
                details=flash_steps(),
            )
            self._record(result, module.id)
            return result
        self._stage(on_stage, Msg.WAIT_RECONNECT, "Validando")
        found = self._wait_for_device(plan.device, on_stage, on_log)
        if found is None:
            result = OperationResult(
                False,
                "E301",
                Msg.FLASH_NO_RECONNECT,
                "flash_no_reconnect",
                technical="A gravação terminou com 'All done', mas o dispositivo não voltou.",
                stage=Msg.WAIT_RECONNECT,
                details=flash_steps(
                    etapa_comando="concluida",
                    etapa_all_done="confirmada",
                ),
            )
            self._record(result, module.id)
            return result
        return self._validate_after_flash(module, found, on_stage, on_log)

    def _validate_after_flash(self, module, device: Device, on_stage, on_log) -> OperationResult:
        self._stage(on_stage, "Validando comunicação", "Validando")
        checked = self.shell.run_script(
            verify_script(self.env.repo_msys, device.port),
            timeout=120,
            on_line=on_log,
        )
        report = parse_identity(checked.output, exit_code=checked.exit_code, expected_version=self.env.version)
        self._log(on_log, report.summary + "\n")
        if report.communication_ok:
            self._remember_hardware(report)
        details = self._identity_details(report, {"module": module.id, "port": device.port})
        proved = {
            "etapa_comando": "concluida",
            "etapa_all_done": "confirmada",
            "etapa_reconexao": "confirmada",
        }
        if report.firmware_kind == "RDV4":
            details.update(
                flash_steps(
                    **proved,
                    etapa_comunicacao="confirmada" if report.communication_ok else "nao_confirmada",
                    etapa_plataforma="RDV4",
                    validacao="incompativel",
                )
            )
            result = OperationResult(
                False,
                "E303",
                Msg.DEVICE_INCOMPATIBLE,
                "incompatible_device",
                technical=report.summary,
                stage="Validando comunicação",
                details=details,
            )
        elif not report.communication_ok:
            details.update(flash_steps(**proved, etapa_comunicacao="falhou"))
            result = OperationResult(
                False,
                "E301",
                Msg.FLASH_NO_COMM,
                "flash_no_communication",
                technical=report.summary,
                stage="Validando comunicação",
                details=details,
            )
        elif report.version_mismatch:
            details.update(
                flash_steps(
                    **proved,
                    etapa_comunicacao="confirmada",
                    etapa_versao="nao_confere",
                    etapa_plataforma=report.firmware_kind or "nao_confirmada",
                )
            )
            result = OperationResult(
                False,
                "E301",
                Msg.FLASH_VERSION_MISMATCH,
                "flash_version_mismatch",
                technical=report.summary,
                stage="Validando comunicação",
                details=details,
            )
        else:
            # Comunicação e versão não identificam o módulo. OK200 fica reservado ao laboratório.
            details.update(
                flash_steps(
                    **proved,
                    etapa_comunicacao="confirmada",
                    etapa_versao="confere",
                    etapa_plataforma=report.firmware_kind or "nao_confirmada",
                    etapa_modulo="nao_confirmado",
                    etapa_laboratorio="nao_realizado",
                    validacao="parcial",
                )
            )
            message = Msg.FLASH_PARTIAL_CHECK
            if report.standalone_banner:
                message += (
                    " O firmware informou o texto do modo Standalone, "
                    "mas isso não confirma o módulo compilado: "
                    f"{report.standalone_banner}."
                )
            else:
                message += " O hw version e o hw status não informaram o modo Standalone."
            result = OperationResult(
                True,
                "OK210",
                message,
                "flash_partial_validation",
                technical=report.summary,
                stage="Validação parcial",
                details=details,
            )
        self._record(result, module.id)
        return result

    def _verify(self, device, on_stage, on_log) -> OperationResult:
        if device is None:
            result = OperationResult(False, "E100", Msg.NOT_FOUND, "comm_error", stage="verificacao")
            self._record(result, "")
            return result
        if device.confidence.value != "alta":
            result = OperationResult(False, "E103", Msg.MODEL_UNCONFIRMED, "comm_error", stage="verificacao")
            self._record(result, "")
            return result
        self._stage(on_stage, "Verificando dispositivo", "Verificando")
        checked = self.shell.run_script(
            verify_script(self.env.repo_msys, device.port),
            timeout=120,
            on_line=on_log,
        )
        report = parse_identity(checked.output, exit_code=checked.exit_code, expected_version=self.env.version)
        self._log(on_log, report.summary + "\n")
        if report.communication_ok:
            self._remember_hardware(report)
        details = self._identity_details(report, {"port": device.port})
        if report.communication_ok and report.firmware_kind == "RDV4":
            result = OperationResult(
                True,
                "OK202",
                Msg.RDV4_DIAGNOSTIC,
                "verified_restricted",
                technical=report.summary,
                details=details,
            )
        elif report.communication_ok and not report.version_mismatch:
            result = OperationResult(
                True,
                "OK201",
                Msg.detected(device.port),
                "verified",
                technical=report.summary,
                details=details,
            )
        else:
            result = OperationResult(False, "E103", Msg.MODEL_UNCONFIRMED, "comm_error", technical=report.summary)
        self._record(result, "")
        return result

    def _wait_for_device(self, previous: Device, on_stage, on_log) -> Device | None:
        waited = 0
        while waited <= 45:
            devices = self.detect()
            found = match_after_reboot(previous, devices)
            if found is not None:
                self._log(on_log, Msg.detected(found.port) + "\n")
                return found
            self._stage(on_stage, Msg.WAIT_RECONNECT, "Validando")
            self.sleeper(1)
            waited += 1
        return None

    def _preflight(self, device: Device, on_log: LogCallback | None) -> IdentityReport | None:
        checked = self.shell.run_script(
            verify_script(self.env.repo_msys, device.port),
            timeout=120,
            on_line=on_log,
        )
        report = parse_identity(checked.output, exit_code=checked.exit_code, expected_version=self.env.version)
        self._log(on_log, report.summary + "\n")
        if not report.communication_ok:
            return None
        self._remember_hardware(report)
        return report

    def _remember_hardware(self, report: IdentityReport) -> None:
        if report.firmware_kind:
            self.prefs.detected_firmware_kind = report.firmware_kind
        if report.mcu:
            self.prefs.detected_mcu = report.mcu
        if report.external_flash and report.external_flash != "não informado":
            self.prefs.detected_external_flash = report.external_flash
        if report.external_flash_size:
            self.prefs.detected_flash_size = report.external_flash_size
        if report.standalone_banner:
            self.prefs.detected_standalone = report.standalone_banner
        if report.smartcard:
            self.prefs.detected_smartcard = report.smartcard
        if report.bt_addon:
            self.prefs.detected_bt_addon = report.bt_addon
        mcu = report.mcu or ""
        if "256" in mcu and "512" not in mcu:
            self.prefs.platform_size_256 = True
        elif "512" in mcu:
            self.prefs.platform_size_256 = False
        if report.external_flash == "presente" and not self.prefs.spi_flash_recusada:
            self.prefs.spi_flash_confirmada = True
        elif report.external_flash == "ausente":
            self.prefs.spi_flash_confirmada = False
        self.prefs.save()

    @staticmethod
    def _identity_details(report: IdentityReport, extra: dict[str, str] | None = None) -> dict[str, str]:
        details = {
            "firmware": report.firmware_kind,
            "flash_externa": report.external_flash,
            "flash_size": report.external_flash_size,
            "standalone": report.standalone_banner,
            "mcu": report.mcu,
            "smartcard": report.smartcard,
            "bt_addon": report.bt_addon,
        }
        if extra:
            details.update(extra)
        return details

    @staticmethod
    def _stage(callback: StageCallback | None, stage: str, status: str) -> None:
        if callback:
            callback(stage, status)

    @staticmethod
    def _log(callback: LogCallback | None, text: str) -> None:
        if callback and text:
            callback(text)

    def _file_and_ui(self, path: Path, on_log: LogCallback | None):
        path.parent.mkdir(parents=True, exist_ok=True)

        def _write(chunk: str) -> None:
            with path.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(chunk)
            self._log(on_log, chunk)

        return _write

    def _record(self, result: OperationResult, module_id: str) -> None:
        if result.code == "E400":
            level = logging.CRITICAL
        elif result.code == "E010" or result.outcome == "flash_partial_validation":
            level = logging.WARNING
        elif result.ok:
            level = logging.INFO
        else:
            level = logging.ERROR
        module = module_id or getattr(self, "_current_module", "")
        operation = getattr(self, "_operation_id", "")
        log(
            level,
            result.code,
            result.message,
            result.technical,
            component="workflow",
            operation=operation,
            module=module,
            stage=result.stage,
            result=result.outcome,
        )
        audit(
            {
                "severity": logging.getLevelName(level),
                "code": result.code,
                "component": "workflow",
                "operation": operation,
                "module": module,
                "stage": result.stage,
                "result": result.outcome,
                "ok": result.ok,
                "outcome": result.outcome,
                "message": result.message,
                "technical": result.technical[:4000],
                "details": result.details,
            }
        )
