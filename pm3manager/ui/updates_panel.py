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
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
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

        summary = QHBoxLayout()
        summary.setSpacing(12)
        self.iceman_summary = QLabel("Iceman: —")
        self.prox_summary = QLabel("ProxSpace: —")
        for label in (self.iceman_summary, self.prox_summary):
            label.setWordWrap(True)
            label.setObjectName("value")
            label.setTextFormat(Qt.TextFormat.PlainText)
            summary.addWidget(label, 1)
        layout.addLayout(summary)

        self.iceman_version = QLabel()
        self.iceman_commit = QLabel()
        self.iceman_release = QLabel()
        self.iceman_remote = QLabel()
        self.iceman_state = QLabel()
        self.iceman_when = QLabel()
        self.iceman_link = QLabel()
        self.iceman_extra = QLabel()
        self.prox_version = QLabel()
        self.prox_release = QLabel()
        self.prox_state = QLabel()
        self.prox_when = QLabel()
        self.prox_link = QLabel()
        self.prox_extra = QLabel()
        self.columns_split = QSplitter(Qt.Orientation.Horizontal)
        self.columns_split.setObjectName("updateColumns")
        self.columns_split.setChildrenCollapsible(False)
        self.columns_split.setHandleWidth(8)
        self.columns_split.addWidget(self._column(
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
        self.columns_split.addWidget(self._column(
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
        self.columns_split.setStretchFactor(0, 1)
        self.columns_split.setStretchFactor(1, 1)
        self._columns_narrow: bool | None = None
        columns_scroll = QScrollArea()
        columns_scroll.setObjectName("updateColumnsScroll")
        columns_scroll.setWidgetResizable(True)
        columns_scroll.setFrameShape(QFrame.Shape.NoFrame)
        columns_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        columns_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        columns_scroll.setWidget(self.columns_split)
        columns_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        columns_scroll.setMinimumHeight(0)
        columns_scroll.setMaximumHeight(150)
        self.columns_scroll = columns_scroll

        self.check_button = QPushButton("Verificar atualizações")
        self.details_button = QPushButton("Ver detalhes")
        self.changes_button = QPushButton("Ver alterações")
        self.github_button = QPushButton("Abrir no GitHub")
        self.settings_button = QPushButton("Configurações")
        self.instructions_button = QPushButton("Ver instruções de atualização")
        self.check_button.clicked.connect(self.check_now)
        self.details_button.clicked.connect(self._toggle_details)
        self.changes_button.clicked.connect(self._show_changes)
        self.github_button.clicked.connect(self._open_github)
        self.settings_button.clicked.connect(self._open_settings)
        self.instructions_button.clicked.connect(self._show_instructions)
        primary = QHBoxLayout()
        for button in (self.check_button, self.details_button):
            self._size_button(button)
            primary.addWidget(button)
        layout.addLayout(primary)

        self._details = QWidget()
        self._details.setObjectName("updateDetails")
        details_layout = QVBoxLayout(self._details)
        details_layout.setContentsMargins(0, 4, 0, 0)
        details_layout.setSpacing(6)
        details_layout.addWidget(columns_scroll, 1)
        secondary = QHBoxLayout()
        extra = QHBoxLayout()
        for button in (self.changes_button, self.github_button, self.settings_button):
            self._size_button(button)
            secondary.addWidget(button)
        for button in (self.instructions_button,):
            self._size_button(button)
            extra.addWidget(button)
        details_layout.addLayout(secondary)
        details_layout.addLayout(extra)
        self._details_open = False
        self._details_dialog: QDialog | None = None
        self._capping = False
        self._details.setVisible(False)
        layout.addWidget(self._details)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._apply_height_cap()

    def _toggle_details(self) -> None:
        if self._details_dialog is not None:
            self._details_dialog.close()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Detalhes das atualizações")
        dialog.resize(860, 560)
        dialog_layout = QVBoxLayout(dialog)
        self._details.setVisible(True)
        dialog_layout.addWidget(self._details)
        self.columns_scroll.setMinimumHeight(180)
        self.columns_scroll.setMaximumHeight(16777215)
        self._details_open = True
        self._details_dialog = dialog
        dialog.finished.connect(self._hide_details_dialog)
        dialog.show()

    def _hide_details_dialog(self) -> None:
        self._details_open = False
        self._details_dialog = None
        self.columns_scroll.setMinimumHeight(0)
        self.columns_scroll.setMaximumHeight(150)
        self._details.setParent(self)
        layout = self.layout()
        if layout is not None:
            layout.addWidget(self._details)
        self._details.setVisible(False)
        self._apply_height_cap()

    def _collapsed_height(self) -> int:
        line = max(16, self.fontMetrics().height())
        button = max(32, line + 16)
        return 16 + line + line + line + button + 20

    def _preferred_panel_height(self) -> int:
        layout = self.layout()
        if layout is None:
            return self._collapsed_height()
        width = self.width() if self.width() > 80 else 720
        if layout.hasHeightForWidth():
            return max(layout.heightForWidth(width), 96)
        return max(layout.sizeHint().height(), 96)

    def _apply_height_cap(self) -> None:
        if self._capping or not hasattr(self, "_details"):
            return
        if self._details_dialog is not None:
            return
        self._capping = True
        try:
            self._details.setVisible(False)
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            collapsed = self._collapsed_height()
            cap = max(96, min(self._preferred_panel_height(), collapsed))
            self.setMinimumHeight(cap)
            self.setMaximumHeight(cap)
        finally:
            self._capping = False
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - API do Qt
        super().resizeEvent(event)
        self._apply_column_orientation()
        self._fit_column_text()
        if not self._capping:
            self._apply_height_cap()

    def _fit_column_text(self) -> None:
        if not hasattr(self, "columns_split"):
            return
        for label in self.columns_split.findChildren(QLabel):
            if not label.wordWrap() or label.width() < 20:
                continue
            needed = label.heightForWidth(label.width())
            if needed > label.minimumHeight():
                label.setMinimumHeight(needed)

    def _size_button(self, button: QPushButton) -> None:
        button.setMinimumHeight(max(32, button.fontMetrics().height() + 16))
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _apply_column_orientation(self) -> None:
        if not hasattr(self, "columns_split") or self.width() < 40:
            return
        narrow = self.width() < 860
        if narrow == self._columns_narrow:
            return
        self._columns_narrow = narrow
        self.columns_split.setOrientation(
            Qt.Orientation.Vertical if narrow else Qt.Orientation.Horizontal
        )

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
            label.setObjectName("value")
            row = QWidget()
            row.setObjectName("checkRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            cap = QLabel(caption)
            cap.setObjectName("muted")
            cap.setMinimumWidth(min(148, max(96, cap.sizeHint().width())))
            cap.setAlignment(Qt.AlignmentFlag.AlignTop)
            row_layout.addWidget(cap, 0, Qt.AlignmentFlag.AlignTop)
            row_layout.addWidget(label, 1)
            layout.addWidget(row)
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
        self.iceman_summary.setText(self._essential_line("Iceman", report.iceman))
        self.prox_summary.setText(self._essential_line("ProxSpace", report.proxspace))
        self.iceman_summary.setToolTip(self._essential_tip(report.iceman))
        self.prox_summary.setToolTip(self._essential_tip(report.proxspace))
        self._apply_height_cap()

    def _essential_line(self, title: str, report: ProviderReport) -> str:
        version = report.local.version_label or UNKNOWN_VERSION
        state = report.message or "sem estado"
        return f"{title}: {version} · {state}"

    def _essential_tip(self, report: ProviderReport) -> str:
        lines = [
            self._essential_line(report.title, report),
            f"Verificação: {report.checked_at or '—'}",
            report.web_url,
        ]
        return "\n".join(line for line in lines if line)

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
