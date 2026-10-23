"""Layout da janela V2. Offscreen, sem GitHub, sem Proxmark3 e sem gravação."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QMessageBox, QScrollArea

from pm3manager.cache.store import FirmwareCache
from pm3manager.models import Category, Compatibility, Module
from pm3manager.paths import project_root
from pm3manager.preferences import Preferences
from pm3manager.proxspace.shell import ProxSpaceShell
from pm3manager.workflow.context import AppContext
from pm3manager.workflow.lock import OperationLock
from tests.fakes import make_env, module


def _catalog_modules() -> list[Module]:
    raw = json.loads((project_root() / "catalog" / "modulos.json").read_text(encoding="utf-8"))
    modules = []
    for item in raw:
        modules.append(
            Module(
                id=item["id"],
                name=item["nome"],
                description=item["descricao"],
                frequency=item["frequencia"],
                category=Category(item["categoria"]),
                compatibility=Compatibility(item["compatibilidade"]),
                hardware_requirements=item.get("requisitos", ""),
                limitations=tuple(item.get("limitacoes") or ()),
                hal_description="",
                doc_hardware="",
                requires_flash=bool(item.get("requer_flash", False)),
                requires_bt=bool(item.get("requer_bt", False)),
                requires_smartcard=bool(item.get("requer_smartcard", False)),
                rdv4_only=bool(item.get("exclusivo_rdv4", False)),
                source_file=item.get("fonte", ""),
            )
        )
    return modules


def _window(isolated_data, monkeypatch, modules=None):
    monkeypatch.setattr("pm3manager.ui.main_window.detect_devices", lambda: [])
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    env = make_env(isolated_data)
    prefs = Preferences()
    context = AppContext(
        env=env,
        prefs=prefs,
        modules=modules if modules is not None else _catalog_modules(),
        shell=ProxSpaceShell(env, isolated_data / "work"),
        cache=FirmwareCache(isolated_data / "firmware-cache"),
        lock=OperationLock(),
    )
    from pm3manager.ui.main_window import MainWindow

    return MainWindow(context)


def _close(window) -> None:
    window._poll.stop()
    if not window.updates_panel._closed:
        window.close()
    if not window.updates_panel._closed:
        window.updates_panel.shutdown()


def _show(window, qapp, width: int, height: int) -> None:
    window.resize(width, height)
    window.show()
    qapp.processEvents()
    QTest.qWait(30)
    qapp.processEvents()


def _global_rect(widget) -> QRect:
    return QRect(widget.mapToGlobal(widget.rect().topLeft()), widget.size())


def _overlap_area(left, right) -> int:
    if left is right or not left.isVisible() or not right.isVisible():
        return 0
    if left.isAncestorOf(right) or right.isAncestorOf(left):
        return 0
    inter = _global_rect(left).intersected(_global_rect(right))
    if inter.width() <= 2 or inter.height() <= 2:
        return 0
    return inter.width() * inter.height()


def _assert_no_overlap(pairs) -> None:
    problems = []
    for left, right, name in pairs:
        area = _overlap_area(left, right)
        if area:
            problems.append(f"{name}={area}")
    assert not problems, "; ".join(problems)


def _assert_wrapped(labels) -> None:
    short = []
    for name, label in labels:
        if not isinstance(label, QLabel) or not label.wordWrap() or not label.isVisible():
            continue
        if label.width() < 20 or not label.text().strip():
            continue
        needed = label.heightForWidth(label.width())
        if label.height() + 2 < needed:
            short.append(f"{name} tem {label.height()}px e precisa de {needed}px")
    assert not short, "; ".join(short)


def test_janela_pequena_mantem_paineis_e_rolagem(qapp, isolated_data, monkeypatch):
    window = _window(isolated_data, monkeypatch)
    try:
        assert window.minimumSize().width() == window.WINDOW_MIN_WIDTH == 760
        assert window.minimumSize().height() == window.WINDOW_MIN_HEIGHT == 520
        _show(window, qapp, 800, 560)
        assert window._top_split.orientation() == Qt.Orientation.Vertical
        assert window.updates_panel.isVisible()
        assert window.updates_panel.maximumHeight() > 2000
        assert window.updates_panel.height() >= 120
        device_bar = window._device_scroll.verticalScrollBar()
        assert device_bar.maximum() > 0 or window._device_scroll.widget().height() > window._device_scroll.viewport().height()
        window._device_scroll.ensureWidgetVisible(window.spi_check)
        window._device_scroll.ensureWidgetVisible(window.size_check)
        qapp.processEvents()
        assert window.spi_check.isEnabled()
        assert window.size_check.isEnabled() is False
        assert window.spi_check.accessibleName() == "Confirmo que esta placa tem memória flash SPI externa"
        assert "PLATFORM_SIZE=256" in window.size_check.accessibleName()
        assert window._device_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    finally:
        _close(window)


def test_textos_de_hardware_nao_sobrepoem_as_confirmacoes(qapp, isolated_data, monkeypatch):
    window = _window(isolated_data, monkeypatch, modules=[module("HF_MATTYRUN"), module("LF_SAMYRUN")])
    try:
        _show(window, qapp, 1280, 720)
        window.device_labels["hardware"].setText("Proxmark3 — AT91SAM7S512, flash SPI 2048 Kb. " * 8)
        window.device_labels["config"].setText(
            "PM3GENERIC, LED_ORDER=PM3EASY, PLATFORM_SIZE não definido. " * 8
        )
        window.device_labels["firmware"].setText("Iceman/master/v4.23346; AT91SAM7S512; " * 6)
        qapp.processEvents()
        window._fit_wrapped_text(window._device_scroll)
        qapp.processEvents()
        _assert_wrapped((key, label) for key, label in window.device_labels.items())
        spi_label = window.spi_check.parentWidget().findChild(QLabel, "checkText")
        size_label = window.size_check.parentWidget().findChild(QLabel, "checkText")
        _assert_no_overlap(
            [
                (window.device_labels["hardware"], window.spi_check, "hardware/spi"),
                (window.device_labels["hardware"], window.size_check, "hardware/size"),
                (window.device_labels["firmware"], window.spi_check, "firmware/spi"),
                (window.device_labels["config"], window.size_check, "config/size"),
                (window.proxspace_button, window.spi_check, "proxspace/spi"),
                (window.spi_check, window.size_check, "spi/size"),
                (spi_label, size_label, "rotulos"),
            ]
        )
        assert spi_label.text().startswith("Confirmo que esta placa tem memória flash SPI")
        assert "256" in size_label.text()
    finally:
        _close(window)


def test_lista_de_modulos_prioriza_rolagem_vertical(qapp, isolated_data, monkeypatch):
    modules = _catalog_modules()
    assert len(modules) == 41
    window = _window(isolated_data, monkeypatch, modules=modules)
    try:
        _show(window, qapp, 1280, 720)
        assert window.module_table.rowCount() == 41
        assert window.module_table.horizontalScrollBar().maximum() == 0
        names = []
        for row in range(window.module_table.rowCount()):
            name_item = window.module_table.item(row, 1)
            id_item = window.module_table.item(row, 0)
            assert name_item.toolTip().startswith(name_item.text())
            assert id_item.text() in name_item.toolTip() or name_item.text() in name_item.toolTip()
            assert name_item.text()
            names.append(id_item.text())
        assert "HF_MATTYRUN" in names
        window.search_box.setText("MATTY")
        qapp.processEvents()
        shown = [window.module_table.item(row, 0).text() for row in range(window.module_table.rowCount())]
        assert shown == ["HF_MATTYRUN"]
        window.module_table.selectRow(0)
        selected = window.module_table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        table_id = id(window.module_table)
        window.category_combo.setCurrentText("High Frequency (HF)")
        window.search_box.setText("")
        qapp.processEvents()
        hf = [window.module_table.item(row, 0).text() for row in range(window.module_table.rowCount())]
        assert "HF_MATTYRUN" in hf
        assert "LF_SAMYRUN" not in hf
        for width, height in ((1366, 768), (1600, 900), (1920, 1080), (2560, 1440), (800, 600)):
            window.resize(width, height)
            qapp.processEvents()
            assert id(window.module_table) == table_id
            assert window.module_table.horizontalScrollBar().maximum() == 0
        assert window.search_box.text() == ""
        assert window.category_combo.currentText() == "High Frequency (HF)"
        assert window._selected_module() is not None
        assert window._selected_module().id == selected == "HF_MATTYRUN"
        window.resize(820, 640)
        qapp.processEvents()
        assert window._top_split.orientation() == Qt.Orientation.Vertical
        assert id(window.module_table) == table_id
        window.resize(1440, 900)
        qapp.processEvents()
        assert window._top_split.orientation() == Qt.Orientation.Horizontal
        assert window.category_combo.currentText() == "High Frequency (HF)"
    finally:
        _close(window)


def test_atualizacoes_operacoes_e_estado_apos_redimensionar(qapp, isolated_data, monkeypatch):
    modules = _catalog_modules()
    window = _window(isolated_data, monkeypatch, modules=modules)
    checks = []

    def forbidden(*args, **kwargs):
        checks.append("rede")
        raise AssertionError("redimensionar não pode consultar o GitHub")

    window.updates_panel.service.check = forbidden
    try:
        _show(window, qapp, 1366, 768)
        assert window.updates_panel.height() >= 140
        for caption in ("Iceman", "ProxSpace", "Atualizações"):
            assert any(label.text() == caption for label in window.findChildren(QLabel))
        for caption in (
            "Verificar atualizações",
            "Ver alterações",
            "Abrir no GitHub",
            "Configurações",
            "Ver instruções de atualização",
        ):
            button = next(item for item in window.updates_panel.findChildren(type(window.apply_button)) if item.text() == caption)
            assert button.minimumHeight() >= 32
            assert button.isVisible()
        for button in (
            window.apply_button,
            window.rebuild_button,
            window.verify_button,
            window.client_button,
            window.logs_button,
        ):
            assert button.minimumHeight() >= 32
            assert button.text()
        assert window.apply_button.text() == "Aplicar módulo"
        assert "Recompilar e Verificar dispositivo não gravam." in window._operation_scroll.widget().findChild(QLabel).text() or any(
            "não gravam" in label.text() for label in window._operation_scroll.findChildren(QLabel)
        )
        _assert_no_overlap(
            [
                (window.apply_button, window.rebuild_button, "aplicar/recompilar"),
                (window.rebuild_button, window.verify_button, "recompilar/verificar"),
                (window.verify_button, window.client_button, "verificar/cliente"),
                (window.client_button, window.logs_button, "cliente/logs"),
            ]
        )
        window._operation_scroll.ensureWidgetVisible(window.apply_button)
        qapp.processEvents()
        assert window.context.prefs.flash_autorizado is False
        assert window.authorize_check.isChecked() is False
        window.search_box.setText("REBLAY")
        qapp.processEvents()
        window.module_table.selectRow(0)
        window.spi_check.setChecked(True)
        qapp.processEvents()
        chosen = window._selected_module().id
        for width, height in ((1920, 1080), (800, 560), (1280, 720)):
            before = window.updates_panel._checking
            window.resize(width, height)
            qapp.processEvents()
            assert window.updates_panel._checking is before
            assert window.search_box.text() == "REBLAY"
            assert window.spi_check.isChecked() is True
            assert window.context.prefs.spi_flash_confirmada is True
            assert window.context.prefs.flash_autorizado is False
            if chosen:
                assert window._selected_module() is not None
                assert window._selected_module().id == chosen
        assert checks == []
        assert window.log_view.minimumHeight() >= 64
        assert window._progress_split.sizes()[1] >= 48
        assert isinstance(window._progress_scroll, QScrollArea)
        window._poll.stop()
        window.close()
        assert window.updates_panel._closed is True
        assert window.updates_panel._timer.isActive() is False
        assert window.updates_panel._worker is None or window.updates_panel._worker.isRunning() is False
    finally:
        _close(window)


def test_divisor_ignora_tamanhos_invalidos_e_restaura_os_validos(qapp, isolated_data, monkeypatch):
    window = _window(isolated_data, monkeypatch, modules=[module()])
    try:
        window.context.prefs.ui_main_split = "0,0,0"
        window.context.prefs.ui_top_split = "nope"
        window.context.prefs.ui_top_split_narrow = "-5,10,10"
        _show(window, qapp, 1280, 720)
        assert all(item >= 48 for item in window._main_split.sizes())
        assert all(item >= 48 for item in window._top_split.sizes())
        assert len(window._main_split.sizes()) == 3
    finally:
        _close(window)

    restored = _window(isolated_data, monkeypatch, modules=[module()])
    try:
        restored.context.prefs.ui_main_split = "500,250,250"
        restored.context.prefs.ui_top_split = "300,400,300"
        _show(restored, qapp, 1600, 900)
        main = restored._main_split.sizes()
        assert abs((main[0] / sum(main)) - 0.5) < 0.15
        top = restored._top_split.sizes()
        assert top[1] >= top[0]
        assert top[1] >= top[2]
    finally:
        _close(restored)


def test_escalas_do_windows_nao_quebram_o_layout(tmp_path):
    probe = tmp_path / "probe_layout.py"
    probe.write_text(
        """
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from pm3manager.cache.store import FirmwareCache
from pm3manager.preferences import Preferences
from pm3manager.proxspace.shell import ProxSpaceShell
from pm3manager.ui.main_window import MainWindow
from pm3manager.workflow.context import AppContext
from pm3manager.workflow.lock import OperationLock
from tests.fakes import make_env, module

