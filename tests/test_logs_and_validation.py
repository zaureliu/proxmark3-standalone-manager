"""Isolamento dos logs e limites da validação de gravação."""

import json
import logging

import pytest

from pm3manager.cache.store import FirmwareCache
from pm3manager.logging_setup import (
    LogIsolationError,
    audit,
    latest_log_file,
    log,
    operational_log_dir,
    reset_logging,
    setup_logging,
)
from pm3manager.messages import Msg
from pm3manager.models import Compatibility, OperationResult
from pm3manager.paths import project_root
from pm3manager.preferences import Preferences
from pm3manager.ui.presentation import present_result
from pm3manager.workflow.lock import OperationLock
from pm3manager.workflow.service import ManagerService
from tests.fakes import VERSION, FakeShell, device, make_env, module
from tests.test_workflow import _service


ARCHIVE_NAME = "app-historico-anterior-a-correcao-20261023.log"
OPERATIONAL = project_root() / "var" / "logs" / "app.log"


def _custom(tmp_path, shell, detect):
    return ManagerService(
        make_env(tmp_path),
        Preferences(),
        shell,
        FirmwareCache(tmp_path / "cache"),
        OperationLock(),
        detect=detect,
        port_free=lambda port: (True, ""),
        sleeper=lambda seconds: None,
    )


def _events(tmp_path) -> list[dict]:
    path = tmp_path / "logs" / "operations.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_historico_anterior_foi_preservado_fora_do_log_ativo():
    archive = project_root() / "var" / "logs" / ARCHIVE_NAME
    if not archive.is_file():
        pytest.skip("Histórico operacional local ausente; ele não faz parte do repositório.")
    assert archive.is_file()
    old = archive.read_text(encoding="utf-8", errors="replace")
    assert "falha simulada" in old
    assert "[E200]" in old or "code=E200" in old
    current = OPERATIONAL.read_text(encoding="utf-8", errors="replace")
    assert ARCHIVE_NAME in current
    assert "falha simulada" not in current
    assert "Could not find Proxmark3" not in current


def test_handler_preso_nao_grava_no_log_operacional(tmp_path):
    before = OPERATIONAL.read_bytes()
    logger = logging.getLogger("pm3manager")
    rogue = logging.FileHandler(OPERATIONAL, encoding="utf-8")
    logger.addHandler(rogue)
    try:
        log(
            logging.ERROR,
            "E200",
            "Falha ao compilar firmware.",
            "error: falha simulada",
            component="workflow",
            operation="op-isolamento",
            module="LF_SAMYRUN",
            stage="Compilação",
            result="error",
        )
    finally:
        if rogue in logger.handlers:
            logger.removeHandler(rogue)
        rogue.close()
    assert OPERATIONAL.read_bytes() == before
    text = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "code=E200" in text
    assert "falha simulada" in text
    assert "env=teste" in text
    assert "module=LF_SAMYRUN" in text
    assert "operation=op-isolamento" in text


def test_diretorio_operacional_explicito_e_recusado(monkeypatch):
    before = OPERATIONAL.read_bytes()
    monkeypatch.setenv("PM3MANAGER_LOG_DIR", str(operational_log_dir()))
    with pytest.raises(LogIsolationError):
        setup_logging()
    assert OPERATIONAL.read_bytes() == before


def test_sem_diretorio_explicito_nao_cai_no_log_operacional(monkeypatch):
    before = OPERATIONAL.read_bytes()
    monkeypatch.delenv("PM3MANAGER_LOG_DIR", raising=False)
    log(
        logging.ERROR,
        "E201",
        "Falha ao compilar firmware.",
        "elf ausente durante teste",
        component="workflow",
        operation="op-fallback",
        module="LF_SAMYRUN",
        stage="Validando artefatos",
        result="error",
    )
    assert OPERATIONAL.read_bytes() == before
    written = latest_log_file().resolve()
    assert written != OPERATIONAL.resolve()
    assert operational_log_dir() not in written.parents
    text = written.read_text(encoding="utf-8")
    assert "code=E201" in text
    assert "env=teste" in text
    assert "elf ausente durante teste" in text


