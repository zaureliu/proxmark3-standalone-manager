"""Diagnóstico somente leitura. Não precisa de Proxmark3 e não grava firmware."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from pm3manager.cache.store import FirmwareCache
from pm3manager.diagnostics.analyze import analyze
from pm3manager.diagnostics.commands import SAFE_COMMANDS, render_script, validate_commands
from pm3manager.diagnostics.environment import _git, git_snapshot, read_makefile
from pm3manager.diagnostics.export import export_json, export_text
from pm3manager.diagnostics.models import Observation, Origin, Severity, Verdict
from pm3manager.diagnostics.process import run_process
from pm3manager.diagnostics.sanitize import sanitize
from pm3manager.diagnostics.service import DiagnosticService, live_collect
from pm3manager.errors import SecurityError
from pm3manager.models import Compatibility
from pm3manager.preferences import Preferences
from pm3manager.proxspace.shell import ProxSpaceShell
from pm3manager.workflow.context import AppContext
from pm3manager.workflow.lock import OperationLock
from tests.fakes import VERSION, device, make_env, module

COMMIT = "dc0110c29d320e04b37ea436ee2924901407ae72"
CLIENT = f"""[ Proxmark3 ]
[ client ]
{VERSION}
Bootrom.... {VERSION}
OS......... {VERSION}
Firmware.................. PM3 GENERIC
uC: AT91SAM7S512
Embedded flash memory 512K bytes
External flash............ present
Memory size............. 2048 Kb
Architecture identifier: AT91SAM7S
Internal SRAM size: 64K
Emulator memory: 512 bytes
BigBuf_size......... 4096
Smartcard reader.......... absent
FPC USART for BT add-on... absent
Ping response received
"""


def _observation(**extra) -> Observation:
    chosen = device()
    payload = dict(
        generated_at="2026-10-27T12:00:00-03:00",
        app_version="2.0.0",
        mode="full",
        devices=[chosen],
        selected=chosen,
        port_free=True,
        client_attempted=True,
        client_output=CLIENT,
        client_exit=0,
        commands=SAFE_COMMANDS,
        env_present=True,
        proxspace_present=True,
        checkout_present=True,
        checkout_name="proxmark3-v4.23346",
        version_file=VERSION,
        version_token="9ce8a4b6c",
        essential={
            "runme64.bat": True,
            "msys2_shell.cmd": True,
            "Makefile": True,
            "Makefile.hal": True,
            "pm3": True,
        },
        toolchain_found=True,
        git_state="repo",
        git_commit=COMMIT,
        git_shallow=False,
        git_dirty=False,
        makefile_present=True,
        makefile={
            "PLATFORM": ["PM3GENERIC"],
            "LED_ORDER": ["PM3EASY"],
            "STANDALONE": ["HF_MATTYRUN"],
        },
        intended_platform="PM3GENERIC",
        intended_standalone="HF_MATTYRUN",
        intended_led_order="PM3EASY",
        module=module("HF_MATTYRUN"),
    )
    payload.update(extra)
    return Observation(**payload)


def _fact(report, key):
    return next(item for item in report.facts if item.key == key)


def _check(report, code):
    return next(item for item in report.checks if item.code == code)


def test_dispositivo_conectado_com_resposta_valida():
    report = analyze(_observation())
    assert report.verdict is Verdict.COMPATIBLE
    assert report.verdict_label == "Compatível segundo verificações disponíveis"
    assert "100%" not in report.verdict_label
    assert "100%" not in export_text(report)
    assert _fact(report, "port").value == "COM5"
    assert _fact(report, "port").origin is Origin.DETECTED
    assert _fact(report, "vidpid").value == "9AC4:4B8F"
    assert _fact(report, "firmware_version").origin is Origin.DETECTED
    assert VERSION in _fact(report, "firmware_version").value
    assert _fact(report, "bootrom_version").origin is Origin.DETECTED
    assert _fact(report, "mcu_detected").value.startswith("AT91SAM7S512")
    assert _fact(report, "mcu_detected").origin is Origin.DETECTED
    assert _fact(report, "family").value == "PM3 GENERIC"
    assert "presente" in _fact(report, "spi_detected").value
    assert _check(report, "communication").severity is Severity.PASS
    assert _check(report, "module_fit").severity is Severity.PASS
    assert report.client_attempted is True
    assert report.commands == SAFE_COMMANDS
    assert "consultivo" in report.limitations[0].lower()
    for fact in report.facts_by_origin(Origin.DETECTED):
        assert "easy" not in fact.value.casefold()


def test_dispositivo_ausente_nao_e_defeito():
    report = analyze(_observation(selected=None, devices=[], client_attempted=False, client_output="", commands=()))
    assert _fact(report, "connection").value == "Desconectado"
    assert _check(report, "disconnected").severity is Severity.INFO
    assert "defeito" in _check(report, "disconnected").message
    assert report.verdict is not Verdict.INCOMPATIBLE
    assert not report.checks_by_severity(Severity.BLOCKING)


def test_porta_ocupada_nao_forca_acesso():
    report = analyze(
        _observation(
            port_free=False,
            port_message="A porta COM5 está em uso por outro processo.",
            client_attempted=False,
            client_output="",
            commands=(),
        )
    )
    warning = _check(report, "port_busy")
    assert warning.severity is Severity.WARNING
    assert "em uso" in warning.message
    assert report.client_attempted is False
    assert report.commands == ()
    assert report.verdict is Verdict.NEEDS_CONFIRMATION
    assert _fact(report, "firmware_version").origin is not Origin.DETECTED


def test_resposta_incompleta():
    report = analyze(_observation(client_output="[ Proxmark3 ]\nresposta cortada\n"))
    assert _check(report, "communication").severity is Severity.WARNING
    assert report.verdict is Verdict.INSUFFICIENT
    assert _fact(report, "mcu_detected").origin is not Origin.DETECTED


def test_firmware_desconhecido_nao_e_incompativel():
    text = """[ Proxmark3 ]