root = sys.argv[1]
app = QApplication([])
QMessageBox.warning = staticmethod(lambda *args, **kwargs: None)
QMessageBox.critical = staticmethod(lambda *args, **kwargs: None)
QMessageBox.information = staticmethod(lambda *args, **kwargs: None)
import pm3manager.ui.main_window as ui

ui.detect_devices = lambda: []
env = make_env(__import__("pathlib").Path(root))
prefs = Preferences()
context = AppContext(
    env=env,
    prefs=prefs,
    modules=[module("HF_MATTYRUN"), module("LF_SAMYRUN")],
    shell=ProxSpaceShell(env, __import__("pathlib").Path(root) / "work"),
    cache=FirmwareCache(__import__("pathlib").Path(root) / "cache"),
    lock=OperationLock(),
)
window = MainWindow(context)
try:
    for width, height in ((1280, 720), (800, 560)):
        window.resize(width, height)
        window.show()
        app.processEvents()
        hardware = window.device_labels["hardware"]
        hardware.setText("AT91SAM7S512 com flash SPI externa de 2048 Kb. " * 6)
        app.processEvents()
        window._fit_wrapped_text(window._device_scroll)
        app.processEvents()
        needed = hardware.heightForWidth(hardware.width())
        if hardware.width() > 20 and hardware.height() + 2 < needed:
            raise SystemExit(f"texto cortado em {width}x{height}: {hardware.height()} < {needed}")
        if window.spi_check.accessibleName() == "":
            raise SystemExit("checkbox da flash sem nome")
        if window.updates_panel.height() < 100:
            raise SystemExit(f"atualizacoes baixas: {window.updates_panel.height()}")
        if window.module_table.rowCount() != 2:
            raise SystemExit("modulos sumiram")
finally:
    window._poll.stop()
    window.close()
print("ok")
""",
        encoding="utf-8",
    )
    env_base = os.environ.copy()
    env_base["QT_QPA_PLATFORM"] = "offscreen"
    env_base["PM3MANAGER_ENV"] = "teste"
    env_base["PYTHONPATH"] = str(project_root()) + os.pathsep + env_base.get("PYTHONPATH", "")
    env_base["PYTHONIOENCODING"] = "utf-8"
    for scale in ("1", "1.25", "1.5"):
        data = tmp_path / f"scale-{scale}"
        data.mkdir()
        env = env_base.copy()
        env["QT_SCALE_FACTOR"] = scale
        env["PM3MANAGER_DATA_DIR"] = str(data / "data")
        env["PM3MANAGER_LOG_DIR"] = str(data / "logs")
        completed = subprocess.run(
            [sys.executable, str(probe), str(data)],
            cwd=str(project_root()),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        assert completed.returncode == 0, f"escala {scale}\n{completed.stdout}\n{completed.stderr}"
        assert "ok" in completed.stdout