def test_falhas_simuladas_ficam_so_no_log_de_teste(isolated_data, tmp_path):
    before = OPERATIONAL.read_bytes()
    scenarios = []

    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.fail_build = True
    scenarios.append(_service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=True))

    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.omit_elf = True
    scenarios.append(_service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=True))

    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.banner_platform = "PM3RDV4"
    scenarios.append(_service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=True))

    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.fail_flash = True
    scenarios.append(_service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=True))

    shell = FakeShell(make_env(tmp_path).repo_root)
    scenarios.append(
        _service(tmp_path, shell)[0].apply(
            module("HF_REBLAY", Compatibility.INCOMPATIBLE),
            device(),
            force_rebuild=True,
            flash_authorized=True,
        )
    )

    shell = FakeShell(make_env(tmp_path).repo_root)
    service, _, _ = _service(tmp_path, shell)
    assert service.lock.acquire("teste")
    scenarios.append(service.apply(module(), device(), force_rebuild=False, flash_authorized=False))
    service.lock.release()

    shell = FakeShell(make_env(tmp_path).repo_root)
    service, _, _ = _service(tmp_path, shell, devices=[])
    scenarios.append(service.apply(module(), None, force_rebuild=True, flash_authorized=True))

    codes = [item.code for item in scenarios]
    assert codes == ["E200", "E201", "E202", "E300", "E104", "E010", "E100"]
    text = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    recorded = _events(tmp_path)
    for code in codes:
        assert f"code={code}" in text
        assert any(event["code"] == code and event["environment"] == "teste" for event in recorded)
    assert "ERROR" in text
    assert "WARNING" in text
    assert OPERATIONAL.read_bytes() == before
    assert "falha simulada" not in OPERATIONAL.read_text(encoding="utf-8")


def test_erro_real_nao_e_ocultado(isolated_data, tmp_path, monkeypatch):
    monkeypatch.setenv("PM3MANAGER_ENV", "producao")
    monkeypatch.setenv("PM3MANAGER_LOG_DIR", str(tmp_path / "logs"))
    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.fail_build = True
    result = _service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=False)
    assert result.code == "E200"
    assert not result.ok
    text = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "ERROR" in text
    assert "code=E200" in text
    assert "env=producao" in text
    assert "falha simulada" in text
    assert "component=workflow" in text
    event = _events(tmp_path)[-1]
    assert event["severity"] == "ERROR"
    assert event["environment"] == "producao"
    assert event["code"] == "E200"
    assert event["module"] == "LF_SAMYRUN"
    assert event["ok"] is False


