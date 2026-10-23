import os
from pathlib import Path

import pytest

from pm3manager.app import self_check
from pm3manager.install.shortcut import SHORTCUT_NAME, create_shortcut, desktop_directory, read_shortcut
from pm3manager.messages import Msg
from pm3manager.models import OperationResult
from pm3manager.paths import project_root
from pm3manager.proxspace.locator import locate
from pm3manager.proxspace.shell import ProxSpaceShell
from pm3manager.workflow.context import AppContext
from tests.support import require_local_proxspace


def test_shell_real_do_proxspace(tmp_path):
    require_local_proxspace()
    env = locate()
    shell = ProxSpaceShell(env, tmp_path)
    result = shell.run_script(
        """#!/bin/bash
set -eu
echo INTEGRATION_OK
cd /pm3/proxmark3-v4.23346
test -f Makefile
test -f pm3-flash-fullimage
test -f client/proxmark3.exe
echo REPO_OK
""",
        timeout=60,
    )
    assert result.exit_code == 0, result.output
    assert "INTEGRATION_OK" in result.output
    assert "REPO_OK" in result.output


def test_atalho_em_pasta_temporaria(tmp_path):
    exe = tmp_path / "Proxmark3StandaloneManager.exe"
    exe.write_bytes(b"MZ")
    lnk = tmp_path / SHORTCUT_NAME
    create_shortcut(exe, lnk, tmp_path, exe)
    info = read_shortcut(lnk)
    assert Path(info["TARGET"]).resolve() == exe.resolve()
    assert Path(info["WORKDIR"]).resolve() == tmp_path.resolve()
    assert info["STYLE"] == "1"
    desktop = desktop_directory()
    assert desktop.is_dir()
    assert "Usuario" not in str(desktop)


def test_autoverificacao_real():
    require_local_proxspace()
    operational = project_root() / "var" / "logs" / "app.log"
    before = operational.read_bytes()
    assert self_check() == 0
    assert operational.read_bytes() == before
    from pm3manager.paths import data_dir

    payload_path = data_dir() / "self-check.json"
    assert payload_path.is_file()
    text = payload_path.read_text(encoding="utf-8")
    assert "v4.23346" in text
    from pm3manager.preferences import Preferences

    stored = "true" if Preferences.load().flash_autorizado else "false"
    assert f'"flash_authorized": {stored}' in text


def test_janela_principal(qapp, tmp_path, monkeypatch):
    require_local_proxspace()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("pm3manager.preferences.data_dir", lambda: tmp_path)
    monkeypatch.setattr("pm3manager.paths.data_dir", lambda: tmp_path)
    monkeypatch.setattr("pm3manager.workflow.context.data_dir", lambda: tmp_path)
    context = AppContext.load()
    from pm3manager.ui.main_window import MainWindow

    window = MainWindow(context)
    try:
        assert window.apply_button.text() == "Aplicar módulo"
        assert window.rebuild_button.text() == "Recompilar"
        assert window.verify_button.text() == "Verificar dispositivo"
        assert window.client_button.text() == "Abrir cliente Proxmark3"
        assert window.logs_button.text() == "Visualizar logs"
        assert window.windowTitle() == "Proxmark3 Standalone Manager"
        assert context.prefs.flash_autorizado is False
        assert "Validação parcial" in window.log_legend.text()
        assert "Validação concluída" in window.log_legend.text()
        assert "Evento de teste" in window.log_legend.text()
        assert "Erro operacional" in window.log_legend.text()
        assert "Easy" not in window.summary_label.text()
        assert "Easy" not in window.confirm_uncertain.text()
        assert window.size_check.isEnabled() is False
        window.search_box.setText("SAMY")
        ids = []
        for row in range(window.module_table.rowCount()):
            ids.append(window.module_table.item(row, 0).text())
        assert "LF_SAMYRUN" in ids
        window.search_box.setText("")
        window.category_combo.setCurrentText("High Frequency (HF)")
        hf_ids = [window.module_table.item(row, 0).text() for row in range(window.module_table.rowCount())]
        assert "HF_REBLAY" in hf_ids
        assert "LF_SAMYRUN" not in hf_ids
        for row, module_id in enumerate(hf_ids):
            if module_id == "HF_REBLAY":
                window.module_table.selectRow(row)
                break
        assert window.apply_button.isEnabled() is False
        assert "incompatível" in window.block_reason.text().lower()
        qapp.processEvents()
    finally:
        window._poll.stop()
        window.close()


def test_painel_nao_trata_validacao_parcial_como_sucesso(qapp, tmp_path, monkeypatch):
    require_local_proxspace()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr("pm3manager.preferences.data_dir", lambda: tmp_path)
    monkeypatch.setattr("pm3manager.paths.data_dir", lambda: tmp_path)
    monkeypatch.setattr("pm3manager.workflow.context.data_dir", lambda: tmp_path)
    monkeypatch.setattr("pm3manager.ui.main_window.environment_name", lambda: "producao")
    import pm3manager.ui.main_window as mw

    monkeypatch.setattr(mw.QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(mw.QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *args, **kwargs: None)
    context = AppContext.load()
    window = mw.MainWindow(context)
    try:
        partial = OperationResult(
            True,
            "OK210",
            Msg.FLASH_PARTIAL_CHECK,
            "flash_partial_validation",
            technical="detalhe técnico da comunicação",
            stage="Validação parcial",
            details={
                "firmware": "PM3 GENERIC",
                "standalone": "LF HID26 standalone - aka SamyRun (Samy Kamkar)",
                "etapa_modulo": "nao_confirmado",
                "validacao": "parcial",
            },
        )
        window._finished(partial)
        assert window.status_pill.text() == "Validação parcial"
        assert window.progress.value() == 0
        shown = window.log_view.toPlainText()
        assert "Validação parcial" in shown
        assert "OK210" in shown
        assert "Detalhe técnico" in shown
        assert "Evento de teste" not in shown
        assert "não confirmado" in window.device_labels["firmware"].text()
        failed = OperationResult(
            False,
            "E300",
            Msg.FLASH_UNCONFIRMED,
            "flash_unconfirmed",
            stage="Gravação não confirmada",
        )
        window._finished(failed)
        assert window.status_pill.text() == "Erro"
        assert "Erro operacional" in window.log_view.toPlainText()
        assert window.status_pill.text() != "Pronto"
    finally:
        window._poll.stop()
        window.close()
