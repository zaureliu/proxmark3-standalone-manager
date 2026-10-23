"""Janela principal. Operações longas ficam numa QThread."""

from __future__ import annotations

import html
import os
import sys

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pm3manager import __version__
from pm3manager.errors import AppError
from pm3manager.hardware.detector import detect_devices
from pm3manager.messages import Msg
from pm3manager.models import COMPATIBILITY_LABEL, Compatibility, Confidence, Device, Module
from pm3manager.modules.catalog import can_apply, filter_modules
from pm3manager.paths import resource_path
from pm3manager.client.launcher import launch_client
from pm3manager.logging_setup import environment_name, latest_log_file, setup_logging
from pm3manager.ui.presentation import present_result
from pm3manager.ui.theme import LOG_KIND_COLORS, STATUS_COLORS, STYLESHEET
from pm3manager.ui.worker import ServiceWorker
from pm3manager.preferences import Preferences
from pm3manager.workflow.context import AppContext
from pm3manager.workflow.service import ManagerService, build_config, incompatible_flash


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.service = ManagerService(
            context.env,
            context.prefs,
            context.shell,
            context.cache,
            context.lock,
            detect=detect_devices,
        )
        self._devices: list[Device] = []
        self._busy = False
        self._consume_authorization = False
        self._worker: ServiceWorker | None = None
        self._elapsed = QElapsedTimer()
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick)
        self.setWindowTitle("Proxmark3 Standalone Manager")
        self.resize(1240, 820)
        self.setMinimumSize(980, 680)
        self._build()
        self._apply_recovery_note()
        self._refresh_modules()
        self._select_last_module()
        self._sync_hardware_controls()
        self._refresh_config_text()
        self._refresh_firmware_label()
        self.set_status("Detectando")
        self._poll = QTimer(self)
        self._poll.setInterval(1500)
        self._poll.timeout.connect(self._poll_devices)
        self._poll.start()
        QTimer.singleShot(0, self._poll_devices)

    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Proxmark3 Standalone Manager")
        title.setObjectName("title")
        self.subtitle = QLabel(self._subtitle_text())
        self.subtitle.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(self.subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.status_pill = QLabel("Detectando")
        self.status_pill.setObjectName("statusPill")
        header.addWidget(self.status_pill)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._device_card())
        splitter.addWidget(self._module_card())
        splitter.addWidget(self._operation_card())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 3)
        root.addWidget(splitter, 1)
        root.addWidget(self._progress_card())

    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("title")
        label.setStyleSheet("font-size: 15px; background: transparent;")
        layout.addWidget(label)
        return frame, layout

    def _device_card(self) -> QFrame:
        frame, layout = self._card("Dispositivo")
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self._device_changed)
        layout.addWidget(self.device_combo)
        self.proxspace_label = QLabel(str(self.context.env.proxspace_root))
        self.proxspace_label.setWordWrap(True)
        self.proxspace_label.setObjectName("muted")
        self.proxspace_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.proxspace_label)
        self.repo_combo = QComboBox()
        self.repo_combo.currentTextChanged.connect(self._repo_changed)
        layout.addWidget(self.repo_combo)
        self.proxspace_button = QPushButton("Selecionar ProxSpace")
        self.proxspace_button.clicked.connect(self._choose_proxspace)
        layout.addWidget(self.proxspace_button)
        self._populate_repo_combo()
        self.device_labels = {}
        grid = QGridLayout()
        rows = (
            ("hardware", "Hardware"),
            ("port", "Porta COM"),
            ("usb", "Confiança"),
            ("firmware", "Firmware"),
            ("config", "Compilação"),
        )
        for row, (key, caption) in enumerate(rows):
            caption_label = QLabel(caption)
            caption_label.setObjectName("muted")
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(caption_label, row, 0)
            grid.addWidget(value, row, 1)
            self.device_labels[key] = value
        layout.addLayout(grid)
        self.spi_check = QCheckBox("Confirmo que esta placa tem memória flash SPI externa")
        self.spi_check.setChecked(self.context.prefs.spi_flash_confirmada)
        self.spi_check.toggled.connect(self._spi_toggled)
        self.size_check = QCheckBox("Forçar PLATFORM_SIZE=256 (somente MCU com 256 KB internos)")
        self.size_check.toggled.connect(self._size_toggled)
        layout.addWidget(self.spi_check)
        layout.addWidget(self.size_check)
        hint = QLabel(
            "O make lê Makefile.platform na raiz do checkout. O arquivo em pm3/ não entra nessa compilação. "
            "PM3GENERIC com LED_ORDER=PM3EASY define o chip AT91SAM7S; isso não identifica o modelo como Easy. "
            "MCU de 512 KB não usa PLATFORM_SIZE=256. MCU de 256 KB torna esse tamanho obrigatório. "
            "FLASH só entra com a flash SPI confirmada. RDV4 pode ser diagnosticado, mas não recebe esta imagem."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return frame

    def _module_card(self) -> QFrame:
        frame, layout = self._card("Módulos Standalone")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Pesquisar módulo, protocolo ou identificador")
        self.search_box.textChanged.connect(self._refresh_modules)
        self.category_combo = QComboBox()
        self.category_combo.addItems(
            ["Todas", "Low Frequency (LF)", "High Frequency (HF)", "Multimodo", "Outros"]
        )
        self.category_combo.currentTextChanged.connect(self._refresh_modules)
        layout.addWidget(self.search_box)
        layout.addWidget(self.category_combo)
        self.module_table = QTableWidget(0, 4)
        self.module_table.setHorizontalHeaderLabels(["Identificador", "Nome", "Compatibilidade", "Cache"])
        self.module_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.module_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.module_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.module_table.verticalHeader().setVisible(False)
        self.module_table.horizontalHeader().setStretchLastSection(True)
        self.module_table.itemSelectionChanged.connect(self._module_changed)
        layout.addWidget(self.module_table, 1)
        return frame

    def _operation_card(self) -> QFrame:
        frame, layout = self._card("Operações")
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(False)
        layout.addWidget(self.details, 1)
        self.confirm_uncertain = QCheckBox("Confirmo os requisitos deste módulo neste Proxmark3")
        self.confirm_uncertain.toggled.connect(self._uncertain_toggled)
        layout.addWidget(self.confirm_uncertain)
        self.authorize_check = QCheckBox(
            "Autorizar gravação real da fullimage no próximo Aplicar módulo"
        )
        self.authorize_check.setChecked(False)
        self.context.prefs.flash_autorizado = False
        self.authorize_check.toggled.connect(self._authorize_toggled)
        layout.addWidget(self.authorize_check)
        authorize_hint = QLabel(
            "Desmarcada, Aplicar módulo só compila. Marcada, essa operação grava a fullimage "
            "real com pm3-flash-fullimage e não pede outra confirmação. A autorização não é "
            "salva: ela acaba ao terminar, falhar ou ser desmarcada, e também ao abrir o aplicativo. "
            "Recompilar e Verificar dispositivo não gravam."
        )
        authorize_hint.setObjectName("hint")
        authorize_hint.setWordWrap(True)
        layout.addWidget(authorize_hint)
        self.apply_button = QPushButton("Aplicar módulo")
        self.apply_button.setObjectName("primary")
        self.rebuild_button = QPushButton("Recompilar")
        self.verify_button = QPushButton("Verificar dispositivo")
        self.client_button = QPushButton("Abrir cliente Proxmark3")
        self.logs_button = QPushButton("Visualizar logs")
        self.apply_button.clicked.connect(self._apply)
        self.rebuild_button.clicked.connect(self._rebuild)
        self.verify_button.clicked.connect(self._verify)
        self.client_button.clicked.connect(self._open_client)
        self.logs_button.clicked.connect(self._show_logs)
        for button in (
            self.apply_button,
            self.rebuild_button,
            self.verify_button,
            self.client_button,
            self.logs_button,
        ):
            layout.addWidget(button)
        self.block_reason = QLabel("")
        self.block_reason.setObjectName("hint")
        self.block_reason.setWordWrap(True)
        layout.addWidget(self.block_reason)
        return frame

    def _progress_card(self) -> QFrame:
        frame, layout = self._card("Progresso")
        top = QHBoxLayout()
        self.stage_label = QLabel("Etapa: aguardando")
        self.elapsed_label = QLabel("Tempo decorrido: 00:00")
        self.elapsed_label.setObjectName("muted")
        top.addWidget(self.stage_label)
        top.addStretch(1)
        top.addWidget(self.elapsed_label)
        layout.addLayout(top)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.summary_label = QLabel("Conecte o Proxmark3 e escolha um módulo.")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        note = QLabel(
            "Durante a gravação a porta pode sumir enquanto o bootloader reinicia. "
            "Isso não é, sozinho, uma falha. Se for preciso apertar o botão do Proxmark3, "
            "o programa avisa: ele não aperta o botão por você."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.log_legend = QLabel(
            "Estados: Informação, Aviso, Erro operacional, Falha crítica, "
            "Evento de teste, Validação parcial e Validação concluída."
        )
        self.log_legend.setObjectName("hint")
        self.log_legend.setWordWrap(True)
        layout.addWidget(self.log_legend)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setAcceptRichText(True)
        self.log_view.document().setMaximumBlockCount(2000)
        self.log_view.setFont(QFont("Consolas", 10))
        self.log_view.setPlaceholderText(
            "O estado de cada operação aparece identificado. O texto técnico da compilação e da gravação permanece neste painel."
        )
        layout.addWidget(self.log_view, 1)
        return frame

    def set_status(self, status: str) -> None:
        self.status_pill.setText(status)
        color = STATUS_COLORS.get(status, "#8b95a5")
        self.status_pill.setStyleSheet(
            f"background: {color}; color: #14181f; border-radius: 10px; padding: 4px 10px; font-weight: 700;"
        )

    def _apply_recovery_note(self) -> None:
        if self.context.recovery_note:
            self._append_log(self.context.recovery_note + "\n")
            self.summary_label.setText(self.context.recovery_note)

    def _poll_devices(self) -> None:
        devices = detect_devices()
        previous = self._selected_device()
        self._devices = devices
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        if not devices:
            self.device_combo.addItem("Nenhum Proxmark3 detectado", None)
        for device in devices:
            suffix = "" if device.confidence == Confidence.HIGH else " — identificação não confiável"
            self.device_combo.addItem(device.label + suffix, device.identity_key)
        chosen = -1
        wanted = self.context.prefs.selected_serial or (previous.identity_key if previous else "")
        if wanted:
            for index in range(self.device_combo.count()):
                if self.device_combo.itemData(index) == wanted:
                    chosen = index
                    break
        if chosen < 0 and devices:
            chosen = 0
        if chosen >= 0:
            self.device_combo.setCurrentIndex(chosen)
        self.device_combo.blockSignals(False)
        self._show_device(self._selected_device(), announce=not self._busy)
        if not self._busy:
            if not devices:
                self.set_status("Desconectado")
            elif self._selected_device() and self._selected_device().confidence == Confidence.HIGH:
                if self.status_pill.text() in {"Detectando", "Desconectado", "Erro"}:
                    self.set_status("Conectado")
            else:
                self.set_status("Conectado")

    def _selected_device(self) -> Device | None:
        key = self.device_combo.currentData() if hasattr(self, "device_combo") else None
        for device in self._devices:
            if device.identity_key == key:
                return device
        return None

    def _device_changed(self) -> None:
        device = self._selected_device()
        if device and device.serial_number:
            self.context.prefs.selected_serial = device.serial_number
        elif device:
            self.context.prefs.selected_serial = device.identity_key
        self.context.prefs.save()
        self._show_device(device, announce=True)

    def _show_device(self, device: Device | None, announce: bool) -> None:
        if device is None:
            self.device_labels["hardware"].setText("Proxmark3 não encontrado")
            self.device_labels["port"].setText("—")
            self.device_labels["usb"].setText("Desconectado")
            if announce and not self._busy:
                self.summary_label.setText(Msg.NOT_FOUND)
            self._update_actions()
            return
        self.device_labels["hardware"].setText(_hardware_caption(device, self.context.prefs))
        self.device_labels["port"].setText(device.port)
        confidence = "Alta" if device.confidence == Confidence.HIGH else "Não confiável"
        self.device_labels["usb"].setText(f"{confidence}. {device.reason}")
        if announce and not self._busy and device.confidence == Confidence.HIGH:
            self.summary_label.setText(Msg.detected(device.port))
        elif announce and not self._busy:
            self.summary_label.setText(Msg.MODEL_UNCONFIRMED)
        self._update_actions()

    def _refresh_config_text(self) -> None:
        module = self._selected_module()
        config = build_config(module.id if module else "LF_SAMYRUN", self.context.prefs)
        extras = " ".join(config.extras) if config.extras else "nenhum"
        size = f"PLATFORM_SIZE={config.platform_size}" if config.platform_size else "PLATFORM_SIZE não definido (o make usa 512)"
        standalone = module.id if module else "nenhum"
        repo_file = self.context.env.repo_root / "Makefile.platform"
        if repo_file.is_file():
            body = repo_file.read_text(encoding="utf-8", errors="replace")
            if "BEGIN Proxmark3 Standalone Manager" in body:
                internal = "presente na raiz do checkout e gerenciado por este aplicativo"
            else:
                internal = "presente na raiz do checkout, mas não foi gerado por este aplicativo"
        else:
            internal = "ausente na raiz do checkout; sem ele o make escolhe PM3RDV4"
        external = "não encontrado"
        if self.context.env.external_makefile_text:
            external = "existe em pm3/, fora do checkout; o make não lê esse arquivo"
        text = (
            f"PM3GENERIC, LED_ORDER=PM3EASY, extras: {extras}, {size}, "
            f"STANDALONE={standalone}. Repositório {self.context.env.repo_root.name} "
            f"({self.context.env.version}, {self.context.env.commit}). "
            f"Makefile.platform efetivo: {internal}. Arquivo externo: {external}."
        )
        self.device_labels["config"].setText(text)

    def _sync_hardware_controls(self) -> None:
        mcu = self.context.prefs.detected_mcu or ""
        small = "256" in mcu and "512" not in mcu
        large = "512" in mcu
        self.size_check.blockSignals(True)
        self.size_check.setEnabled(False)
        self.size_check.setChecked(small)
        self.size_check.blockSignals(False)
        wanted = True if small else False
        if (small or large or self.context.prefs.platform_size_256) and self.context.prefs.platform_size_256 != wanted:
            self.context.prefs.platform_size_256 = wanted
            self.context.prefs.save()
        self.spi_check.blockSignals(True)
        self.spi_check.setChecked(self.context.prefs.spi_flash_confirmada)
        self.spi_check.blockSignals(False)

    def _refresh_firmware_label(self) -> None:
        prefs = self.context.prefs
        if not any((prefs.detected_mcu, prefs.detected_external_flash, prefs.detected_standalone)):
            return
        self.device_labels["firmware"].setText(
            _firmware_text(
                {
                    "firmware": self.context.env.version,
                    "mcu": prefs.detected_mcu,
                    "flash_externa": prefs.detected_external_flash,
                    "flash_size": prefs.detected_flash_size,
                    "standalone": prefs.detected_standalone,
                }
            )
        )

    def _refresh_modules(self) -> None:
        selected = self._selected_module()
        modules = filter_modules(
            self.context.modules,
            self.search_box.text() if hasattr(self, "search_box") else "",
            self.category_combo.currentText() if hasattr(self, "category_combo") else "Todas",
        )
        self.module_table.setRowCount(len(modules))
        toolchain = self.service.toolchain
        for row, module in enumerate(modules):
            config = build_config(module.id, self.context.prefs)
            cache = self.context.cache.status(self.context.env, config, toolchain)
            values = (module.id, module.name, COMPATIBILITY_LABEL[module.compatibility], cache)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, module.id)
                self.module_table.setItem(row, column, item)
        self.module_table.resizeColumnsToContents()
        if selected:
            self._select_module(selected.id)
        self._module_changed()

    def _select_last_module(self) -> None:
        if self.context.prefs.last_module_id:
            self._select_module(self.context.prefs.last_module_id)

    def _select_module(self, module_id: str) -> None:
        for row in range(self.module_table.rowCount()):
            item = self.module_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == module_id:
                self.module_table.selectRow(row)
                return

    def _selected_module(self) -> Module | None:
        if not hasattr(self, "module_table"):
            return None
        row = self.module_table.currentRow()
        if row < 0:
            return None
        item = self.module_table.item(row, 0)
        if item is None:
            return None
        module_id = item.data(Qt.ItemDataRole.UserRole)
        for module in self.context.modules:
            if module.id == module_id:
                return module
        return None

    def _module_changed(self) -> None:
        module = self._selected_module()
        self.confirm_uncertain.blockSignals(True)
        if module is None:
            self.details.setPlainText("Selecione um módulo.")
            self.confirm_uncertain.setVisible(False)
        else:
            self.context.prefs.last_module_id = module.id
            self.context.prefs.save()
            lines = [
                module.id,
                module.name,
                "",
                module.description,
                "",
                f"Frequência: {module.frequency}",
                f"Categoria: {module.category.value}",
                f"Compatibilidade: {COMPATIBILITY_LABEL[module.compatibility]}",
                f"Requisitos: {module.hardware_requirements}",
                f"Arquivo: {module.source_file or 'não mapeado'}",
                "",
                "Limitações:",
                *[f"• {item}" for item in module.limitations],
                "",
                "Teste o modo Standalone apenas com tags próprias de laboratório, "
                "depois de desconectar o cabo USB. O comportamento de rádio não é provado pela gravação.",
            ]
            self.details.setPlainText("\n".join(lines))
            uncertain = module.compatibility == Compatibility.UNCERTAIN
            self.confirm_uncertain.setVisible(uncertain)
            self.confirm_uncertain.setChecked(module.id in self.context.prefs.confirmed_uncertain_modules)
        self.confirm_uncertain.blockSignals(False)
        self._refresh_config_text()
        self._update_actions()

    def _update_actions(self) -> None:
        module = self._selected_module()
        device = self._selected_device()
        allowed, reason = can_apply(module, self.context.prefs) if module else (False, "Selecione um módulo.")
        hardware_block = ""
        if allowed and module is not None and self.context.prefs.flash_autorizado:
            try:
                hardware_block = incompatible_flash(
                    self.context.prefs,
                    build_config(module.id, self.context.prefs),
                )
            except AppError:
                hardware_block = ""
        if hardware_block:
            notice = hardware_block
        elif not allowed:
            notice = reason
        elif self.context.prefs.flash_autorizado:
            notice = "A próxima operação Aplicar módulo gravará a fullimage real neste dispositivo."
        else:
            notice = "Gravação desligada. Aplicar módulo apenas compila."
        self.block_reason.setText(notice)
        self.authorize_check.setEnabled(not self._busy)
        self.apply_button.setEnabled((not self._busy) and allowed and not hardware_block)
        self.rebuild_button.setEnabled((not self._busy) and allowed)
        if hasattr(self, "proxspace_button"):
            self.proxspace_button.setEnabled(not self._busy)
            self.repo_combo.setEnabled(not self._busy)
        high = device is not None and device.confidence == Confidence.HIGH
        self.verify_button.setEnabled((not self._busy) and high)
        self.client_button.setEnabled((not self._busy) and high)
        self.logs_button.setEnabled(True)

    def _subtitle_text(self) -> str:
        return f"Versão {__version__}  ·  firmware {self.context.env.version}"

    def _populate_repo_combo(self) -> None:
        self.repo_combo.blockSignals(True)
        self.repo_combo.clear()
        names = list(self.context.env.available_repos) or [self.context.env.repo_root.name]
        for name in names:
            self.repo_combo.addItem(name)
        index = self.repo_combo.findText(self.context.env.repo_root.name)
        if index >= 0:
            self.repo_combo.setCurrentIndex(index)
        self.repo_combo.blockSignals(False)
        self.proxspace_label.setText(str(self.context.env.proxspace_root))
        if hasattr(self, "subtitle"):
            self.subtitle.setText(self._subtitle_text())

    def _choose_proxspace(self) -> None:
        if self._busy:
            return
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Selecionar a pasta do ProxSpace",
            self.context.prefs.proxspace_root or str(self.context.env.proxspace_root),
        )
        if not chosen:
            return
        self.context.prefs.proxspace_root = chosen
        self.context.prefs.repo_dirname = ""
        self.context.prefs.save()
        self._reload_context()

    def _repo_changed(self, name: str) -> None:
        if self._busy or not name or name == self.context.env.repo_root.name:
            return
        self.context.prefs.repo_dirname = name
        self.context.prefs.save()
        self._reload_context()

    def _reload_context(self) -> None:
        if self._busy:
            return
        try:
            fresh = AppContext.load()
        except AppError as exc:
            QMessageBox.critical(
                self,
                "Proxmark3 Standalone Manager",
                f"{exc.message}\n\nCódigo: {exc.code}\n\n{exc.technical}",
            )
            return
        self.context = fresh
        self._consume_authorization = False
        self.authorize_check.blockSignals(True)
        self.authorize_check.setChecked(False)
        self.authorize_check.blockSignals(False)
        self.service = ManagerService(
            fresh.env,
            fresh.prefs,
            fresh.shell,
            fresh.cache,
            fresh.lock,
            detect=detect_devices,
        )
        self._populate_repo_combo()
        self._refresh_modules()
        self._select_last_module()
        self._sync_hardware_controls()
        self._refresh_config_text()
        self._refresh_firmware_label()
        self.summary_label.setText(f"ProxSpace em uso: {fresh.env.proxspace_root}")

    def _spi_toggled(self, checked: bool) -> None:
        self.context.prefs.spi_flash_confirmada = checked
        self.context.prefs.spi_flash_recusada = not checked
        self.context.prefs.save()
        self._refresh_modules()
        self._refresh_config_text()

    def _size_toggled(self, checked: bool) -> None:
        mcu = self.context.prefs.detected_mcu or ""
        small = "256" in mcu and "512" not in mcu
        if checked and not small:
            self.size_check.blockSignals(True)
            self.size_check.setChecked(False)
            self.size_check.blockSignals(False)
            return
        self.context.prefs.platform_size_256 = checked
        self.context.prefs.save()
        self._refresh_config_text()

    def _uncertain_toggled(self, checked: bool) -> None:
        module = self._selected_module()
        if module is None:
            return
        confirmed = set(self.context.prefs.confirmed_uncertain_modules)
        if checked:
            confirmed.add(module.id)
        else:
            confirmed.discard(module.id)
        self.context.prefs.confirmed_uncertain_modules = sorted(confirmed)
        self.context.prefs.save()
        self._update_actions()

    def _authorize_toggled(self, checked: bool) -> None:
        if checked:
            answer = QMessageBox.question(
                self,
                "Autorizar gravação",
                "A gravação real envia somente a fullimage ao Proxmark3 conectado.\n"
                "O bootloader não será alterado e nenhuma recuperação forçada será feita.\n\n"
                "Esta autorização vale somente para a próxima operação Aplicar módulo.\n"
                "Essa operação grava o firmware real e não pede nova confirmação.\n"
                "Ao terminar, falhar ou ser desmarcada, a autorização é desligada.\n"
                "Ela não fica salva e não volta na próxima abertura do aplicativo.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._revoke_flash_authorization(update_summary=True)
                return
        self.context.prefs.flash_autorizado = checked
        self.context.prefs.save()
        if checked:
            self.summary_label.setText(
                "Gravação real autorizada só para o próximo Aplicar módulo. Essa operação grava a fullimage."
            )
        else:
            self.summary_label.setText("Gravação real desativada. Aplicar módulo apenas compila.")
        self._update_actions()

    def _revoke_flash_authorization(self, *, update_summary: bool) -> None:
        self.context.prefs.flash_autorizado = False
        self._consume_authorization = False
        self.context.prefs.save()
        self.authorize_check.blockSignals(True)
        self.authorize_check.setChecked(False)
        self.authorize_check.blockSignals(False)
        if update_summary:
            self.summary_label.setText("Gravação real desativada. Aplicar módulo apenas compila.")
            self._update_actions()

    def _apply(self) -> None:
        module = self._selected_module()
        if module is None:
            return
        authorized = bool(self.context.prefs.flash_autorizado)
        chosen = module
        device = self._selected_device()
        self._start(
            lambda on_log, on_stage, chosen=chosen, device=device, authorized=authorized: self.service.apply(
                chosen,
                device,
                force_rebuild=False,
                flash_authorized=authorized,
                on_stage=on_stage,
                on_log=on_log,
            ),
            consumes_authorization=authorized,
        )

    def _rebuild(self) -> None:
        module = self._selected_module()
        if module is None:
            return
        self._start(
            lambda on_log, on_stage: self.service.recompile(module, on_stage=on_stage, on_log=on_log),
            consumes_authorization=False,
        )

    def _verify(self) -> None:
        self._start(
            lambda on_log, on_stage: self.service.verify(self._selected_device(), on_stage=on_stage, on_log=on_log),
            consumes_authorization=False,
        )

    def _open_client(self) -> None:
        if self.context.lock.locked:
            self._show_result_message(Msg.BUSY, "E010", "warning")
            return
        device = self._selected_device()
        if device is None or device.confidence != Confidence.HIGH:
            self.summary_label.setText(Msg.NOT_FOUND if device is None else Msg.MODEL_UNCONFIRMED)
            return
        try:
            launch_client(self.context.env, device.port, self.context.shell.work_dir)
        except AppError as exc:
            self._append_log(f"{exc.message}\n{exc.technical}\n")
            self.summary_label.setText(exc.message)
            self.set_status("Erro")
            return
        self.summary_label.setText(f"Cliente aberto em {device.port}.")
        self._append_log(f"Cliente Proxmark3 solicitado em {device.port}.\n")

    def _show_logs(self) -> None:
        path = latest_log_file()
        dialog = QDialog(self)
        dialog.setWindowTitle("Logs")
        dialog.resize(760, 480)
        layout = QVBoxLayout(dialog)
        caption = QLabel(
            "Log operacional. Eventos de teste ficam em diretório separado e não entram neste arquivo."
        )
        caption.setWordWrap(True)
        caption.setObjectName("hint")
        layout.addWidget(caption)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setFont(QFont("Consolas", 10))
        if path.is_file():
            data = path.read_text(encoding="utf-8", errors="replace")
            view.setPlainText(data[-100_000:])
        else:
            view.setPlainText("Ainda não há log em disco.")
        layout.addWidget(view)
        button = QPushButton("Abrir pasta de logs")
        def _open_folder() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            os.startfile(path.parent)  # noqa: S606 - pasta local do aplicativo

        button.clicked.connect(_open_folder)
        layout.addWidget(button)
        dialog.exec()

    def _start(self, action, *, consumes_authorization: bool = False) -> None:
        if self._busy:
            self.summary_label.setText(Msg.BUSY)
            return
        self._consume_authorization = consumes_authorization
        self._busy = True
        self._update_actions()
        self.progress.setRange(0, 0)
        self._elapsed.start()
        self._clock.start()
        self._append_log("\n--- nova operação ---\n")
        self._worker = ServiceWorker(action)
        self._worker.log_ready.connect(self._append_log)
        self._worker.stage_changed.connect(self._on_stage)
        self._worker.completed.connect(self._finished)
        self._worker.start()

    def _on_stage(self, stage: str, status: str) -> None:
        self.stage_label.setText(f"Etapa: {stage}")
        if status in STATUS_COLORS:
            self.set_status(status)
        self._append_log(f"[{stage}]\n")

    def _finished(self, result) -> None:
        self._busy = False
        if self._consume_authorization:
            self._revoke_flash_authorization(update_summary=False)
        self._clock.stop()
        self.progress.setRange(0, 1)
        view = present_result(result, environment=environment_name())
        self.progress.setValue(0 if view.pending or not result.ok else 1)
        self.summary_label.setText(f"{result.message}  ({result.code})")
        self.stage_label.setText(f"Etapa: {result.stage or result.message}")
        self._append_log(f"{result.code}: {result.message}", kind=view.kind, label=view.label)
        if result.technical:
            self._append_log("Detalhe técnico:\n" + result.technical[-2000:])
        if result.details.get("firmware") or result.details.get("mcu"):
            self._sync_hardware_controls()
            self._refresh_firmware_label()
            self.device_labels["firmware"].setText(_firmware_text(result.details))
            device = self._selected_device()
            if device is not None:
                self.device_labels["hardware"].setText(_hardware_caption(device, self.context.prefs))
        if view.status:
            self.set_status(view.status)
        elif result.ok:
            self.set_status("Pronto" if self._selected_device() else "Desconectado")
        else:
            self.set_status("Erro")
        self._refresh_modules()
        self._update_actions()
        self._show_result_message(result.message, result.code, view.dialog)

    def _show_result_message(self, message: str, code: str, dialog: str = "information") -> None:
        boxes = {
            "warning": QMessageBox.warning,
            "critical": QMessageBox.critical,
            "information": QMessageBox.information,
        }
        boxes.get(dialog, QMessageBox.information)(
            self,
            "Proxmark3 Standalone Manager",
            f"{message}\n\nCódigo: {code}",
        )

    def _tick(self) -> None:
        seconds = self._elapsed.elapsed() // 1000
        self.elapsed_label.setText(f"Tempo decorrido: {seconds // 60:02d}:{seconds % 60:02d}")

    def _append_log(self, text: str, *, kind: str = "", label: str = "") -> None:
        if not text:
            return
        color = LOG_KIND_COLORS.get(kind, "#d7dde6")
        safe = html.escape(text.rstrip("\n")).replace("\n", "<br>")
        prefix = ""
        if label:
            prefix = f"<span style='color:{color};font-weight:700'>[{html.escape(label)}]</span> "
        self.log_view.append(
            f"<span style='color:#d7dde6;font-family:Consolas,monospace'>{prefix}{safe}</span>"
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if self._busy:
            QMessageBox.warning(
                self,
                "Operação em andamento",
                "Espere a compilação ou a gravação terminar antes de fechar.",
            )
            event.ignore()
            return
        event.accept()


def _hardware_caption(device: Device, prefs: Preferences) -> str:
    mcu = prefs.detected_mcu or ""
    flash = prefs.detected_external_flash or ""
    size = prefs.detected_flash_size or ""
    if "512" in mcu:
        flash_text = ""
        if flash:
            flash_text = f", flash SPI {flash}" + (f" {size}" if size else "")
        return (
            f"Proxmark3 — {mcu}{flash_text}. "
            "Modelo comercial não confirmado; não tratar como Easy de 256 KB nem como RDV4."
        )
    if "easy" in device.hardware_name.lower():
        return "Proxmark3 — o driver USB lista um perfil Easy. O MCU ainda não confirmou o modelo."
    return device.hardware_name


def _firmware_text(details: dict) -> str:
    parts = [str(details.get("firmware", "") or "")]
    mcu = str(details.get("mcu", "") or "")
    if mcu:
        parts.append(mcu)
    flash = str(details.get("flash_externa", "") or "")
    size = str(details.get("flash_size", "") or "")
    if flash:
        parts.append("flash SPI " + flash + (f" ({size})" if size else ""))
    if details.get("standalone"):
        banner = str(details["standalone"])
        if details.get("etapa_modulo") == "nao_confirmado" or details.get("validacao") == "parcial":
            parts.append(f"modo informado, não confirmado: {banner}")
        else:
            parts.append(banner)
    if "512" in mcu:
        parts.append("compilação PM3GENERIC sem PLATFORM_SIZE=256")
    return "; ".join(part for part in parts if part)


def _load_context_with_prompt() -> AppContext | None:
    while True:
        try:
            return AppContext.load()
        except AppError as exc:
            if exc.code != "E001":
                QMessageBox.critical(
                    None,
                    "Proxmark3 Standalone Manager",
                    f"{exc.message}\n\nCódigo: {exc.code}\n\n{exc.technical}",
                )
                return None
            answer = QMessageBox.question(
                None,
                "ProxSpace não encontrado",
                f"{exc.message}\n\n{exc.technical}\n\nDeseja selecionar a pasta do ProxSpace?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return None
            chosen = QFileDialog.getExistingDirectory(None, "Selecionar a pasta do ProxSpace")
            if not chosen:
                return None
            prefs = Preferences.load()
            prefs.proxspace_root = chosen
            prefs.save()


def run_gui() -> int:
    setup_logging()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    app.setApplicationName("Proxmark3 Standalone Manager")
    icon = resource_path("assets", "icon.ico")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    context = _load_context_with_prompt()
    if context is None:
        return 1
    window = MainWindow(context)
    if icon.is_file():
        window.setWindowIcon(QIcon(str(icon)))
    window.show()
    return app.exec()
