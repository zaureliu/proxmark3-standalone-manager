"""Painel Atualizações. Qt offscreen, sem GitHub e sem Proxmark3."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QCheckBox, QDialog, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox

from pm3manager.cache.store import FirmwareCache
from pm3manager.preferences import Preferences
from pm3manager.proxspace.shell import ProxSpaceShell
from pm3manager.updates.compatibility import NOT_VERIFIED
from pm3manager.updates.github_client import GitHubClient, GitHubError
from pm3manager.updates.models import UNKNOWN_VERSION, LocalInstall, MonitorReport, ProviderReport, Relation, ReleaseInfo, RemoteView
from pm3manager.updates.providers import ICEMAN, PROXSPACE
from pm3manager.ui.updates_panel import UpdatesPanel
from pm3manager.workflow.context import AppContext
from pm3manager.workflow.lock import OperationLock
from tests.fakes import make_env, module


class Ctx:
    def __init__(self, env, prefs) -> None:
        self.env = env
        self.prefs = prefs


def _provider(key: str, web: str, **kwargs) -> ProviderReport:
    remote = kwargs.pop("remote", None)
    data = dict(
        key=key,
        title="Iceman" if key == "iceman" else "ProxSpace",
        web_url=web,
        local=LocalInstall(present=True, version="v4.23346", version_label="v4.23346", commit="a" * 40, branch="master"),
        remote=remote,
        relation=Relation.NEW_RELEASE,
        message="Nova release disponível.",
        compatibility=NOT_VERIFIED,
        fresh=True,
        cached=False,
        checked_at="2026-10-23T12:00:00+00:00",
        notification_id="release:v4.23347",
        announce=True,
        announce_text="Nova versão do Iceman disponível." if key == "iceman" else "",
    )
    data.update(kwargs)
    return ProviderReport(**data)


def _remote() -> RemoteView:
    return RemoteView(
        archived=False,
        default_branch="master",
        html_url=ICEMAN.web,
        release=ReleaseInfo(
            "v4.23347",
            "v4.23347",
            "2026-10-01T00:00:00Z",
            f"{ICEMAN.web}/releases/tag/v4.23347",
            "Notas da release sem HTML",
            "b" * 40,
        ),
        branch_sha="b" * 40,
        compare_status="ahead",
        release_compare="ahead",
        commit_lines=("bbbbbbbbbbbb ajuste do cliente",),
    )


def _report(**kwargs) -> MonitorReport:
    iceman = kwargs.pop("iceman", _provider("iceman", ICEMAN.web, remote=_remote()))
    proxspace = kwargs.pop(
        "proxspace",
        _provider(
            "proxspace",
            PROXSPACE.web,
            relation=Relation.CURRENT,
            message="ProxSpace atualizado. Repositório ProxSpace arquivado.",
            announce=False,
            announce_text="",
            notification_id="",
            remote=RemoteView(archived=True, default_branch="master", release=None),
            local=LocalInstall(present=True, kind="pacote", version_label=UNKNOWN_VERSION),
        ),
    )
    return MonitorReport(iceman=iceman, proxspace=proxspace, **kwargs)


def _panel(tmp_path, prefs: Preferences | None = None) -> UpdatesPanel:
    env = make_env(tmp_path)
    return UpdatesPanel(Ctx(env, prefs or Preferences()), None)


def _drive(panel, action) -> list[BaseException]:
    errors: list[BaseException] = []
    bail = QTimer(panel)
    bail.setSingleShot(True)

    def run() -> None:
        bail.stop()
        dialogs = [item for item in panel.findChildren(QDialog) if item.isVisible()]
        if not dialogs:
            errors.append(AssertionError("diálogo não apareceu"))
            return
        try:
            action(dialogs[-1])
        except BaseException as exc:
            errors.append(exc)
            dialogs[-1].reject()

    def give_up() -> None:
        for dialog in panel.findChildren(QDialog):
            if dialog.isVisible():
                errors.append(AssertionError("diálogo não foi concluído"))
                dialog.reject()

    bail.timeout.connect(give_up)
    bail.start(3000)
    QTimer.singleShot(0, panel, run)
    return errors


def test_painel_mostra_os_dois_lados_e_dispensa_sem_apagar(qapp, isolated_data):
    panel = _panel(isolated_data)
    panel.show()
    try:
        assert panel.iceman_link.text() == ICEMAN.web
        assert panel.prox_link.text() == PROXSPACE.web
        assert panel.prox_version.text() == UNKNOWN_VERSION
        report = _report()
        panel._on_report(report)
        assert panel.notice.isVisible()
        assert panel.notice_label.text() == "Nova versão do Iceman disponível."
        assert "v4.23347" in panel.iceman_release.text()
        assert panel.iceman_remote.text().startswith("master ")
        assert "Notas da release" in panel.iceman_extra.text()
        assert NOT_VERIFIED in panel.iceman_extra.text()
        assert "Repositório ProxSpace arquivado." in panel.prox_state.text()
        assert "bbbbbbbbbbbb" in panel.iceman_commit.text() or panel.iceman_commit.text().startswith("a" * 12)
        panel._dismiss_notice()
        assert panel.notice.isVisible() is False
        assert panel.iceman_release.text().startswith("v4.23347")
        assert panel.iceman_state.text() == "Nova release disponível."
        panel._on_report(_report(iceman=_provider("iceman", ICEMAN.web, remote=_remote(), announce=False, announce_text="")))
        assert panel.notice.isVisible() is False
        assert "release:v4.23347" in panel.service.cache.notified()
        assert "release:v4.23347" in panel.service.cache.dismissed()
    finally:
        panel.shutdown()


def test_commit_local_nao_mostra_o_identificador_do_arquivo_de_versao(qapp, isolated_data):
    head = "dc0110c29d320e04b37ea436ee2924901407ae72"
    local = LocalInstall(
        present=True,
        version_label="Iceman/master/v4.23346",
        commit=head,
        tag="v4.23346",
        detached=True,
        firmware_commit="9ce8a4b6c",
        notes=("Identificador no arquivo de versão: 9ce8a4b6c. Não é o Git HEAD.",),
    )
    panel = _panel(isolated_data)
    panel.show()
    try:
        panel._show(_report(iceman=_provider(
            "iceman",
            ICEMAN.web,
            local=local,
            remote=_remote(),
            relation=Relation.NEW_COMMITS,
            message="Novos commits disponíveis.",
            announce=False,
            announce_text="",
            notification_id="",
        )))
        assert panel.iceman_commit.text().startswith(head[:12])
        assert "9ce8a4b6c" not in panel.iceman_commit.text()
        assert "HEAD desanexado" in panel.iceman_commit.text()
        assert "9ce8a4b6c" in panel.iceman_extra.text()
        assert "Não é o Git HEAD" in panel.iceman_extra.text()
        missing = LocalInstall(
            present=True,
            version_label="Iceman/master/v4.23346",
            firmware_commit="9ce8a4b6c",
        )
        panel._show(_report(iceman=_provider(
            "iceman",
            ICEMAN.web,
            local=missing,
            remote=_remote(),
            relation=Relation.LOCAL_UNKNOWN,
            message="Versão local não identificada.",
            announce=False,
            announce_text="",
            notification_id="",
        )))
        assert panel.iceman_commit.text() == "—"
        assert "9ce8a4b6c" not in panel.iceman_commit.text()
        assert "Não é o Git HEAD" in panel.iceman_extra.text()
    finally:
        panel.shutdown()


def test_botoes_de_alteracoes_instrucoes_github_e_configuracao(qapp, isolated_data, monkeypatch):
    prefs = Preferences()
    prefs.updates_enabled = True
    prefs.updates_interval_minutes = 60
    prefs.updates_notify = True
    panel = _panel(isolated_data, prefs)
    opened: list[str] = []
    monkeypatch.setattr(
        "pm3manager.ui.updates_panel.QDesktopServices.openUrl",
        lambda url: opened.append(url.toString()) or True,
    )
    try:
        panel._show(_report())

        def read_changes(dialog: QDialog) -> None:
            edit = dialog.findChild(QPlainTextEdit)
            assert edit is not None
            assert dialog.findChild(type(edit)) is edit
            text = edit.toPlainText()
            assert "Release: v4.23347" in text
            assert "Notas da release sem HTML" in text
            assert "ajuste do cliente" in text
            assert "Compatibilidade" in text or "não verifica" in text
            assert "<script>" not in text
            dialog.accept()

        errors = _drive(panel, read_changes)
        panel.changes_button.click()
        if errors:
            raise errors[0]

        def read_help(dialog: QDialog) -> None:
            text = dialog.findChild(QPlainTextEdit).toPlainText()
            assert "não grava firmware" in text
            assert "bootrom" in text
            assert "git pull" not in text.lower() or "não" in text.lower()
            dialog.accept()

        errors = _drive(panel, read_help)
        panel.instructions_button.click()
        if errors:
            raise errors[0]

        def open_iceman(dialog: QDialog) -> None:
            for button in dialog.findChildren(QPushButton):
                if button.text() == "Iceman":
                    button.click()
            dialog.accept()

        errors = _drive(panel, open_iceman)
        panel.github_button.click()
        if errors:
            raise errors[0]
        assert opened == [ICEMAN.web]
        panel._open_url("https://evil.example/payload")
        panel._open_url("https://github.com/RfidResearchGroup/proxmark3.evil")
        assert opened == [ICEMAN.web]

        def save_settings(dialog: QDialog) -> None:
            boxes = dialog.findChildren(QCheckBox)
            assert [box.text() for box in boxes] == ["Verificação automática", "Notificações visuais"]
            boxes[0].setChecked(False)
            boxes[1].setChecked(False)
            spin = dialog.findChild(QSpinBox)
            assert spin.minimum() == 15
            assert spin.maximum() == 24 * 60
            spin.setValue(45)
            for button in dialog.findChildren(QPushButton):
                if button.text() == "Salvar":
                    button.click()

        errors = _drive(panel, save_settings)
        panel.settings_button.click()
        if errors:
            raise errors[0]
        assert prefs.updates_enabled is False
        assert prefs.updates_notify is False
        assert prefs.updates_interval_minutes == 45
        assert panel._timer.isActive() is False
        again = Preferences.load()
        assert again.updates_interval_minutes == 45
        assert again.updates_enabled is False
        prefs.updates_enabled = True
        prefs.updates_interval_minutes = 15
        panel.apply_schedule()
        assert panel._timer.isActive() is True
        assert panel._timer.interval() == 15 * 60 * 1000
    finally:
        panel.shutdown()


def test_verificacao_manual_nao_bloqueia_nem_repete_enquanto_corre(qapp, isolated_data):
    panel = _panel(isolated_data)
    calls = {"n": 0}
    started = threading.Event()

    def fake_check(iceman, proxspace, cancel=None):
        calls["n"] += 1
        started.set()
        if cancel is not None:
            cancel.wait(2)
        return _report(busy=False)

    panel.service.check = fake_check
    try:
        began = time.monotonic()
        panel.check_button.click()
        assert started.wait(2)
        assert time.monotonic() - began < 1.5
        assert panel.status_label.text() == "Verificando atualizações..."
        panel.check_button.click()
        panel.shutdown()
        assert calls["n"] == 1
        assert panel._closed is True
        assert panel._worker is None or panel._worker.isRunning() is False
    finally:
        panel.shutdown()


def test_falha_do_worker_e_encerramento_com_a_janela(qapp, isolated_data, monkeypatch):
    panel = _panel(isolated_data)

    def broken(iceman, proxspace, cancel=None):
        raise RuntimeError("falha simulada")

    panel._locals = lambda: (LocalInstall(), LocalInstall())
    panel.service.check = broken
    try:
        panel.check_now()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and panel.status_label.text() == "Verificando atualizações...":
            QTest.qWait(50)
        assert panel.status_label.text() == "Não foi possível consultar o GitHub."
        assert panel._checking is False
    finally:
        panel.shutdown()

    monkeypatch.setattr("pm3manager.ui.main_window.detect_devices", lambda: [])
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    env = make_env(isolated_data)
    prefs = Preferences()
    prefs.updates_enabled = False
    context = AppContext(
        env=env,
        prefs=prefs,
        modules=[module("HF_MATTYRUN")],
        shell=ProxSpaceShell(env, isolated_data / "work"),
        cache=FirmwareCache(isolated_data / "firmware-cache"),
        lock=OperationLock(),
    )
    from pm3manager.ui.main_window import MainWindow

    window = MainWindow(context)
    try:
        assert window.minimumSize().width() == 980
        assert window.minimumSize().height() == 720
        titles = [label.text() for label in window.findChildren(QLabel)]
        assert "Atualizações" in titles
        for caption in ("Verificar atualizações", "Ver alterações", "Abrir no GitHub", "Configurações"):
            assert any(button.text() == caption for button in window.findChildren(QPushButton))
        window.show()
        window.resize(1024, 700)
        qapp.processEvents()
        window.resize(1400, 900)
        qapp.processEvents()
        assert window.isVisible()
        assert not window.updates_panel.isHidden()
        window._busy = True
        window.close()
        assert window.updates_panel._closed is False
        window._busy = False
        window._poll.stop()
        window.close()
        assert window.updates_panel._closed is True
    finally:
        window._poll.stop()
        if not window.updates_panel._closed:
            window.updates_panel.shutdown()


def test_inicio_da_janela_nao_consulta_a_rede_na_suite(qapp, isolated_data, monkeypatch):
    hit = []

    def boom(self, url, etag="", *, missing_ok=False):
        hit.append(url)
        raise GitHubError("connection", "Não foi possível consultar o GitHub.")

    monkeypatch.setattr(GitHubClient, "get_json", boom)
    env = make_env(isolated_data)
    prefs = Preferences()
    context = AppContext(
        env=env,
        prefs=prefs,
        modules=[module("HF_MATTYRUN")],
        shell=ProxSpaceShell(env, isolated_data / "work"),
        cache=FirmwareCache(isolated_data / "firmware-cache"),
        lock=OperationLock(),
    )
    from pm3manager.ui.main_window import MainWindow

    window = MainWindow(context)
    try:
        QTest.qWait(1100)
        qapp.processEvents()
        assert hit == []
        assert window.updates_panel._checking is False
    finally:
        window._poll.stop()
        window.close()


def test_inicio_real_agenda_a_consulta_sem_esperar_o_intervalo(qapp, isolated_data, monkeypatch):
    monkeypatch.setenv("PM3MANAGER_ENV", "producao")
    calls = []
    monkeypatch.setattr(UpdatesPanel, "check_now", lambda self: calls.append("agora"))
    panel = _panel(isolated_data)
    try:
        QTest.qWait(1500)
        assert calls == ["agora"]
        assert panel._timer.isActive() is True
        assert panel._timer.interval() == 60 * 60 * 1000
    finally:
        panel.shutdown()


def test_qtimer_respeita_o_intervalo_e_nao_sobrepoe_a_consulta(qapp, isolated_data):
    """O intervalo de produção permanece em minutos. Só o QTimer deste teste é acelerado."""
    from pm3manager.updates.models import clamp_interval

    assert clamp_interval(1) == 15
    prefs = Preferences()
    prefs.updates_interval_minutes = 15
    panel = _panel(isolated_data, prefs)
    release = threading.Event()
    started: list[float] = []

    def slow() -> MonitorReport:
        started.append(time.monotonic())
        release.wait(2)
        return _report(iceman=_provider(
            "iceman",
            ICEMAN.web,
            remote=_remote(),
            announce=False,
            announce_text="",
            notification_id="",
        ))

    panel._run_check = slow
    try:
        panel.apply_schedule()
        assert panel._timer.isActive() is True
        assert panel._timer.interval() == 15 * 60 * 1000
        panel._timer.setInterval(80)
        panel.check_now()
        deadline = time.monotonic() + 2
        while not started and time.monotonic() < deadline:
            QTest.qWait(20)
        QTest.qWait(300)
        assert len(started) == 1
        assert panel._checking is True
        assert panel.status_label.text() == "Verificando atualizações..."
        release.set()
        deadline = time.monotonic() + 2
        while panel._checking and time.monotonic() < deadline:
            QTest.qWait(20)
        assert panel._checking is False
    finally:
        release.set()
        panel.shutdown()
        assert panel._closed is True
        assert panel._timer.isActive() is False
        assert panel._worker is None or panel._worker.isFinished()


def test_consulta_automatica_desligada_nao_dispara_no_inicio(qapp, isolated_data, monkeypatch):
    monkeypatch.setenv("PM3MANAGER_ENV", "producao")
    calls = []
    monkeypatch.setattr(UpdatesPanel, "check_now", lambda self: calls.append("agora"))
    prefs = Preferences()
    prefs.updates_enabled = False
    panel = _panel(isolated_data, prefs)
    try:
        QTest.qWait(1500)
        assert calls == []
        assert panel._timer.isActive() is False
    finally:
        panel.shutdown()


def test_links_e_rotulos_usam_texto_puro(qapp, isolated_data):
    panel = _panel(isolated_data)
    try:
        assert panel.iceman_state.textFormat() == Qt.TextFormat.PlainText
        assert panel.iceman_extra.textFormat() == Qt.TextFormat.PlainText
        panel._show(
            _report(
                iceman=_provider(
                    "iceman",
                    ICEMAN.web,
                    remote=_remote(),
                    message="Nova release disponível.",
                )
            )
        )
        assert "<" not in panel.iceman_extra.text()
    finally:
        panel.shutdown()
