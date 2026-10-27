"""Manual offline. O texto da ficha não vira HTML nem comando."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pm3manager.guide.catalog import build_cards, coverage, load_reviewed
from pm3manager.guide.models import FIELD_LABELS, FIELD_KEYS, ORIGIN_LABEL, REVIEW_LABEL, GuideDataError, ModuleCard
from pm3manager.guide.search import FILTERS, filter_cards
from pm3manager.guide.urls import is_allowed
from pm3manager.models import Module


class GuidePanel(QWidget):
    def __init__(self, modules: list[Module], path=None, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._cards: list[ModuleCard] = []
        self._visible: list[ModuleCard] = []
        self._selected_id = ""
        self._error = ""
        self._library = None
        self._build()
        self.set_modules(modules)

    def set_modules(self, modules: list[Module]) -> None:
        self._error = ""
        try:
            self._library = load_reviewed(self._path)
            self._cards = build_cards(modules, self._library)
            report = coverage(modules, self._library)
        except GuideDataError as exc:
            self._library = None
            self._cards = []
            self._error = str(exc)
            report = None
        if report is not None and report.unreviewed:
            self.notice.setText(
                "Há módulos no catálogo ainda sem ficha revisada: " + ", ".join(report.unreviewed)
            )
        elif self._error:
            self.notice.setText(self._error)
        else:
            self.notice.setText(
                "Manual offline. Abrir uma ficha não executa RFID e não consulta o GitHub."
            )
        self._apply_filter(keep=self._selected_id)

    def show_module(self, module_id: str) -> None:
        self._selected_id = module_id
        self.search.setText("")
        self.filter_box.setCurrentText("Todas")
        self._apply_filter(keep=module_id)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0)
        root.setSpacing(8)
        self.notice = QLabel("Manual offline.")
        self.notice.setWordWrap(True)
        self.notice.setObjectName("hint")
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.notice)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Pesquisar no manual")
        self.search.textChanged.connect(lambda: self._apply_filter(keep=self._selected_id))
        self.filter_box = QComboBox()
        self.filter_box.addItems(list(FILTERS))
        self.filter_box.currentTextChanged.connect(lambda: self._apply_filter(keep=self._selected_id))
        root.addWidget(self.search)
        root.addWidget(self.filter_box)
        body = QHBoxLayout()
        self.module_list = QListWidget()
        self.module_list.currentRowChanged.connect(self._row_changed)
        body.addWidget(self.module_list, 1)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlainText("Selecione um módulo.")
        body.addWidget(self.detail, 2)
        root.addLayout(body, 1)
        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copiar ficha")
        self.open_button = QPushButton("Abrir referência")
        self.reference_box = QComboBox()
        self.copy_button.setMinimumHeight(32)
        self.open_button.setMinimumHeight(32)
        self.copy_button.clicked.connect(self._copy)
        self.open_button.clicked.connect(self._open)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.reference_box, 1)
        buttons.addWidget(self.open_button)
        root.addLayout(buttons)

    def _apply_filter(self, keep: str = "") -> None:
        self._visible = filter_cards(self._cards, self.search.text(), self.filter_box.currentText())
        self.module_list.blockSignals(True)
        self.module_list.clear()
        for card in self._visible:
            self.module_list.addItem(f"{card.module_id} — {card.friendly_name}")
        chosen = 0 if self._visible else -1
        for index, card in enumerate(self._visible):
            if card.module_id == keep:
                chosen = index
                break
        if chosen >= 0:
            self.module_list.setCurrentRow(chosen)
        self.module_list.blockSignals(False)
        self._show(self._visible[chosen] if chosen >= 0 else None)

    def _row_changed(self, row: int) -> None:
        card = self._visible[row] if 0 <= row < len(self._visible) else None
        if card is not None:
            self._selected_id = card.module_id
        self._show(card)

    def _show(self, card: ModuleCard | None) -> None:
        self.reference_box.clear()
        if card is None:
            self.detail.setPlainText("Nenhuma ficha para o filtro atual.")
            self.open_button.setEnabled(False)
            return
        lines = [
            card.module_id,
            card.friendly_name,
            f"Estado da documentação: {REVIEW_LABEL.get(card.review_state, card.review_state)}",
            f"Classificação já usada pelo aplicativo: {card.catalog_compatibility}",
            "O manual não altera essa classificação.",
            "",
            "Como utilizar",
            card.fields["start"].value,
            card.fields["functions"].value,
            "",
            card.responsible_use,
            "",
        ]
        for key in FIELD_KEYS:
            field = card.fields[key]
            lines.append(FIELD_LABELS[key])
            lines.append(field.value)
            lines.append(f"Origem: {ORIGIN_LABEL.get(field.origin, field.origin)}. {field.justification}")
            if field.source:
                lines.append(f"Fonte: {field.source}")
            lines.append("")
        lines.append("Fontes")
        if card.checkout_commit:
            lines.append(f"Commit do checkout analisado: {card.checkout_commit}")
        lines.append(f"Revisão: {card.reviewed_on or 'não revisada'}")
        for item in card.references:
            lines.append(item.label)
            if item.path:
                lines.append(item.path)
            if item.url:
                lines.append(item.url)
            self.reference_box.addItem(item.label, item.url)
        self.detail.setPlainText("\n".join(lines))
        self.open_button.setEnabled(self.reference_box.count() > 0)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.detail.toPlainText())

    def _open(self) -> None:
        url = str(self.reference_box.currentData() or "")
        if not is_allowed(url):
            self.notice.setText("A referência não é uma URL permitida. Nenhum endereço foi aberto.")
            return
        QDesktopServices.openUrl(QUrl(url))

    @property
    def selected_module_id(self) -> str:
        return self._selected_id
