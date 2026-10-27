"""Filtros e indicador de compatibilidade. Offscreen, sem leitura de hardware."""

from __future__ import annotations

from PySide6.QtWidgets import QScrollArea

from tests.test_layout import _ancestor_scroll, _close, _inside, _show, _window


def test_filtro_preserva_tabela_botoes_e_catalogo(qapp, isolated_data, monkeypatch):
    window = _window(isolated_data, monkeypatch)
    try:
        _show(window, qapp, 1280, 720)
        assert window.compatibility_filter.objectName() == "compatibilityFilter"
        assert window.compatibility_filter.currentData() == "todos"
        assert "não identificado" in window.device_identity.text() or "Proxmark3" in window.device_identity.text()
        total = window.module_table.rowCount()
        assert total >= 3
        table_id = id(window.module_table)
        labels = [window.compatibility_filter.itemText(index) for index in range(window.compatibility_filter.count())]
        assert "Todos" in labels
        assert "Compatíveis" in labels
        assert "Incompatíveis" in labels
        window.compatibility_filter.setCurrentIndex(window.compatibility_filter.findData("incompativeis"))
        qapp.processEvents()
        assert id(window.module_table) == table_id
        marker = window.module_table.item(0, 2).text() if window.module_table.rowCount() else ""
        if marker:
            assert any(token in marker for token in ("Incompatível", "Indisponível", "insuficientes", "confirmação", "Compatível"))
        window.compatibility_filter.setCurrentIndex(window.compatibility_filter.findData("todos"))
        qapp.processEvents()
        assert window.module_table.rowCount() == total
        for button in (
            window.apply_button,
            window.rebuild_button,
            window.verify_button,
            window.client_button,
            window.logs_button,
        ):
            assert _inside(button, window._operation_frame)
            assert _ancestor_scroll(button) is None
        assert not _inside(window.diagnosis_button, window._operation_frame)
        assert isinstance(window.diagnosis_button.parentWidget(), type(window.manual_button.parentWidget()))
        window.diagnosis_button.click()
        qapp.processEvents()
        assert window._pages.currentWidget() is window.diagnostics_panel
        window._pages.setCurrentIndex(0)
        qapp.processEvents()
        for width, height in ((1366, 768), (1600, 900), (1920, 1080), (2560, 1440)):
            window.resize(width, height)
            qapp.processEvents()
            assert window.apply_button.isVisible()
            assert _ancestor_scroll(window.apply_button) is None
            assert not isinstance(window._operation_frame.parentWidget(), QScrollArea)
    finally:
        _close(window)
