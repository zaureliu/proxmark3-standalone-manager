"""Aba de diagnóstico. A coleta roda fora da thread da interface."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pm3manager.diagnostics.export import export_json, export_text, summary_text
from pm3manager.diagnostics.models import ORIGIN_LABEL, SEVERITY_LABEL, DiagnosticReport, Severity
from pm3manager.diagnostics.service import DiagnosticService, live_collect
from pm3manager.models import Device, Module
from pm3manager.workflow.context import AppContext

_GROUPS = (
    ("Dispositivo", ("connection", "port", "vidpid", "usb_name", "usb_confidence")),
    ("Firmware e bootrom", ("client_version", "firmware_version", "bootrom_version", "family", "ping", "standalone_banner")),
    ("Hardware e memória", ("mcu_detected", "architecture", "sram", "embedded_flash", "spi_detected", "emulator_memory", "bigbuf", "smartcard", "bt_addon", "compile_mcu_support")),
    ("Ambiente ProxSpace", ("proxspace", "toolchain")),
    ("Checkout Iceman", ("checkout", "version_file", "version_token", "git_commit", "git_shallow", "git_dirty")),
    ("Configuração da compilação", ("file_platform", "file_platform_extras", "file_standalone", "file_led_order", "file_platform_size", "intended_platform", "intended_standalone", "intended_extras", "intended_led", "intended_size", "prefs_mcu", "prefs_kind", "prefs_spi", "spi_confirmed_pref")),
    ("Módulo selecionado", ("module_id", "module_class")),
)


class _DiagnosticWorker(QThread):
    finished_report = Signal(object)

    def __init__(self, service: DiagnosticService, mode: str) -> None:
        super().__init__()
        self._service = service
        self._mode = mode

    def run(self) -> None:
        self.finished_report.emit(self._service.run(self._mode))


class DiagnosticsPanel(QWidget):
    def __init__(
        self,
        context: AppContext,
        device_provider: Callable[[], Device | None],
        module_provider: Callable[[], Module | None],
        blocked: Callable[[], bool],
        on_busy: Callable[[bool], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._device = device_provider
        self._module = module_provider
        self._blocked = blocked
        self._on_busy = on_busy
        self._report: DiagnosticReport | None = None
        self._worker: _DiagnosticWorker | None = None
        self.service = DiagnosticService(context.lock, live_collect(context, device_provider, module_provider, context.shell.work_dir))
        self._build()

    def rebind(self, context: AppContext) -> None:
        self.service.lock = context.lock
        self.service.collect = live_collect(context, self._device, self._module, context.shell.work_dir)

    def shutdown(self) -> None:
        self.service.cancel()
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(4000)
        self._worker = None
        self._set_running(False)

    def mark_context(self) -> None:
        if self._report is None:
            self.stale.setText("")
            return
        current = _stamp(self._device(), self._module())
        if current != _report_stamp(self._report):
            self.stale.setText(
                "A leitura abaixo é de outro dispositivo ou módulo. Ela não confirma o contexto atual."
            )
        else:
            self.stale.setText("")

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0)
        root.setSpacing(8)
        self.status = QLabel("O diagnóstico ainda não foi executado.")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.verdict = QLabel("Sem resultado")
        self.verdict.setObjectName("title")
        self.verdict.setTextFormat(Qt.TextFormat.PlainText)
        self.stale = QLabel("")
        self.stale.setObjectName("hint")
        self.stale.setWordWrap(True)
        self.stale.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.verdict)
        root.addWidget(self.status)
        root.addWidget(self.stale)
        row = QHBoxLayout()
        self.run_button = QPushButton("Executar diagnóstico")
        self.refresh_button = QPushButton("Atualizar informações")
        self.copy_button = QPushButton("Copiar resumo")
        self.export_button = QPushButton("Exportar relatório")
        self.details_button = QPushButton("Ver detalhes técnicos")
        self.cancel_button = QPushButton("Cancelar")
        self.run_button.setObjectName("primary")
        for button in (
            self.run_button,
            self.refresh_button,
            self.copy_button,
            self.export_button,
            self.details_button,
            self.cancel_button,
        ):
            button.setMinimumHeight(32)
            row.addWidget(button)
        self.run_button.clicked.connect(lambda: self.start("full"))
        self.refresh_button.clicked.connect(lambda: self.start("refresh"))
        self.copy_button.clicked.connect(self._copy)
        self.export_button.clicked.connect(self._export)
        self.details_button.clicked.connect(self._details)
        self.cancel_button.clicked.connect(self.service.cancel)
        root.addLayout(row)
        self.copy_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.details_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def start(self, mode: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.status.setText("O diagnóstico já está em execução.")
            return
        if self._blocked():
            self.status.setText(
                "Há compilação, gravação ou outra operação em andamento. O diagnóstico não foi iniciado."
            )
            return
        self._set_running(True)
        self.status.setText("Lendo o ambiente. O cliente só entra em Executar diagnóstico.")
        worker = _DiagnosticWorker(self.service, mode)
        worker.finished_report.connect(self._finished)
        worker.finished.connect(self._thread_done)
        self._worker = worker
        worker.start()

    def _thread_done(self) -> None:
        self._worker = None

    def _finished(self, report: object) -> None:
        self._set_running(False)
        if not isinstance(report, DiagnosticReport):
            self.status.setText("O diagnóstico não devolveu um relatório.")
            return
        self._report = report
        self.verdict.setText(report.verdict_label)
        self.status.setText(report.summary)
        self._fill(report)
        self.mark_context()
        enabled = True
        self.copy_button.setEnabled(enabled)
        self.export_button.setEnabled(enabled)
        self.details_button.setEnabled(enabled)

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.refresh_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self._on_busy(running)

    def _fill(self, report: DiagnosticReport) -> None:
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        by_key = {fact.key: fact for fact in report.facts}
        for title, keys in _GROUPS:
            chosen = [by_key[key] for key in keys if key in by_key]
            files = [fact for fact in report.facts if fact.key.startswith("file:") and title == "Ambiente ProxSpace"]
            if title == "Ambiente ProxSpace":
                chosen.extend(files)
            if not chosen:
                continue
            self._body.addWidget(self._heading(title))
            for fact in chosen:
                self._body.addWidget(self._fact(fact.label, fact.value, ORIGIN_LABEL[fact.origin], fact.justification))
        self._body.addWidget(self._heading("Compatibilidade"))
        self._body.addWidget(self._fact("Resultado", report.verdict_label, "Inferido", report.summary))
        self._body.addWidget(self._heading("Avisos e verificações"))
        for severity in (Severity.BLOCKING, Severity.WARNING, Severity.UNKNOWN, Severity.INFO, Severity.PASS):
            for check in report.checks_by_severity(severity):
                self._body.addWidget(
                    self._fact(check.title, check.message, SEVERITY_LABEL[severity], check.justification)
                )
        self._body.addWidget(self._heading("Limitações"))
        for item in report.limitations:
            label = QLabel(item)
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setObjectName("hint")
            self._body.addWidget(label)
        self._body.addStretch(1)

    def _heading(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("section")
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def _fact(self, label: str, value: str, origin: str, why: str) -> QLabel:
        widget = QLabel(f"{label}: {value}\n{origin}. {why}")
        widget.setWordWrap(True)
        widget.setTextFormat(Qt.TextFormat.PlainText)
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return widget

    def _copy(self) -> None:
        if self._report is None:
            return
        QGuiApplication.clipboard().setText(summary_text(self._report))
        self.status.setText("Resumo copiado.")

    def _export(self) -> None:
        if self._report is None:
            return
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Exportar diagnóstico",
            "diagnostico.json",
            "JSON (*.json);;Texto (*.txt)",
        )
        if not path:
            return
        text = export_text(self._report) if path.lower().endswith(".txt") or "Texto" in selected else export_json(self._report)
        from pathlib import Path

        Path(path).write_text(text, encoding="utf-8")
        self.status.setText("Relatório exportado.")

    def _details(self) -> None:
        if self._report is None:
            return
        from PySide6.QtWidgets import QDialog

        dialog = QDialog(self)
        dialog.setWindowTitle("Detalhes do diagnóstico")
        dialog.resize(760, 520)
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(export_text(self._report) + "\n" + self._report.technical)
        layout.addWidget(view)
        dialog.exec()


def _stamp(device: Device | None, module: Module | None) -> str:
    if device is None:
        port = vid = pid = ""
    else:
        port = device.port
        vid = f"{device.vid:04X}" if device.vid is not None else ""
        pid = f"{device.pid:04X}" if device.pid is not None else ""
    module_id = module.id if module else ""
    return "|".join((port, vid, pid, module_id))


def _report_stamp(report: DiagnosticReport) -> str:
    parts = report.context_key.split("|")
    return "|".join(parts[:4])
