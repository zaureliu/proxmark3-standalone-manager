"""Compila LF_SAMYRUN sem gravar o Proxmark3 e testa o cache.

Não chama pm3-flash-all, pm3-flash-bootrom nem pm3-flash-fullimage.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATUS = ROOT / "var" / "audit-status.txt"
RESULT = ROOT / "var" / "audit-result.json"
PID_FILE = ROOT / "var" / "audit-pid.txt"
FORBIDDEN = ("pm3-flash-all", "pm3-flash-bootrom", "pm3-flash-fullimage", "--unlock-bootloader")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_status(ok: bool, message: str) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(("SUCCESS " if ok else "FAILED ") + message + "\n", encoding="utf-8")


def _finish(ok: bool, payload: dict) -> int:
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_status(ok, str(payload.get("message", "")))
    print(("SUCCESS" if ok else "FAILED") + " " + str(payload.get("message", "")), flush=True)
    return 0 if ok else 1


class CountingShell:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.scripts: list[str] = []

    def run_script(self, script: str, *, timeout: float, on_line=None):
        self.scripts.append(script)
        for token in FORBIDDEN:
            if token in script:
                raise RuntimeError(f"gravação recusada: {token}")
        return self.inner.run_script(script, timeout=timeout, on_line=on_line)


def main() -> int:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(__import__("os").getpid()), encoding="utf-8")
    if STATUS.exists():
        STATUS.unlink()
    payload: dict = {"message": "compilação não concluída"}
    try:
        from pm3manager.hardware.detector import detect_devices
        from pm3manager.hardware.identity import parse_identity
        from pm3manager.models import Compatibility, Confidence
        from pm3manager.workflow.context import AppContext
        from pm3manager.workflow.service import ManagerService, build_config

        started = datetime.now().isoformat(timespec="seconds")
        backup_root = ROOT / "var" / "audit-backup" / datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_root.mkdir(parents=True, exist_ok=True)
        context = AppContext.load()
        env = context.env
        prefs = context.prefs
        prefs.flash_autorizado = False
        counts: dict[str, int] = {}
        modules = {}
        for module in context.modules:
            counts[module.compatibility.value] = counts.get(module.compatibility.value, 0) + 1
            modules[module.id] = module
        payload.update(
            {
                "started": started,
                "repo": str(env.repo_root),
                "version": env.version,
                "commit": env.commit,
                "modules": len(context.modules),
                "compatibility": counts,
                "parent_makefile": str(env.external_makefile or ""),
            }
        )
        selected = modules.get("LF_SAMYRUN")
        if selected is None or selected.compatibility != Compatibility.COMPATIBLE:
            payload["message"] = "LF_SAMYRUN não está compatível no catálogo."
            return _finish(False, payload)

        parent = env.proxspace_root / "pm3" / "Makefile.platform"
        parent_before = parent.read_bytes() if parent.is_file() else b""
        (backup_root / "pm3-Makefile.platform").write_bytes(parent_before)
        fullimage = env.repo_root / "armsrc" / "obj" / "fullimage.elf"
        bootrom = env.repo_root / "bootrom" / "obj" / "bootrom.elf"
        cache_file = env.repo_root / ".Makefile.options.cache"
        client = env.repo_root / "client" / "proxmark3.exe"
        for source in (fullimage, bootrom, cache_file, client):
            if source.is_file():
                target = backup_root / source.name
                shutil.copy2(source, target)
        bootrom_before = _sha256(bootrom) if bootrom.is_file() else ""
        fullimage_before = _sha256(fullimage) if fullimage.is_file() else ""
        client_before = _sha256(client) if client.is_file() else ""
        payload["backup"] = str(backup_root)
        payload["fullimage_before"] = {"sha256": fullimage_before, "size": fullimage.stat().st_size if fullimage.is_file() else 0}
        payload["bootrom_before"] = bootrom_before

        devices = detect_devices()
        payload["devices"] = [
            {"port": device.port, "name": device.hardware_name, "confidence": device.confidence.value, "reason": device.reason}
            for device in devices
        ]
        shell = CountingShell(context.shell)
        service = ManagerService(
            env,
            prefs,
            shell,
            context.cache,
            context.lock,
            detect=detect_devices,
        )
        high = [device for device in devices if device.confidence == Confidence.HIGH]
        if len(high) > 1:
            payload["message"] = "Há mais de um Proxmark3. A compilação foi interrompida."
            return _finish(False, payload)
        if len(high) == 1:
            verified = service.verify(high[0])
            payload["verify"] = {"ok": verified.ok, "code": verified.code, "message": verified.message, "details": verified.details}
            if verified.code in {"E303", "OK202"} or (verified.details or {}).get("firmware") == "RDV4":
                payload["message"] = "O aparelho foi identificado como RDV4. Compilação interrompida."
                return _finish(False, payload)
            if verified.ok:
                if "512" not in (prefs.detected_mcu or ""):
                    payload["message"] = f"O MCU informado não tem 512 KB: {prefs.detected_mcu}"
                    return _finish(False, payload)
                if prefs.detected_external_flash == "ausente":
                    payload["message"] = "A verificação ao vivo não encontrou flash SPI. Compilação interrompida."
                    return _finish(False, payload)
        else:
            previous = ROOT / "var" / "hw-version.txt"
            if previous.is_file():
                report = parse_identity(previous.read_text(encoding="utf-8", errors="replace"), exit_code=0, expected_version=env.version)
                prefs.detected_mcu = report.mcu or prefs.detected_mcu
                prefs.detected_external_flash = report.external_flash
                prefs.detected_flash_size = report.external_flash_size
                prefs.detected_standalone = report.standalone_banner
                prefs.detected_smartcard = report.smartcard
                prefs.detected_bt_addon = report.bt_addon
            payload["verify"] = {"ok": False, "message": "Nenhum Proxmark3 de confiança alta está conectado agora."}

        prefs.flash_autorizado = False
        prefs.platform_size_256 = False
        prefs.spi_flash_recusada = False
        prefs.spi_flash_confirmada = True
        prefs.save()
        config = build_config(selected.id, prefs)
        payload["config"] = config.identity()
        if config.platform != "PM3GENERIC" or config.extras != ("FLASH",) or config.platform_size:
            payload["message"] = "A configuração efetiva não é PM3GENERIC com FLASH e sem PLATFORM_SIZE."
            return _finish(False, payload)

        log_path = ROOT / "var" / "logs" / "build-LF_SAMYRUN.log"
        if log_path.is_file():
            shutil.copy2(log_path, backup_root / "build-LF_SAMYRUN.previous.log")
            log_path.unlink()
        live_log = ROOT / "var" / "audit-live.log"
        if live_log.exists():
            live_log.unlink()

        def on_log(text: str) -> None:
            with live_log.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(text)

        def on_stage(stage: str, status: str) -> None:
            print(f"STAGE {stage} | {status}", flush=True)

        compiled = service.apply(
            selected,
            high[0] if high else None,
            force_rebuild=True,
            flash_authorized=False,
            on_stage=on_stage,
            on_log=on_log,
        )
        payload["compile"] = {
            "ok": compiled.ok,
            "code": compiled.code,
            "outcome": compiled.outcome,
            "message": compiled.message,
            "details": compiled.details,
        }
        if any(token in script for script in shell.scripts for token in FORBIDDEN):
            payload["message"] = "Um script de gravação foi preparado. Resultado rejeitado."
            return _finish(False, payload)
        if not compiled.ok:
            payload["message"] = compiled.message
            payload["technical"] = compiled.technical[-4000:]
            return _finish(False, payload)

        makefile = (env.repo_root / "Makefile.platform").read_text(encoding="utf-8")
        options = cache_file.read_text(encoding="utf-8", errors="replace") if cache_file.is_file() else ""
        build_log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
        info = [
            line
            for line in build_log.splitlines()
            if line.startswith(
                ("Platform name:", "PLATFORM:", "PLATFORM_SIZE:", "Platform extras:", "Standalone mode:", "Included options:", "Firmware size:", "ERROR:")
            )
        ]
        payload["make_info"] = info[:40]
        payload["makefile_kept"] = {
            "platform": "PLATFORM=PM3GENERIC" in makefile,
            "extras": "PLATFORM_EXTRAS=FLASH" in makefile,
            "standalone": "STANDALONE=LF_SAMYRUN" in makefile,
            "led_order": "LED_ORDER=PM3EASY" in makefile,
            "size_forced": "\nPLATFORM_SIZE=" in makefile,
        }
        if parent.read_bytes() != parent_before:
            payload["message"] = "O Makefile.platform de pm3/ foi alterado."
            return _finish(False, payload)
        bootrom_after = _sha256(bootrom) if bootrom.is_file() else ""
        if bootrom_after != bootrom_before:
            saved = backup_root / "bootrom.elf"
            if saved.is_file():
                bootrom.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved, bootrom)
            elif bootrom.is_file():
                bootrom.unlink()
            payload["message"] = "O bootrom foi alterado pelo make e restaurado a partir do backup. A fullimage nova foi mantida."
            payload["bootrom_restored"] = True
            return _finish(False, payload)
        if not fullimage.is_file() or not fullimage.read_bytes().startswith(b"\x7fELF"):
            payload["message"] = "A fullimage nova não é um ELF."
            return _finish(False, payload)
        digest = _sha256(fullimage)
        if digest == fullimage_before:
            payload["message"] = "A fullimage não mudou. A compilação não gerou imagem nova."
            return _finish(False, payload)
        if env.version.encode("utf-8") not in fullimage.read_bytes():
            payload["message"] = "A fullimage não contém a versão do checkout."
            return _finish(False, payload)
        if "Proxmark3 RDV4" in build_log or "PLATFORM:          PM3RDV4" in build_log:
            payload["message"] = "O log do make anunciou PM3RDV4."
            return _finish(False, payload)
        if "PLATFORM:          PM3GENERIC" not in build_log or "Standalone mode:   LF_SAMYRUN" not in build_log:
            payload["message"] = "O log do make não confirmou PM3GENERIC e LF_SAMYRUN."
            return _finish(False, payload)
        if "Platform extras:   FLASH" not in build_log or "PLATFORM_SIZE:     512" not in build_log:
            payload["message"] = "O log do make não confirmou FLASH e PLATFORM_SIZE 512."
            return _finish(False, payload)
        if "CACHED_PLATFORM=PM3GENERIC" not in options or "WITH_STANDALONE_LF_SAMYRUN" not in options:
            payload["message"] = "O cache de opções do make não registrou PM3GENERIC e LF_SAMYRUN."
            return _finish(False, payload)
        if "-DRDV4" in options:
            payload["message"] = "O cache de opções ainda contém -DRDV4."
            return _finish(False, payload)
        source_name = Path(selected.source_file).name if selected.source_file else ""
        objects = sorted((env.repo_root / "armsrc" / "obj").glob("*.o"))
        linked = [path.name for path in objects if source_name and source_name.replace(".c", ".o") == path.name]
        text = fullimage.read_bytes()
        payload["fullimage"] = {"size": fullimage.stat().st_size, "sha256": digest}
        payload["standalone_object"] = linked
        payload["standalone_string_in_elf"] = b"SamyRun" in text or b"LF_SAMYRUN" in text
        payload["firmware_size_lines"] = [line for line in info if line.startswith("Firmware size:") or line.startswith("ERROR:")]
        payload["client_changed"] = (_sha256(client) if client.is_file() else "") != client_before
        payload["bootrom_unchanged"] = True

        before = len(shell.scripts)
        recovered = service.apply(
            selected,
            high[0] if high else None,
            force_rebuild=False,
            flash_authorized=False,
            on_stage=on_stage,
            on_log=on_log,
        )
        payload["cache_reuse"] = {
            "ok": recovered.ok,
            "outcome": recovered.outcome,
            "code": recovered.code,
            "make_again": any("make -j" in script for script in shell.scripts[before:]),
            "details": recovered.details,
        }
        if (not recovered.ok) or recovered.outcome != "cache_hit" or payload["cache_reuse"]["make_again"]:
            payload["message"] = "O cache não devolveu a imagem sem uma nova compilação."
            return _finish(False, payload)
        cached_hash = str((recovered.details or {}).get("sha256", ""))
        if cached_hash != digest or _sha256(fullimage) != digest:
            payload["message"] = "O hash recuperado do cache não confere com a fullimage compilada."
            return _finish(False, payload)
        other = build_config("HF_AVEFUL", prefs)
        foreign = context.cache.lookup(env, other, service.toolchain)
        payload["foreign_module_reused"] = foreign is not None
        if foreign is not None:
            payload["message"] = "O cache devolveu imagem de outro módulo."
            return _finish(False, payload)
        payload["message"] = "LF_SAMYRUN compilado com PM3GENERIC e FLASH, sem gravação, e recuperado do cache."
        payload["finished"] = datetime.now().isoformat(timespec="seconds")
        return _finish(True, payload)
    except Exception:
        payload["message"] = "Falha inesperada na validação."
        payload["traceback"] = traceback.format_exc()[-4000:]
        return _finish(False, payload)


if __name__ == "__main__":
    sys.exit(main())
