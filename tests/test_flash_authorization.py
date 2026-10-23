"""A autorização de gravação vale só para a operação confirmada e não volta do disco."""

from __future__ import annotations

import json

from PySide6.QtWidgets import QLabel, QMessageBox

from pm3manager.cache.store import FirmwareCache
from pm3manager.messages import Msg
from pm3manager.models import OperationResult
from pm3manager.preferences import Preferences
from pm3manager.proxspace.shell import ProxSpaceShell
from pm3manager.workflow.context import AppContext
from pm3manager.workflow.lock import OperationLock
from tests.fakes import make_env, module


class _Signal:
    def __init__(self) -> None:
        self._slots = []

    def connect(self, slot) -> None:
        self._slots.append(slot)

    def emit(self, *args) -> None:
        for slot in list(self._slots):
            slot(*args)


class _InlineWorker:
    def __init__(self, action) -> None:
        self._action = action
        self.log_ready = _Signal()
        self.stage_changed = _Signal()
        self.completed = _Signal()

    def start(self) -> None:
        result = self._action(
            on_log=self.log_ready.emit,
            on_stage=self.stage_changed.emit,
        )
        self.completed.emit(result)


def _window(qapp, tmp_path, monkeypatch, questions):
    os_env = tmp_path / "prefs"
    os_env.mkdir()
    monkeypatch.setattr("pm3manager.preferences.data_dir", lambda: os_env)
    monkeypatch.setattr("pm3manager.paths.data_dir", lambda: os_env)
    monkeypatch.setattr("pm3manager.workflow.service.data_dir", lambda: os_env)
    monkeypatch.setattr("pm3manager.ui.main_window.detect_devices", lambda: [])
    raw = {
        "last_module_id": "HF_MATTYRUN",
        "flash_autorizado": True,
        "spi_flash_confirmada": True,
        "detected_mcu": "AT91SAM7S512 512K bytes",
        "nota_local": "preservar",
    }
    (os_env / "preferences.json").write_text(json.dumps(raw), encoding="utf-8")
    loaded = Preferences.load()
    env = make_env(tmp_path)
    context = AppContext(
        env=env,
        prefs=loaded,
        modules=[module("HF_MATTYRUN")],
        shell=ProxSpaceShell(env, tmp_path / "work"),
        cache=FirmwareCache(tmp_path / "cache"),
        lock=OperationLock(),
    )
    import pm3manager.ui.main_window as mw

    monkeypatch.setattr(mw.QMessageBox, "question", lambda *args, **kwargs: questions.append(args) or QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(mw.QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(mw, "ServiceWorker", _InlineWorker)
    monkeypatch.setattr(mw.QTimer, "singleShot", lambda *args, **kwargs: None)
    window = mw.MainWindow(context)
    window._poll.stop()
    return window, os_env, loaded


def test_carregar_apaga_autorizacao_e_preserva_o_resto(isolated_data):
    path = isolated_data / "preferences.json"
    path.write_text(
        json.dumps(
            {
                "last_module_id": "HF_MATTYRUN",
                "flash_autorizado": True,
                "spi_flash_confirmada": True,
                "detected_mcu": "AT91SAM7S512 512K bytes",
                "nota_local": "nao-apagar",
            }
        ),
        encoding="utf-8",
    )
    loaded = Preferences.load()
    assert loaded.flash_autorizado is False
    assert loaded.last_module_id == "HF_MATTYRUN"
    assert loaded.spi_flash_confirmada is True
    assert loaded.detected_mcu == "AT91SAM7S512 512K bytes"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["flash_autorizado"] is False
    assert stored["last_module_id"] == "HF_MATTYRUN"
    assert stored["spi_flash_confirmada"] is True
    assert stored["nota_local"] == "nao-apagar"
    assert "AT91SAM7S512" in path.read_text(encoding="utf-8")


def test_texto_true_tambem_e_apagado(isolated_data):
    path = isolated_data / "preferences.json"
    path.write_text(json.dumps({"flash_autorizado": "true", "last_module_id": "LF_SAMYRUN"}), encoding="utf-8")
    loaded = Preferences.load()
    assert loaded.flash_autorizado is False
    assert loaded.last_module_id == "LF_SAMYRUN"
    assert json.loads(path.read_text(encoding="utf-8"))["flash_autorizado"] is False


def test_salvar_nao_grava_autorizacao_na_memoria_ligada(isolated_data):
    prefs = Preferences(last_module_id="HF_MATTYRUN", flash_autorizado=True, spi_flash_confirmada=True)
    prefs.save()
    assert prefs.flash_autorizado is True
    stored = json.loads(Preferences.path().read_text(encoding="utf-8"))
    assert stored["flash_autorizado"] is False
    assert stored["last_module_id"] == "HF_MATTYRUN"
    again = Preferences.load()
    assert again.flash_autorizado is False
    assert again.spi_flash_confirmada is True


def test_janela_abre_sem_autorizacao_mesmo_com_arquivo_antigo(qapp, tmp_path, monkeypatch):
    window, folder, _loaded = _window(qapp, tmp_path, monkeypatch, [])
    try:
        assert window.authorize_check.isChecked() is False
        assert window.context.prefs.flash_autorizado is False
        stored = json.loads((folder / "preferences.json").read_text(encoding="utf-8"))
        assert stored["flash_autorizado"] is False
        assert stored["nota_local"] == "preservar"
        labels = [widget.text() for widget in window.findChildren(QLabel)]
        assert any("pm3-flash-fullimage" in text for text in labels)
        assert "Gravação desligada" in window.block_reason.text()
    finally:
        window.close()


def test_uma_confirmacao_grava_so_a_operacao_e_depois_desliga(qapp, tmp_path, monkeypatch):
    questions = []
    window, folder, _loaded = _window(qapp, tmp_path, monkeypatch, questions)
    calls = []

    def fake_apply(selected, device, *, force_rebuild, flash_authorized, on_stage, on_log):
        calls.append(flash_authorized)
        on_stage("Gravação", "Gravando")
        return OperationResult(
            True,
            "OK210",
            Msg.FLASH_PARTIAL_CHECK,
            "flash_partial_validation",
            stage="Validação parcial",
        )

    window.service.apply = fake_apply
    try:
        window.authorize_check.setChecked(True)
        assert len(questions) == 1
        assert "somente para a próxima operação" in questions[0][2]
        assert window.context.prefs.flash_autorizado is True
        assert json.loads((folder / "preferences.json").read_text(encoding="utf-8"))["flash_autorizado"] is False
        assert "gravará a fullimage real" in window.block_reason.text()
        window.apply_button.click()
        assert calls == [True]
        assert len(questions) == 1
        assert window.context.prefs.flash_autorizado is False
        assert window.authorize_check.isChecked() is False
        assert "OK210" in window.summary_label.text()
        window.apply_button.click()
        assert calls == [True, False]
        assert "pm3-flash" not in json.dumps(calls)
    finally:
        window.close()


def test_falha_da_operacao_desliga_a_autorizacao(qapp, tmp_path, monkeypatch):
    window, _folder, _loaded = _window(qapp, tmp_path, monkeypatch, [])
    try:
        window.context.prefs.flash_autorizado = True
        window._consume_authorization = True
        window.authorize_check.blockSignals(True)
        window.authorize_check.setChecked(True)
        window.authorize_check.blockSignals(False)
        window._finished(
            OperationResult(
                False,
                "E300",
                Msg.FLASH_UNCONFIRMED,
                "flash_unconfirmed",
                stage="Gravação não confirmada",
            )
        )
        assert window.context.prefs.flash_autorizado is False
        assert window.authorize_check.isChecked() is False
        assert window.status_pill.text() == "Erro"
    finally:
        window.close()


def test_desmarcar_cancela_antes_de_aplicar(qapp, tmp_path, monkeypatch):
    questions = []
    window, folder, _loaded = _window(qapp, tmp_path, monkeypatch, questions)
    calls = []
    window.service.apply = lambda *args, **kwargs: calls.append(kwargs["flash_authorized"]) or OperationResult(
        True, "OK100", Msg.FLASH_NOT_AUTHORIZED, "compile_only", stage="Compilação concluída"
    )
    try:
        window.authorize_check.setChecked(True)
        window.authorize_check.setChecked(False)
        assert window.context.prefs.flash_autorizado is False
        assert json.loads((folder / "preferences.json").read_text(encoding="utf-8"))["flash_autorizado"] is False
        window.apply_button.click()
        assert calls == [False]
        assert len(questions) == 1
    finally:
        window.close()


def test_recusar_o_aviso_nao_autoriza(qapp, tmp_path, monkeypatch):
    window, _folder, _loaded = _window(qapp, tmp_path, monkeypatch, [])
    import pm3manager.ui.main_window as mw

    monkeypatch.setattr(mw.QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    try:
        window.authorize_check.setChecked(True)
        assert window.authorize_check.isChecked() is False
        assert window.context.prefs.flash_autorizado is False
    finally:
        window.close()


def test_recompilar_nao_grava_e_nao_consome_a_autorizacao(qapp, tmp_path, monkeypatch):
    window, _folder, _loaded = _window(qapp, tmp_path, monkeypatch, [])
    compiled = []

    def fake_recompile(selected, *, on_stage, on_log):
        compiled.append(selected.id)
        return OperationResult(True, "OK100", Msg.COMPILE_OK, "compiled", stage="Compilação concluída")

    window.service.recompile = fake_recompile
    try:
        window.authorize_check.setChecked(True)
        assert window.context.prefs.flash_autorizado is True
        window.rebuild_button.click()
        assert compiled == ["HF_MATTYRUN"]
        assert window.context.prefs.flash_autorizado is True
        assert window.authorize_check.isChecked() is True
    finally:
        window.close()


def test_aplicar_sem_autorizacao_continua_so_compilando(qapp, tmp_path, monkeypatch):
    window, _folder, _loaded = _window(qapp, tmp_path, monkeypatch, [])
    calls = []
    window.service.apply = lambda *args, **kwargs: calls.append(kwargs["flash_authorized"]) or OperationResult(
        True, "OK100", Msg.FLASH_NOT_AUTHORIZED, "compile_only", stage="Compilação concluída"
    )
    try:
        assert window.authorize_check.isChecked() is False
        window.apply_button.click()
        assert calls == [False]
        assert window.context.prefs.flash_autorizado is False
        assert "não foi executada" in window.summary_label.text()
    finally:
        window.close()
