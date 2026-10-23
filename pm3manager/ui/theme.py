"""Tema escuro. O texto fica claro o bastante para leitura contínua do log."""

STYLESHEET = """
QWidget {
    background: #171a1f;
    color: #e6e8eb;
    font-family: "Segoe UI";
    font-size: 13px;
}
QMainWindow, QDialog {
    background: #171a1f;
}
QFrame#card {
    background: #21262e;
    border: 1px solid #323844;
    border-radius: 10px;
}
QLabel#title {
    font-size: 20px;
    font-weight: 650;
    background: transparent;
}
QLabel#muted, QLabel#hint, QLabel#value, QLabel#section, QLabel#checkText {
    background: transparent;
}
QLabel#muted, QLabel#hint {
    color: #a8b0bb;
}
QLabel#section {
    color: #d5dbe3;
    font-weight: 650;
    padding-top: 6px;
}
QLabel#checkText, QLabel#value {
    color: #e6e8eb;
}
QWidget#checkRow {
    background: transparent;
}
QLabel#statusPill {
    background: #2a3140;
    border-radius: 10px;
    padding: 4px 10px;
    font-weight: 600;
}
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QTextBrowser, QListWidget, QTableWidget {
    background: #12151a;
    border: 1px solid #3a4250;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #2f6fed;
}
QTableWidget {
    gridline-color: #2c3340;
    alternate-background-color: #1a1f27;
}
QTableWidget::item:selected {
    background: #2f6fed;
    color: #f4f7fb;
}
QHeaderView::section {
    background: #1c212a;
    color: #c5ccd6;
    border: none;
    padding: 6px;
}
QPushButton {
    background: #2a3140;
    border: 1px solid #3d4656;
    border-radius: 6px;
    padding: 8px 12px;
}
QPushButton:hover {
    background: #343d4e;
}
QPushButton#primary {
    background: #2f6fed;
    border: none;
    font-weight: 650;
}
QPushButton#primary:hover {
    background: #4b83f1;
}
QPushButton:disabled {
    color: #7d8694;
    background: #232830;
}
QProgressBar {
    background: #12151a;
    border: 1px solid #3a4250;
    border-radius: 6px;
    height: 14px;
    text-align: center;
}
QProgressBar::chunk {
    background: #2f6fed;
    border-radius: 5px;
}
QCheckBox {
    background: transparent;
    spacing: 8px;
}
QSplitter::handle:horizontal {
    width: 8px;
    background: #171a1f;
}
QSplitter::handle:vertical {
    height: 8px;
    background: #171a1f;
}
QFrame#card QScrollArea {
    background: transparent;
    border: none;
}
QFrame#card QScrollArea > QWidget > QWidget,
QFrame#card QWidget#qt_scrollarea_viewport {
    background: transparent;
    border: none;
}
"""

STATUS_COLORS = {
    "Desconectado": "#8b95a5",
    "Detectando": "#7eb6ff",
    "Conectado": "#3ddecb",
    "Verificando": "#7eb6ff",
    "Pronto": "#3dd68c",
    "Compilando": "#e0b15a",
    "Gravando": "#e0b15a",
    "Validando": "#7eb6ff",
    "Validação parcial": "#e0b15a",
    "Validação concluída": "#3dd68c",
    "Falha crítica": "#ff6b6b",
    "Aviso": "#e0b15a",
    "Erro": "#f07178",
}

LOG_KIND_COLORS = {
    "informacao": "#7eb6ff",
    "aviso": "#e0b15a",
    "erro": "#f07178",
    "critico": "#ff6b6b",
    "teste": "#c4b5fd",
    "parcial": "#e0b15a",
    "concluida": "#3dd68c",
}
