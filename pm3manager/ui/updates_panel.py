"""Painel Atualizações. A consulta HTTP fica fora da thread da janela."""

from __future__ import annotations

import os
import threading

from PySide6.QtCore import QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from pm3manager.models import Environment
from pm3manager.updates.compatibility import compatibility_detail
from pm3manager.updates.instructions import INSTRUCTIONS
from pm3manager.updates.models import UNKNOWN_VERSION, LocalInstall, MonitorReport, ProviderReport
from pm3manager.updates.providers import ICEMAN, PROXSPACE
from pm3manager.updates.repository_detector import inspect_iceman, inspect_proxspace
from pm3manager.updates.update_cache import UpdateCache
from pm3manager.updates.update_service import UpdateService

_ALLOWED_WEB = (ICEMAN.web, PROXSPACE.web)
_WORKER_ERROR = "worker-error"


def _defer_network_in_tests() -> bool:
    """A suíte define PM3MANAGER_ENV=teste e não pode depender do GitHub."""
    return os.environ.get("PM3MANAGER_ENV", "").strip().lower() == "teste"


def _changelog_snippet(report: ProviderReport) -> str:
    remote = report.remote
    if remote is None:
        return ""
    if remote.release and remote.release.notes:
        return remote.release.notes.split("\n", 1)[0][:180]
    if remote.commit_lines:
        return remote.commit_lines[0][:180]
    return ""


class _UpdateThread(QThread):
    finished_report = Signal(object)

    def __init__(self, action, parent=None) -> None:
        super().__init__(parent)
        self._action = action

    def run(self) -> None:
        try:
            report = self._action()
        except Exception:
            report = _WORKER_ERROR
        self.finished_report.emit(report)