def test_validacao_parcial_nao_confirma_modulo(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.hw_output = (
        "[ Proxmark3 ]\n"
        "Firmware.................. PM3 GENERIC\n"
        f"{VERSION}\n"
        "[#] Installed standalone mode\n"
        "[#] LF HID26 standalone - aka SamyRun (Samy Kamkar)\n"
    )
    result = _service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert result.ok
    assert result.code == "OK210"
    assert result.outcome == "flash_partial_validation"
    assert result.message.startswith("Validação parcial")
    assert Msg.FLASH_VALIDATED not in result.message
    assert "SamyRun" in result.message
    assert "não confirma o módulo compilado" in result.message
    assert result.details["etapa_comando"] == "concluida"
    assert result.details["etapa_all_done"] == "confirmada"
    assert result.details["etapa_reconexao"] == "confirmada"
    assert result.details["etapa_comunicacao"] == "confirmada"
    assert result.details["etapa_versao"] == "confere"
    assert result.details["etapa_plataforma"] == "PM3 GENERIC"
    assert result.details["etapa_modulo"] == "nao_confirmado"
    assert result.details["etapa_laboratorio"] == "nao_realizado"
    assert result.details["validacao"] == "parcial"
    assert result.details["module"] == "LF_SAMYRUN"
    event = _events(tmp_path)[-1]
    assert event["result"] == "flash_partial_validation"
    assert event["severity"] == "WARNING"
    assert event["environment"] == "teste"
    assert event["stage"] == "Validação parcial"
    view = present_result(result, environment="producao")
    assert view.status == "Validação parcial"
    assert view.dialog == "warning"
    assert view.pending
    assert view.label == "Validação parcial"
    assert "Evento de teste" not in view.label
    tested = present_result(result, environment="teste")
    assert tested.label.startswith("Evento de teste")


def test_reconexao_sem_banner_continua_parcial(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    result = _service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert result.code == "OK210"
    assert "não informaram o modo Standalone" in result.message
    assert result.details["standalone"] == ""
    assert result.details["etapa_modulo"] == "nao_confirmado"


def test_falha_de_flash_nao_vira_sucesso_com_dispositivo_presente(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.fail_flash = True
    result = _service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert result.code == "E300"
    assert result.outcome == "flash_unconfirmed"
    assert not result.ok
    assert result.details["etapa_reconexao"] == "nao_confirmada"
    assert result.details["validacao"] == "nao_concluida"
    assert "reconexão posterior não comprova" in result.message

    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.flash_exit = 0
    shell.flash_output = "writing image\n"
    missed = _service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert missed.code == "E300"
    assert missed.outcome == "flash_unconfirmed"

    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.flash_exit = 1
    shell.flash_output = "All done\n"
    failed_exit = _service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert failed_exit.code == "E300"


def test_all_done_sem_reconexao_nao_valida(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    calls = {"n": 0}

    def detect():
        calls["n"] += 1
        if calls["n"] <= 2:
            return [device()]
        return []

    result = _custom(tmp_path, shell, detect).apply(
        module(),
        device(),
        force_rebuild=True,
        flash_authorized=True,
    )
    assert result.code == "E301"
    assert result.outcome == "flash_no_reconnect"
    assert not result.ok
    assert "não reconectou" in result.message
    assert result.details["etapa_all_done"] == "confirmada"
    assert result.details["etapa_reconexao"] == "nao_confirmada"
    assert result.details["etapa_modulo"] == "nao_confirmado"
    view = present_result(result, environment="producao")
    assert view.status == "Erro"
    assert view.kind == "erro"


def test_comunicacao_ou_versao_incompletas_nao_sao_ok210(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.hw_exit = 1
    shell.hw_output = "Could not find Proxmark3\n"
    silent = _service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert silent.code == "E301"
    assert silent.outcome == "flash_no_communication"
    assert silent.details["etapa_reconexao"] == "confirmada"
    assert silent.details["etapa_comunicacao"] == "falhou"

    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.hw_output = "[ Proxmark3 ]\nFirmware.................. PM3 GENERIC\nversao diferente\n"
    mismatch = _service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert mismatch.code == "E301"
    assert mismatch.outcome == "flash_version_mismatch"
    assert mismatch.details["etapa_versao"] == "nao_confere"
    assert mismatch.details["etapa_modulo"] == "nao_confirmado"


def test_concorrencia_registrada_como_aviso(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    service, _, _ = _service(tmp_path, shell)
    assert service.lock.acquire("ocupado")
    result = service.apply(module(), device(), force_rebuild=False, flash_authorized=False)
    service.lock.release()
    assert result.code == "E010"
    assert result.stage == "concorrencia"
    text = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "WARNING" in text
    assert "code=E010" in text
    assert "module=LF_SAMYRUN" in text
    event = _events(tmp_path)[-1]
    assert event["severity"] == "WARNING"
    assert event["operation"].startswith("apply-")
    assert event["component"] == "workflow"
    view = present_result(result, environment="producao")
    assert view.status == "Aviso"
    assert view.dialog == "warning"


def test_persistencia_dos_campos(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    result = _service(tmp_path, shell)[0].apply(module(), device(), force_rebuild=True, flash_authorized=False)
    assert result.code == "OK100"
    text = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "env=teste" in text
    assert "component=workflow" in text
    assert "code=OK100" in text
    assert "module=LF_SAMYRUN" in text
    assert "stage=" in text
    assert "result=" in text
    event = _events(tmp_path)[-1]
    for key in (
        "at",
        "environment",
        "severity",
        "code",
        "component",
        "operation",
        "module",
        "stage",
        "result",
        "message",
    ):
        assert event[key]
    assert event["environment"] == "teste"
    assert event["severity"] == "INFO"
    reset_logging()
    again = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert again == text
    reread = _events(tmp_path)
    assert reread[-1]["operation"] == event["operation"]


def test_redige_usuario_e_identificadores(tmp_path):
    technical = r"C:\Users\Exemplo\AppData\proxmark Unique ID: DEADBEEF serial number: SECRET porta COM3"
    log(
        logging.ERROR,
        "E103",
        "Erro de comunicação.",
        technical,
        component="workflow",
        operation="op-redact",
        module="LF_SAMYRUN",
        stage="verificacao",
        result="comm_error",
    )
    audit(
        {
            "severity": "ERROR",
            "code": "E103",
            "component": "workflow",
            "operation": "op-redact",
            "module": "LF_SAMYRUN",
            "stage": "verificacao",
            "result": "comm_error",
            "message": "Erro de comunicação.",
            "technical": technical,
            "details": {"porta": "COM3"},
        }
    )
    text = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    stored = _events(tmp_path)[-1]
    assert "Exemplo" not in text
    assert "Exemplo" not in stored["technical"]
    assert "<usuario>" in text
    assert "DEADBEEF" not in text
    assert "SECRET" not in text
    assert "<oculto>" in text
    assert "COM3" in text
    assert stored["details"]["porta"] == "COM3"


def test_ok200_so_na_apresentacao_sintetica():
    synthetic = OperationResult(True, "OK200", Msg.FLASH_VALIDATED, "flashed_validated", stage="Validado")
    view = present_result(synthetic, environment="producao")
    assert view.status == "Validação concluída"
    assert view.pending is False
    partial = present_result(
        OperationResult(True, "OK210", Msg.FLASH_PARTIAL_CHECK, "flash_partial_validation"),
        environment="producao",
    )
    assert partial.status != view.status
    critical = present_result(
        OperationResult(False, "E400", "Falha inesperada.", "error"),
        environment="producao",
    )
    assert critical.status == "Falha crítica"
    assert critical.dialog == "critical"
