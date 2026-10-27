# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-dir, sem console.

As bibliotecas Qt ficam como arquivos comuns em ``_internal``. UPX fica
desligado para que esses arquivos continuem sendo PE normais, substituíveis
no lugar. O marcador ``.pm3manager-root`` não entra no pacote.
"""
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "pm3manager" / "__main__.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "assets" / "icon.ico"), "assets"),
        (str(root / "pm3manager" / "guide" / "data" / "reviewed.json"), "pm3manager/guide/data"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebView",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtMultimedia",
        "PySide6.QtBluetooth",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtGraphs",
        "PySide6.QtLocation",
        "PySide6.QtPositioning",
        "PySide6.QtRemoteObjects",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtTextToSpeech",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Proxmark3StandaloneManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="_internal",
    icon=[str(root / "assets" / "icon.ico")],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Proxmark3StandaloneManager",
)