class UpdatesPanel(QFrame):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.setObjectName("card")
        self._cancel = threading.Event()
        self._checking = False
        self._closed = False
        self._worker: _UpdateThread | None = None
        self._banner_ids: set[str] = set()
        self._banner_dismissed = False
        self._report: MonitorReport | None = None
        self.service = UpdateService(cache=UpdateCache())
        self._build()
        self._show(self.service.cached_view(*self._preview(), keep_stored_local=True))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_now)
        self.apply_schedule()
        if not _defer_network_in_tests():
            QTimer.singleShot(800, self._startup_check)

    def rebind(self, context) -> None:
        self.context = context
        if self._checking or self._closed:
            return
        self._show(self.service.cached_view(*self._preview(), keep_stored_local=True))
        if self.context.prefs.updates_enabled and not _defer_network_in_tests():
            self.check_now()

    def apply_schedule(self) -> None:
        prefs = self.context.prefs
        self._timer.setInterval(prefs.updates_interval_minutes * 60 * 1000)
        if prefs.updates_enabled:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def shutdown(self) -> None:
        self._closed = True
        self._timer.stop()
        self._cancel.set()
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(3000)

    def check_now(self) -> None:
        if self._closed or self._checking:
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self._checking = True
        self._cancel = threading.Event()
        self.status_label.setText("Verificando atualizações...")
        self._worker = _UpdateThread(self._run_check, self)
        self._worker.finished_report.connect(self._on_report)
        self._worker.start()

    def _startup_check(self) -> None:
        if self._closed:
            return
        if self.context.prefs.updates_enabled:
            self.check_now()

    def _run_check(self) -> MonitorReport:
        iceman, proxspace = self._locals()
        return self.service.check(iceman, proxspace, self._cancel)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        title = QLabel("Atualizações")
        title.setObjectName("title")
        title.setStyleSheet("font-size: 15px; background: transparent;")
        layout.addWidget(title)

        self.notice = QFrame()
        notice_row = QHBoxLayout(self.notice)
        notice_row.setContentsMargins(0, 0, 0, 0)
        self.notice_label = QLabel("")
        self.notice_label.setWordWrap(True)
        self.notice_label.setObjectName("hint")
        dismiss = QPushButton("Dispensar")
        dismiss.clicked.connect(self._dismiss_notice)
        notice_row.addWidget(self.notice_label, 1)
        notice_row.addWidget(dismiss)
        self.notice.setVisible(False)
        layout.addWidget(self.notice)

        self.status_label = QLabel("Ainda não verificado.")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("muted")
        layout.addWidget(self.status_label)

        columns = QHBoxLayout()
        self.iceman_version = QLabel()
        self.iceman_commit = QLabel()
        self.iceman_release = QLabel()
        self.iceman_remote = QLabel()
        self.iceman_state = QLabel()
        self.iceman_when = QLabel()
        self.iceman_link = QLabel()
        self.iceman_extra = QLabel()
        columns.addWidget(self._column(
            "Iceman",
            (
                ("Versão local", self.iceman_version),
                ("Commit local", self.iceman_commit),
                ("Última release", self.iceman_release),
                ("Commit da branch", self.iceman_remote),
                ("Estado", self.iceman_state),
                ("Última verificação", self.iceman_when),
                ("Link oficial", self.iceman_link),
                ("Observação", self.iceman_extra),
            ),
        ))
        self.prox_version = QLabel()
        self.prox_release = QLabel()
        self.prox_state = QLabel()
        self.prox_when = QLabel()
        self.prox_link = QLabel()
        self.prox_extra = QLabel()
        columns.addWidget(self._column(
            "ProxSpace",
            (
                ("Versão local", self.prox_version),
                ("Última release", self.prox_release),
                ("Estado", self.prox_state),
                ("Última verificação", self.prox_when),
                ("Link oficial", self.prox_link),
                ("Observação", self.prox_extra),
            ),
        ))
        layout.addLayout(columns)

        buttons = QHBoxLayout()
        self.check_button = QPushButton("Verificar atualizações")
        self.changes_button = QPushButton("Ver alterações")
        self.github_button = QPushButton("Abrir no GitHub")
        self.settings_button = QPushButton("Configurações")
        self.instructions_button = QPushButton("Ver instruções de atualização")
        self.check_button.clicked.connect(self.check_now)
        self.changes_button.clicked.connect(self._show_changes)
        self.github_button.clicked.connect(self._open_github)
        self.settings_button.clicked.connect(self._open_settings)
        self.instructions_button.clicked.connect(self._show_instructions)
        for button in (
            self.check_button,
            self.changes_button,
            self.github_button,
            self.settings_button,
            self.instructions_button,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def _column(self, title: str, rows: tuple[tuple[str, QLabel], ...]) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        heading = QLabel(title)
        heading.setStyleSheet("font-weight: 650; background: transparent;")
        layout.addWidget(heading)
        for caption, label in rows:
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setObjectName("muted")
            layout.addWidget(QLabel(caption))
            layout.addWidget(label)
        layout.addStretch(1)
        return frame

    def _on_report(self, report) -> None:
        self._checking = False
        if self._closed:
            return
        if report == _WORKER_ERROR or not isinstance(report, MonitorReport):
            self.status_label.setText("Não foi possível consultar o GitHub.")
            return
        if report.busy:
            self.status_label.setText("Verificando atualizações...")
            return
        self._show(report)
        self._announce(report)

    def _show(self, report: MonitorReport) -> None:
        self._report = report
        self._fill(report.iceman, self.iceman_version, self.iceman_commit, self.iceman_release, self.iceman_remote, self.iceman_state, self.iceman_when, self.iceman_extra)
        self._fill(report.proxspace, self.prox_version, None, self.prox_release, None, self.prox_state, self.prox_when, self.prox_extra)
        self.iceman_link.setText(report.iceman.web_url)
        self.prox_link.setText(report.proxspace.web_url)
        parts = [report.iceman.message, report.proxspace.message]
        self.status_label.setText("  ·  ".join(part for part in parts if part))

    def _fill(self, report, version, commit, release, remote, state, when, extra) -> None:
        version.setText(report.local.version_label or UNKNOWN_VERSION)
        if commit is not None:
            commit.setText(self._commit_text(report))
        if remote is not None:
            branch = report.remote.default_branch if report.remote else ""
            sha = report.remote.branch_short if report.remote else ""
            remote.setText(f"{branch} {sha}".strip() or "—")
        release_text = "—"
        if report.remote and report.remote.release:
            item = report.remote.release
            release_text = item.tag or item.name or "—"
            if item.published_at:
                release_text = f"{release_text} ({item.published_at})"
        release.setText(release_text)
        state.setText(report.message or "—")
        when.setText(report.checked_at or "—")
        notes = list(report.local.notes)
        fingerprint = (report.local.firmware_commit or "").strip()
        if fingerprint and not any("Não é o Git HEAD" in note for note in notes):
            notes.append(
                f"Identificador no arquivo de versão: {fingerprint}. Não é o Git HEAD."
            )
        if report.archived:
            notes.append("Repositório ProxSpace arquivado." if report.key == "proxspace" else "Repositório arquivado.")
        if report.compatibility:
            notes.append(report.compatibility)
        snippet = _changelog_snippet(report)
        if snippet:
            notes.append(snippet)
        extra.setText(" ".join(notes) if notes else "—")

    def _commit_text(self, report: ProviderReport) -> str:
        local = report.local
        if not local.commit:
            return "—"
        parts = [local.commit_short]
        if local.detached:
            parts.append("HEAD desanexado")
        elif local.branch:
            parts.append(local.branch)
        if local.tag:
            parts.append(local.tag)
        if local.dirty:
            parts.append("com alterações locais")
        return " · ".join(parts)

    def _announce(self, report: MonitorReport) -> None:
        if not self.context.prefs.updates_notify:
            return
        texts = []
        fresh = []
        for item in (report.iceman, report.proxspace):
            if item.announce and item.announce_text and item.notification_id:
                texts.append(item.announce_text)
                fresh.append(item.notification_id)
        if not fresh:
            return
        self.service.cache.mark_notified(fresh)
        self._banner_ids.update(fresh)
        self._banner_dismissed = False
        self.notice_label.setText(" ".join(texts))
        self.notice.setVisible(True)

    def _dismiss_notice(self) -> None:
        if self._banner_ids:
            self.service.cache.dismiss(tuple(self._banner_ids))
        self._banner_dismissed = True
        self.notice.setVisible(False)

    def _show_changes(self) -> None:
        report = self._report
        chunks = []
        if report is None:
            chunks.append("Nenhuma alteração disponível.")
        else:
            for item in (report.iceman, report.proxspace):
                chunks.append(self._change_text(item))
            chunks.append(compatibility_detail())
        self._text_dialog("Alterações", "\n\n".join(chunks))

    def _change_text(self, report: ProviderReport) -> str:
        lines = [report.title, report.message or ""]
        remote = report.remote
        if remote is None:
            lines.append("Sem dados remotos.")
            return "\n".join(line for line in lines if line)
        if remote.release:
            lines.append(f"Release: {remote.release.tag}")
            if remote.release.published_at:
                lines.append(f"Publicada em: {remote.release.published_at}")
            lines.append(remote.release.html_url)
            if remote.release.notes:
                lines.append(remote.release.notes)
            else:
                lines.append("A release não trouxe notas.")
        else:
            lines.append("Nenhuma release estável identificada.")
        if remote.branch_summary:
            lines.append(f"Branch {remote.default_branch}: {remote.branch_summary}")
        if remote.commit_lines:
            lines.append("Commits retornados pela comparação:")
            lines.extend(remote.commit_lines)
        return "\n".join(lines)

    def _show_instructions(self) -> None:
        self._text_dialog("Instruções de atualização", INSTRUCTIONS)

    def _text_dialog(self, title: str, text: str) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(640, 420)
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        layout.addWidget(view)
        close = QPushButton("Fechar")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def _open_github(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Abrir no GitHub")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Escolha o repositório oficial."))
        iceman = QPushButton("Iceman")
        proxspace = QPushButton("ProxSpace")
        iceman.clicked.connect(lambda: self._open_url(ICEMAN.web))
        proxspace.clicked.connect(lambda: self._open_url(PROXSPACE.web))
        layout.addWidget(iceman)
        layout.addWidget(proxspace)
        dialog.exec()

    def _open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Configurações das atualizações")
        layout = QVBoxLayout(dialog)
        enabled = QCheckBox("Verificação automática")
        enabled.setChecked(self.context.prefs.updates_enabled)
        notify = QCheckBox("Notificações visuais")
        notify.setChecked(self.context.prefs.updates_notify)
        interval = QSpinBox()
        interval.setRange(15, 24 * 60)
        interval.setSuffix(" min")
        interval.setValue(self.context.prefs.updates_interval_minutes)
        layout.addWidget(enabled)
        layout.addWidget(QLabel("Intervalo da verificação automática"))
        layout.addWidget(interval)
        layout.addWidget(notify)
        buttons = QHBoxLayout()
        save = QPushButton("Salvar")
        cancel = QPushButton("Cancelar")
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        def _save() -> None:
            prefs = self.context.prefs
            prefs.updates_enabled = enabled.isChecked()
            prefs.updates_notify = notify.isChecked()
            prefs.updates_interval_minutes = interval.value()
            prefs.save()
            self.apply_schedule()
            dialog.accept()

        save.clicked.connect(_save)
        cancel.clicked.connect(dialog.reject)
        dialog.exec()

    def _open_url(self, url: str) -> None:
        if not any(url == prefix or url.startswith(prefix + "/") for prefix in _ALLOWED_WEB):
            return
        QDesktopServices.openUrl(QUrl(url))

    def _preview(self) -> tuple[LocalInstall, LocalInstall]:
        env: Environment = self.context.env
        version = env.version or ""
        iceman = LocalInstall(
            present=True,
            kind="checkout",
            path=str(env.repo_root),
            version=version,
            version_label=version or UNKNOWN_VERSION,
            commit="",
            firmware_commit=env.commit or "",
        )
        proxspace = LocalInstall(
            present=True,
            kind="desconhecido",
            path=str(env.proxspace_root),
            version_label=UNKNOWN_VERSION,
        )
        return iceman, proxspace

    def _locals(self) -> tuple[LocalInstall, LocalInstall]:
        env = self.context.env
        return inspect_iceman(env), inspect_proxspace(env.proxspace_root)