OS......... firmware fora do catalogo
uC: AT91SAM7S512
Embedded flash memory 512K bytes
Bootrom.... sem familia nomeada
"""
    report = analyze(_observation(client_output=text, version_file=""))
    assert _check(report, "firmware_unknown").severity is Severity.UNKNOWN
    assert "incompatível" in _check(report, "firmware_unknown").message
    assert report.verdict is not Verdict.INCOMPATIBLE
    assert report.verdict is Verdict.PARTIAL


def test_bootrom_ausente_nao_e_falha_do_aparelho():
    text = CLIENT.replace(f"Bootrom.... {VERSION}\n", "")
    report = analyze(_observation(client_output=text))
    missing = _check(report, "bootrom_missing")
    assert missing.severity is Severity.UNKNOWN
    assert "falha" in missing.message
    assert _fact(report, "bootrom_version").value == "Não identificado"
    assert report.verdict is not Verdict.INCOMPATIBLE


def test_timeout_nao_promove_texto_parcial():
    report = analyze(
        _observation(
            client_timed_out=True,
            client_output=f"OS......... {VERSION}\nUnique ID...... 0xAABBCCDDEEFF\n",
            client_error="timeout",
        )
    )
    assert report.timed_out is True
    assert _check(report, "timeout").severity is Severity.WARNING
    assert _fact(report, "firmware_version").origin is Origin.UNVERIFIED
    assert _fact(report, "firmware_version").value == "Não verificado"
    assert report.technical == ""
    assert "AABBCCDDEEFF" not in export_json(report)
    assert report.verdict is Verdict.INSUFFICIENT


def test_desconexao_durante_a_leitura():
    report = analyze(
        _observation(client_output="Could not find Proxmark3 on COM5\n", client_exit=1)
    )
    warning = _check(report, "disconnected_during_read")
    assert warning.severity is Severity.WARNING
    assert "defeituoso" in warning.message
    assert report.verdict is not Verdict.INCOMPATIBLE
    assert _fact(report, "mcu_detected").origin is not Origin.DETECTED


def test_cancelamento():
    report = analyze(_observation(client_cancelled=True, client_output=CLIENT))
    assert report.cancelled is True
    assert _check(report, "cancelled").severity is Severity.INFO
    assert _fact(report, "firmware_version").origin is Origin.UNVERIFIED
    assert report.technical == ""
    assert report.verdict is Verdict.INSUFFICIENT


def test_execucao_simultanea_e_lock_de_outra_operacao():
    lock = OperationLock()
    assert lock.acquire("apply")
    refused = DiagnosticService(lock, lambda mode, cancel: (_ for _ in ()).throw(AssertionError("coleta"))).run()
    assert _check(refused, "ocupado").severity is Severity.WARNING
    assert "interrompidas" in _check(refused, "ocupado").message
    assert lock.owner == "apply"
    lock.release()

    started = threading.Event()
    release = threading.Event()

    def collect(mode, cancel):
        started.set()
        assert release.wait(2)
        return _observation(mode=mode)

    service = DiagnosticService(lock, collect)
    holder = []

    def run():
        holder.append(service.run("refresh"))

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(2)
    blocked = service.run("full")
    assert any(item.code == "ocupado" for item in blocked.checks)
    assert lock.owner == "diagnostics"
    release.set()
    thread.join(2)
    assert not thread.is_alive()
    assert lock.locked is False
    assert holder and holder[0].verdict is Verdict.COMPATIBLE


def test_plataforma_divergente_nao_altera_o_arquivo(tmp_path):
    env = make_env(tmp_path)
    platform = env.repo_root / "Makefile.platform"
    platform.write_text("PLATFORM=PM3RDV4\nSTANDALONE=HF_MATTYRUN\n", encoding="utf-8")
    before = platform.read_bytes()
    present, values = read_makefile(env.repo_root)
    assert present is True
    assert values["PLATFORM"] == ["PM3RDV4"]
    assert platform.read_bytes() == before
    report = analyze(
        _observation(makefile_present=True, makefile=values, intended_platform="PM3GENERIC")
    )
    warning = _check(report, "platform_diverge")
    assert warning.severity is Severity.WARNING
    assert "não foi alterado" in warning.message
    assert _fact(report, "file_platform").origin is Origin.CONFIGURED
    assert _fact(report, "intended_platform").origin is Origin.CONFIGURED
    assert platform.read_bytes() == before


def test_requisito_de_spi_desconhecido_e_ausente():
    unknown_text = CLIENT.replace("External flash............ present\n", "")
    unknown = analyze(
        _observation(
            client_output=unknown_text,
            module=module("HF_ST25_TEAROFF", Compatibility.REQUIRES_FLASH),
        )
    )
    assert _check(unknown, "spi_unknown").severity is Severity.UNKNOWN
    assert unknown.verdict is Verdict.NEEDS_CONFIRMATION
    absent = CLIENT.replace("External flash............ present", "External flash............ absent")
    blocked = analyze(
        _observation(
            client_output=absent,
            module=module("HF_ST25_TEAROFF", Compatibility.REQUIRES_FLASH),
        )
    )
    assert _check(blocked, "spi_absent").severity is Severity.BLOCKING
    assert blocked.verdict is Verdict.INCOMPATIBLE


def test_proxspace_ausente():
    report = analyze(
        _observation(
            env_present=False,
            proxspace_present=False,
            checkout_present=False,
            essential={},
            toolchain_found=None,
            git_state="indisponivel",
            makefile_present=None,
            makefile={},
        )
    )
    assert _fact(report, "proxspace").origin is Origin.UNAVAILABLE
    assert _check(report, "proxspace_missing").severity is Severity.WARNING
    assert "defeituoso" in _check(report, "proxspace_missing").message
    assert report.verdict is not Verdict.INCOMPATIBLE


def test_checkout_nao_git_e_raso(tmp_path):
    missing = analyze(_observation(git_state="not_repo", git_commit="", git_shallow=None, git_dirty=None))
    assert _check(missing, "not_git").severity is Severity.INFO
    assert _fact(missing, "git_commit").origin is Origin.UNAVAILABLE
    shallow = analyze(_observation(git_shallow=True))
    assert _check(shallow, "shallow").severity is Severity.INFO
    assert "não foi baixado" in _check(shallow, "shallow").message

    calls = []

    def runner(repo, args):
        calls.append(args)
        if args == ("rev-parse", "--is-inside-work-tree"):
            return 0, "true\n", ""
        if args == ("rev-parse", "HEAD"):
            return 0, COMMIT + "\n", ""
        if args == ("rev-parse", "--is-shallow-repository"):
            return 0, "true\n", ""
        if args == ("status", "--porcelain"):
            return 0, " M armsrc/appmain.c\n", ""
        raise AssertionError(args)

    snapshot = git_snapshot(tmp_path, runner)
    assert snapshot["git_state"] == "repo"
    assert snapshot["git_shallow"] is True
    assert snapshot["git_dirty"] is True
    assert snapshot["git_dirty_count"] == 1
    assert all(args in {
        ("rev-parse", "--is-inside-work-tree"),
        ("rev-parse", "HEAD"),
        ("rev-parse", "--is-shallow-repository"),
        ("status", "--porcelain"),
    } for args in calls)
    with pytest.raises(OSError):
        _git(tmp_path, ("fetch", "origin"))
    with pytest.raises(OSError):
        _git(tmp_path, ("checkout", "main"))


def test_valor_configurado_nao_vira_deteccao():
    report = analyze(
        _observation(
            mode="refresh",
            client_attempted=False,
            client_output="",
            commands=(),
            prefs_mcu="AT91SAM7S512",
            prefs_firmware_kind="PM3 GENERIC",
            prefs_external_flash="presente",
            intended_led_order="PM3EASY",
        )
    )
    configured = _fact(report, "prefs_mcu")
    assert configured.origin is Origin.CONFIGURED
    assert configured.value == "AT91SAM7S512"
    assert _fact(report, "mcu_detected").origin is Origin.UNVERIFIED
    assert _fact(report, "mcu_detected").value == "Não verificado"
    support = _fact(report, "compile_mcu_support")
    assert support.origin is Origin.DOCUMENTED
    assert "PM3EASY" in support.value
    assert "não identifica" in support.justification.casefold()
    detected = {item.value for item in report.facts_by_origin(Origin.DETECTED)}
    assert "AT91SAM7S512" not in detected
    assert not any(value.casefold() == "easy" or value.casefold().endswith(" easy") for value in detected)


def test_exportacao_sanitizada():
    serial = "USB-SERIAL-998877"
    chosen = device(serial=serial)
    raw = "\n".join(
        [
            CLIENT,
            r"C:\Users\Exemplo\AppData\Local\secret",
            "pessoa@example.com",
            "token=abc123secret",
            "password: hunter2",
            "bearer abcdefghijklmnop",
            "Unique ID...... 0xAABBCCDDEEFF",
            f"serial number: {serial}",
            "UID: DEADBEEFCAFE",
            "dump: 00112233445566778899",
        ]
    )
    report = analyze(_observation(selected=chosen, devices=[chosen], client_output=raw))
    exported = export_json(report) + export_text(report)
    for secret in (
        "Exemplo",
        "pessoa@example.com",
        "abc123secret",
        "hunter2",
        "abcdefghijklmnop",
        "AABBCCDDEEFF",
        serial,
        "DEADBEEFCAFE",
        "00112233445566778899",
    ):
        assert secret not in exported
    assert "[perfil]" in exported
    assert "[email]" in exported
    assert "[redigido]" in exported
    assert serial not in report.context_key
    assert "consultivo" in exported.lower()
    assert "certifica" in exported.lower()
    payload = json.loads(export_json(report))
    assert set(payload["checks"]) == {
        "informacoes",
        "verificacoes_aprovadas",
        "avisos",
        "problemas_impeditivos",
        "desconhecidos",
    }
    assert all(item["origin"] for item in payload["facts"])


def test_diagnostico_nao_grava_firmware(tmp_path):
    script = render_script("/pm3/proxmark3-test", "COM5")
    lowered = script.lower()
    assert "./pm3 -p com5 -c 'hw version'" in lowered
    assert "hw status" in lowered
    assert "hw ping" in lowered
    for forbidden in ("pm3-flash", "hw bootloader", "hw reset", "hw readmem", "hw tearoff", " lf ", " hf "):
        assert forbidden not in lowered
    with pytest.raises(SecurityError):
        validate_commands(("hw reset",))
    with pytest.raises(SecurityError):
        validate_commands(("hw version", "lf search"))
    root = Path(__file__).resolve().parents[1] / "pm3manager" / "diagnostics"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "pm3-flash-all" not in text
        assert "pm3-flash-fullimage" not in text
        assert "subprocess.run([\"git\", \"pull\"" not in text
        assert ".checkout(" not in text
    assert sanitize("UID: DEADBEEF") == "UID=[redigido]"
    assert not list((tmp_path / "cache").glob("**/*")) if (tmp_path / "cache").exists() else True


def test_timeout_e_cancelamento_encerram_o_processo(tmp_path):
    started = time.monotonic()
    expired = run_process(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=str(tmp_path),
        timeout=0.8,
        cancel=threading.Event(),
    )
    assert expired.timed_out is True
    assert expired.cancelled is False
    assert time.monotonic() - started < 8
    cancel = threading.Event()
    cancel.set()
    stopped = run_process(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=str(tmp_path),
        timeout=3,
        cancel=cancel,
    )
    assert stopped.cancelled is True
    assert stopped.timed_out is False


def test_coleta_nao_atualiza_preferencia_nem_cache(tmp_path, monkeypatch):
    env = make_env(tmp_path)
    platform = env.repo_root / "Makefile.platform"
    platform.write_text("PLATFORM=PM3GENERIC\n", encoding="utf-8")
    before = platform.read_bytes()
    prefs = Preferences()
    prefs.detected_mcu = "AT91SAM7S256"
    prefs.detected_firmware_kind = "PM3 GENERIC"
    saved = []
    prefs.save = lambda: saved.append("save")
    cache = FirmwareCache(tmp_path / "cache")
    before_cache = sorted(path.name for path in cache.root.iterdir())
    monkeypatch.setattr("pm3manager.diagnostics.service.detect_devices", lambda: [])
    monkeypatch.setattr(
        "pm3manager.diagnostics.service.port_is_free",
        lambda port: (False, f"A porta {port} está em uso por outro processo."),
    )
    monkeypatch.setattr(
        "pm3manager.diagnostics.service.run_client",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cliente")),
    )
    context = AppContext(
        env=env,
        prefs=prefs,
        modules=[],
        shell=ProxSpaceShell(env, tmp_path / "work"),
        cache=cache,
        lock=OperationLock(),
    )
    collect = live_collect(context, device(), module("HF_MATTYRUN"), tmp_path / "work")
    busy = collect("full", threading.Event())
    assert busy.client_attempted is False
    assert busy.commands == ()
    assert "em uso" in busy.client_error
    refresh = collect("refresh", threading.Event())
    assert refresh.client_attempted is False
    assert refresh.prefs_mcu == "AT91SAM7S256"
    assert prefs.detected_mcu == "AT91SAM7S256"
    assert saved == []
    assert platform.read_bytes() == before
    assert sorted(path.name for path in cache.root.iterdir()) == before_cache

    service = DiagnosticService(context.lock, collect)
    failed = service.run("full")
    assert failed.client_attempted is False
    assert context.lock.locked is False

    def broken(mode, cancel):
        raise RuntimeError("falha de coleta")

    broken_report = DiagnosticService(OperationLock(), broken).run("refresh")
    blob = " ".join(item.justification for item in broken_report.facts)
    assert "falha de coleta" in blob
    assert context.lock.locked is False


def test_rdv4_e_tamanho_divergente_continuam_bloqueados():
    rdv4 = CLIENT.replace("PM3 GENERIC", "RDV4")
    device_report = analyze(_observation(client_output=rdv4))
    assert device_report.verdict is Verdict.INCOMPATIBLE
    assert _check(device_report, "rdv4_device").severity is Severity.BLOCKING
    assert "defeituoso" in _check(device_report, "rdv4_device").message
    exclusive = analyze(_observation(module=module("HF_REBLAY", Compatibility.INCOMPATIBLE)))
    assert exclusive.verdict is Verdict.INCOMPATIBLE
    assert _check(exclusive, "module_incompatible").severity is Severity.BLOCKING
    assert "não libera" in _check(exclusive, "module_incompatible").message
    sized = analyze(_observation(intended_platform_size="256"))
    assert sized.verdict is Verdict.INCOMPATIBLE
    assert _check(sized, "size_conflict").severity is Severity.BLOCKING
