"""Abas de Diagnóstico e Manual. Offscreen, sem cliente Proxmark3 e sem gravação."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QPushButton

from pm3manager.diagnostics.analyze import analyze
from pm3manager.diagnostics.models import Observation
from tests.test_diagnostics import _observation
from tests.test_layout import _ancestor_scroll, _close, _inside, _show, _window


def test_abas_botoes_fixos_e_paineis(qapp, isolated_data, monkeypatch):
    window = _window(isolated_data, monkeypatch)
    try:
        _show(window, qapp, 800, 560)
        assert window.updates_panel.height() >= 96
        assert [window._pages.tabText(index) for index in range(window._pages.count())] == [
            "Operações",
            "Diagnóstico",
            "Manual",
        ]
        buttons = (
            window.apply_button,
            window.rebuild_button,
            window.verify_button,
            window.client_button,
            window.logs_button,
        )
        assert [button.text() for button in buttons] == [
            "Aplicar módulo",
            "Recompilar",
            "Verificar dispositivo",
            "Abrir cliente Proxmark3",
            "Visualizar logs",
        ]
        for button in buttons:
            assert _inside(button, window._operation_frame)
            assert _ancestor_scroll(button) is None
        assert window.manual_button.text() == "Ver manual do módulo"
        assert _ancestor_scroll(window.manual_button) is None
        window._pages.setCurrentWidget(window.diagnostics_panel)
        qapp.processEvents()
        labels = {button.text() for button in window.diagnostics_panel.findChildren(QPushButton)}
        assert {
            "Executar diagnóstico",
            "Atualizar informações",
            "Copiar resumo",
            "Exportar relatório",
            "Ver detalhes técnicos",
            "Cancelar",
        } <= labels
        window.resize(1280, 720)
        qapp.processEvents()
        assert window.diagnostics_panel.run_button.isVisible()
        window._pages.setCurrentWidget(window.guide_panel)
        qapp.processEvents()
        assert window.guide_panel.search.isVisible()
        assert window.guide_panel.filter_box.count() >= 8
        window.resize(800, 560)
        qapp.processEvents()
        assert window.updates_panel.height() >= 96 or not window.updates_panel.isVisible()
    finally:
        _close(window)


def test_manual_diagnostico_redimensionamento_e_worker(qapp, isolated_data, monkeypatch, tmp_path):
    window = _window(isolated_data, monkeypatch)
    try:
        _show(window, qapp, 1280, 720)
        window.search_box.setText("MATTY")
        qapp.processEvents()
        window.module_table.selectRow(0)
        qapp.processEvents()
        assert window._selected_module().id == "HF_MATTYRUN"
        assert window.rebuild_button.isEnabled() is True
        window.manual_button.click()
        qapp.processEvents()
        assert window._pages.currentWidget() is window.guide_panel
        assert window.guide_panel.selected_module_id == "HF_MATTYRUN"
        assert "HF_MATTYRUN" in window.guide_panel.detail.toPlainText()
        assert "não executa" in window.guide_panel.detail.toPlainText()
        for width, height in ((800, 560), (1920, 1080), (1024, 700)):
            window.resize(width, height)
            qapp.processEvents()
            assert window.guide_panel.selected_module_id == "HF_MATTYRUN"
            assert window.guide_panel.search.text() == ""
        window._pages.setCurrentIndex(0)
        qapp.processEvents()
        assert window.search_box.text() == "MATTY"
        assert window._selected_module().id == "HF_MATTYRUN"
        assert window.category_combo.currentText()

        entered = threading.Event()

        def collect(mode, cancel):
            entered.set()
            while not cancel.is_set():
                time.sleep(0.02)
            return Observation(
                generated_at="2026-10-27T12:00:00-03:00",
                app_version="2.0.0",
                mode=mode,
                client_cancelled=True,
            )

        window.diagnostics_panel.service.collect = collect
        window._pages.setCurrentWidget(window.diagnostics_panel)
        window.diagnostics_panel.run_button.click()
        assert entered.wait(2)
        pulsed = []
        QTimer.singleShot(0, lambda: pulsed.append(True))
        qapp.processEvents()
        assert pulsed == [True]
        assert window._diagnostic_busy is True
        assert window.rebuild_button.isEnabled() is False
        assert window.apply_button.isEnabled() is False
        assert window.logs_button.isEnabled() is True
        assert window.manual_button.isEnabled() is True
        window.diagnostics_panel.cancel_button.click()
        deadline = time.monotonic() + 4
        while window.diagnostics_panel._worker is not None and time.monotonic() < deadline:
            qapp.processEvents()
        assert window.diagnostics_panel._worker is None
        assert window.context.lock.locked is False
        assert window._diagnostic_busy is False
        assert window.rebuild_button.isEnabled() is True

        report = analyze(_observation())
        window.diagnostics_panel._finished(report)
        qapp.processEvents()
        assert window.diagnostics_panel.verdict.text() == report.verdict_label
        window.diagnostics_panel._copy()
        assert "consultivo" in qapp.clipboard().text().lower()
        target = tmp_path / "diagnostico.json"
        monkeypatch.setattr(
            "pm3manager.ui.diagnostics_panel.QFileDialog.getSaveFileName",
            lambda *args, **kwargs: (str(target), "JSON (*.json)"),
        )
        window.diagnostics_panel._export()
        exported = target.read_text(encoding="utf-8")
        assert "consultivo" in exported.lower()
        assert "pm3-flash" not in exported.lower()
        text_target = tmp_path / "diagnostico.txt"
        monkeypatch.setattr(
            "pm3manager.ui.diagnostics_panel.QFileDialog.getSaveFileName",
            lambda *args, **kwargs: (str(text_target), "Texto (*.txt)"),
        )
        window.diagnostics_panel._export()
        assert "Diagnóstico" in text_target.read_text(encoding="utf-8") or "diagnóstico" in text_target.read_text(encoding="utf-8").lower()

        def _close_details():
            for widget in qapp.topLevelWidgets():
                if isinstance(widget, QDialog) and widget.windowTitle() == "Detalhes do diagnóstico":
                    widget.accept()

        QTimer.singleShot(50, _close_details)
        window.diagnostics_panel._details()
        assert window.context.prefs.detected_mcu == ""
        assert window.context.prefs.flash_autorizado is False
    finally:
        _close(window)


def test_diagnostico_nao_entra_com_operacao_ocupada(qapp, isolated_data, monkeypatch):
    window = _window(isolated_data, monkeypatch)
    calls = []
    monkeypatch.setattr(
        "pm3manager.diagnostics.service.run_client",
        lambda *args, **kwargs: calls.append("cliente") or (0, "", False, False, "", ()),
    )
    try:
        _show(window, qapp, 1024, 700)
        assert window.context.lock.acquire("apply")
        window.diagnostics_panel.run_button.click()
        qapp.processEvents()
        assert "não foi iniciado" in window.diagnostics_panel.status.text()
        assert window.diagnostics_panel._worker is None
        assert calls == []
        assert window.context.lock.owner == "apply"
        window.context.lock.release()
        window._busy = True
        window.diagnostics_panel.start("full")
        qapp.processEvents()
        assert window.diagnostics_panel._worker is None
        assert calls == []
        window._busy = False
    finally:
        if window.context.lock.locked:
            window.context.lock.release()
        _close(window)
