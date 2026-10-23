"""One-dir layout, data paths, and the local validation package.

Tests that need the built executable skip themselves when ``dist`` is absent,
so a checkout without a build can still run. They are not a substitute for
the LGPL: a DLL that exists as a file is not compliance.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

import pm3manager
from pm3manager.paths import data_dir, is_development_tree, project_root
from pm3manager.workflow.context import export_development_catalog

ONEDIR = project_root() / "dist" / "Proxmark3StandaloneManager"
ONEDIR_EXE = ONEDIR / "Proxmark3StandaloneManager.exe"
ZIP_NAME = f"Proxmark3StandaloneManager-v{pm3manager.__version__}-windows-x64.zip"
ZIP_PATH = project_root() / "dist" / ZIP_NAME


def _freeze(monkeypatch, exe: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.delenv("PM3MANAGER_DATA_DIR", raising=False)


def test_one_dir_de_desenvolvimento_continua_em_var(monkeypatch, tmp_path):
    project = tmp_path / "projeto"
    exe_dir = project / "dist" / "Proxmark3StandaloneManager"
    exe_dir.mkdir(parents=True)
    exe = exe_dir / "Proxmark3StandaloneManager.exe"
    exe.write_bytes(b"MZ")
    (project / ".pm3manager-root").write_text("marker", encoding="utf-8")
    _freeze(monkeypatch, exe)
    assert project_root() == project
    assert is_development_tree() is True
    assert data_dir() == project / "var"
    assert not (exe_dir / "var").exists()


def test_one_file_de_desenvolvimento_ainda_acha_o_marcador(monkeypatch, tmp_path):
    project = tmp_path / "projeto"
    dist = project / "dist"
    dist.mkdir(parents=True)
    exe = dist / "Proxmark3StandaloneManager.exe"
    exe.write_bytes(b"MZ")
    (project / ".pm3manager-root").write_text("marker", encoding="utf-8")
    _freeze(monkeypatch, exe)
    assert project_root() == project
    assert is_development_tree() is True


def test_copia_publica_usa_o_perfil_e_nao_a_pasta_do_exe(monkeypatch, tmp_path):
    public = tmp_path / "Tools" / "Proxmark3StandaloneManager"
    public.mkdir(parents=True)
    exe = public / "Proxmark3StandaloneManager.exe"
    exe.write_bytes(b"MZ")
    _freeze(monkeypatch, exe)
    profile = tmp_path / "perfil"
    monkeypatch.setattr("pm3manager.paths.user_config_dir", lambda: profile)
    assert project_root() == public
    assert is_development_tree() is False
    assert data_dir() == profile
    assert profile.is_dir()
    assert not (public / "var").exists()
    assert not (public / "preferences.json").exists()


def test_marcador_nao_e_procurado_alem_do_avo(monkeypatch, tmp_path):
    project = tmp_path / "projeto"
    exe_dir = project / "extra" / "nivel" / "app"
    exe_dir.mkdir(parents=True)
    exe = exe_dir / "Proxmark3StandaloneManager.exe"
    exe.write_bytes(b"MZ")
    (project / ".pm3manager-root").write_text("marker", encoding="utf-8")
    _freeze(monkeypatch, exe)
    assert project_root() == exe_dir
    assert is_development_tree() is False


def test_catalogo_de_desenvolvimento_nao_sai_na_copia_publica(monkeypatch, tmp_path):
    calls: list[Path] = []

    def remember(modules, path):
        calls.append(Path(path))

    monkeypatch.setattr("pm3manager.workflow.context.export_catalog", remember)
    monkeypatch.setattr("pm3manager.workflow.context.is_development_tree", lambda: False)
    export_development_catalog([])
    assert calls == []
    monkeypatch.setattr("pm3manager.workflow.context.is_development_tree", lambda: True)
    monkeypatch.setattr("pm3manager.workflow.context.project_root", lambda: tmp_path)
    export_development_catalog([])
    assert calls == [tmp_path / "catalog" / "modulos.json"]


def test_aplicacao_nao_fixa_o_hash_das_dlls_qt():
    for path in (project_root() / "pm3manager").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "Qt6Core" not in text
        assert "sha256" not in text.lower() or "Qt6" not in text


def _require_built() -> Path:
    if not ONEDIR_EXE.is_file():
        pytest.skip("one-dir executable is not built")
    return ONEDIR_EXE


def _child_env(data: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "PM3MANAGER_LOG_DIR",
        "PM3MANAGER_ENV",
        "PM3MANAGER_PROXSPACE",
        "PROXSPACE",
        "PYTEST_CURRENT_TEST",
    ):
        env.pop(key, None)
    env["PM3MANAGER_DATA_DIR"] = str(data)
    return env


def _run_exe(exe: Path, data: Path, timeout: float = 90) -> subprocess.CompletedProcess[str]:
    data.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [str(exe), "--self-check"],
        cwd=str(exe.parent),
        env=_child_env(data),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@pytest.fixture(scope="module")
def copia_com_espaco():
    if not ONEDIR_EXE.is_file():
        pytest.skip("one-dir executable is not built")
    base = Path(tempfile.mkdtemp(prefix="PM3 Manager "))
    dest = base / "Proxmark3StandaloneManager"
    shutil.copytree(ONEDIR, dest)
    try:
        yield dest
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_pacote_one_dir_tem_qt_em_arquivos_e_avisos():
    _require_built()
    internal = ONEDIR / "_internal"
    assert internal.is_dir()
    found = {path.name: path for path in internal.rglob("*.dll")}
    for name in (
        "Qt6Core.dll",
        "Qt6Gui.dll",
        "Qt6Widgets.dll",
        "pyside6.abi3.dll",
        "shiboken6.abi3.dll",
    ):
        assert name in found, name
        assert found[name].read_bytes()[:2] == b"MZ"
        assert found[name].stat().st_size > 10_000
    assert list(internal.rglob("qwindows.dll"))
    assert not (ONEDIR / ".pm3manager-root").is_file()
    assert not (project_root() / "dist" / "Proxmark3StandaloneManager.exe").is_file()
    status = (ONEDIR / "DISTRIBUTION-STATUS.txt").read_text(encoding="utf-8")
    assert "PUBLICATION: BLOCKED" in status
    for relative in (
        "LICENSE",
        "README.txt",
        "THIRD_PARTY_NOTICES.md",
        "CORRESPONDING-SOURCE.md",
        "SHA256SUMS.txt",
        "licenses/MIT.txt",
        "licenses/GPL-3.0.txt",
        "licenses/LGPL-3.0.txt",
        "licenses/BSD-3-Clause-pyserial.txt",
        "licenses/PyInstaller-COPYING.txt",
        "licenses/Apache-2.0.txt",
        "licenses/PySide6-Qt-NOTICE.txt",
    ):
        assert (ONEDIR / relative).is_file(), relative
    assert "Copyright (c) 2026 Anderson A. Justino" in (ONEDIR / "LICENSE").read_text(encoding="utf-8")
    notice = (ONEDIR / "licenses" / "PySide6-Qt-NOTICE.txt").read_text(encoding="utf-8")
    assert "qt.conf" in notice
    assert "not, by itself" in notice or "not the whole obligation" in notice.lower() or "does not" in notice
    sums = (ONEDIR / "SHA256SUMS.txt").read_text(encoding="ascii")
    exe_hash = hashlib.sha256(ONEDIR_EXE.read_bytes()).hexdigest()
    assert exe_hash in sums


def test_executavel_self_check_na_arvore_de_desenvolvimento(tmp_path):
    exe = _require_built()
    catalog = project_root() / "catalog" / "modulos.json"
    before = catalog.read_bytes() if catalog.is_file() else None
    try:
        completed = _run_exe(exe, tmp_path / "dados")
        assert completed.returncode == 0, completed.stderr
        payload = json.loads((tmp_path / "dados" / "self-check.json").read_text(encoding="utf-8"))
        assert payload["ok"] is True
        assert payload["flash_authorized"] is False
        assert payload["modules"] >= 1
        assert "ProxSpace" in payload["proxspace"]
    finally:
        if before is None:
            if catalog.exists():
                catalog.unlink()
        elif catalog.is_file():
            catalog.write_bytes(before)


def test_copia_em_outra_pasta_sem_proxspace_e_com_espacos(copia_com_espaco, tmp_path):
    exe = copia_com_espaco / "Proxmark3StandaloneManager.exe"
    assert " " in str(exe)
    assert copia_com_espaco.resolve() != ONEDIR.resolve()
    completed = _run_exe(exe, tmp_path / "sem-proxspace")
    assert completed.returncode == 1
    payload = json.loads((tmp_path / "sem-proxspace" / "self-check.json").read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["code"] == "E001"
    assert not (copia_com_espaco / "var").exists()
    assert not (copia_com_espaco / "preferences.json").exists()
    assert not (copia_com_espaco / "self-check.json").exists()


def test_selecao_manual_de_proxspace_persiste(copia_com_espaco, tmp_path):
    proxspace = project_root().parent / "ProxSpace"
    if not (proxspace / "runme64.bat").is_file():
        pytest.skip("ProxSpace is not installed beside the project")
    data = tmp_path / "dados"
    data.mkdir()
    prefs_path = data / "preferences.json"
    prefs_path.write_text(
        json.dumps(
            {
                "proxspace_root": str(proxspace),
                "flash_autorizado": False,
                "canary": "manter",
                "last_module_id": "HF_MATTYRUN",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    before = prefs_path.read_text(encoding="utf-8")
    exe = copia_com_espaco / "Proxmark3StandaloneManager.exe"
    completed = _run_exe(exe, data)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads((data / "self-check.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["flash_authorized"] is False
    assert Path(payload["proxspace"]).resolve() == proxspace.resolve()
    assert prefs_path.read_text(encoding="utf-8") == before
    assert "manter" in before
    assert not (copia_com_espaco / "preferences.json").exists()


def _personal_needles() -> tuple[bytes, ...]:
    """Identidade da máquina que executa o teste, sem gravá-la no código."""
    found: list[bytes] = []
    home = Path.home().name
    if home and home.casefold() != "qt":
        found.append(home.encode("utf-8"))
        found.append(f"\\Users\\{home}".encode("utf-8"))
        found.append(f"/Users/{home}".encode("utf-8"))
    root = project_root()
    found.append(str(root).encode("utf-8"))
    parent = root.parent.name
    generic = {"proxspace", "src", "source", "projects", "repos"}
    if parent and parent.casefold() not in generic:
        found.append(parent.encode("utf-8"))
    unique: list[bytes] = []
    for item in found:
        if item and item not in unique:
            unique.append(item)
    return tuple(unique)


def test_zip_local_nao_leva_dados_pessoais_nem_firmware():
    _require_built()
    if not ZIP_PATH.is_file():
        pytest.skip("validation zip is not built")
    outer = (project_root() / "dist" / "SHA256SUMS.txt").read_text(encoding="ascii")
    zip_hash = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
    assert zip_hash in outer
    forbidden_name_parts = (
        ".pm3manager-root",
        ".venv",
        "preferences.json",
        "app.log",
        "modulos.json",
        "third-party-source",
        "Makefile.platform",
    )
    forbidden_suffixes = {".elf", ".bin", ".dump", ".dmp", ".eml"}
    personal = _personal_needles()
    assert personal
    with zipfile.ZipFile(ZIP_PATH) as archive:
        names = archive.namelist()
        assert f"Proxmark3StandaloneManager/{ONEDIR_EXE.name}" in names
        assert "Proxmark3StandaloneManager/licenses/LGPL-3.0.txt" in names
        assert "Proxmark3StandaloneManager/licenses/GPL-3.0.txt" in names
        assert "Proxmark3StandaloneManager/licenses/QT-FILES.txt" in names
        assert "Proxmark3StandaloneManager/DISTRIBUTION-STATUS.txt" in names
        assert "Proxmark3StandaloneManager/LICENSE" in names
        for name in names:
            lowered = name.lower()
            assert not any(part.lower() in lowered for part in forbidden_name_parts), name
            assert Path(name).suffix.lower() not in forbidden_suffixes, name
            data = archive.read(name)
            for needle in personal:
                assert needle not in data, f"{needle!r} inside {name}"
            # Official Qt binaries contain C:\Users\qt\... from their build.
            # Any other Windows profile path is this machine and is forbidden.
            start = 0
            token = b"\\Users\\"
            while True:
                found = data.find(token, start)
                if found < 0:
                    break
                follow = data[found + len(token) : found + len(token) + 3]
                assert follow == b"qt\\", f"unexpected profile path in {name}"
                start = found + len(token)


def test_substituir_qt6core_na_copia_bloqueia_e_a_restauracao_recupera(copia_com_espaco, tmp_path):
    """Desliga Qt6Core.dll e restaura os mesmos bytes.

    Isso mostra qual arquivo o processo carrega. Não mostra que uma Qt
    modificada e recompilada funciona, e não é conformidade com a LGPL.
    """
    dlls = list(copia_com_espaco.rglob("Qt6Core.dll"))
    assert len(dlls) == 1
    dll = dlls[0]
    backup = dll.read_bytes()
    digest = hashlib.sha256(backup).hexdigest()
    disabled = dll.with_suffix(".dll.disabled")
    exe = copia_com_espaco / "Proxmark3StandaloneManager.exe"
    missing = tmp_path / "sem-dll"
    missing.mkdir()
    try:
        dll.rename(disabled)
        proc = subprocess.Popen(
            [str(exe), "--self-check"],
            cwd=str(exe.parent),
            env=_child_env(missing),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        code: int | None
        try:
            code = proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=15)
            code = None
        if code == 0:
            raise AssertionError("the process exited 0 without Qt6Core.dll")
        if (missing / "self-check.json").is_file():
            failed = json.loads((missing / "self-check.json").read_text(encoding="utf-8"))
            assert failed.get("qt_loaded") is not True
    finally:
        if not dll.exists() and disabled.exists():
            disabled.replace(dll)
        if not dll.exists():
            dll.write_bytes(backup)
        assert hashlib.sha256(dll.read_bytes()).hexdigest() == digest
    restored = tmp_path / "restaurado"
    completed = _run_exe(exe, restored)
    assert (restored / "self-check.json").is_file()
    assert completed.returncode in (0, 1)
    restored_payload = json.loads((restored / "self-check.json").read_text(encoding="utf-8"))
    assert restored_payload.get("qt_loaded") is True


def test_atalho_aponta_para_o_executavel_one_dir():
    _require_built()
    from pm3manager.install.shortcut import SHORTCUT_NAME, desktop_directory, read_shortcut

    link = desktop_directory() / SHORTCUT_NAME
    if not link.is_file():
        pytest.skip("desktop shortcut is not created")
    info = read_shortcut(link)
    assert Path(info["TARGET"]).resolve() == ONEDIR_EXE.resolve()
    assert Path(info["WORKDIR"]).resolve() == ONEDIR_EXE.parent.resolve()
    assert info.get("STYLE") == "1"
    assert "Proxmark3StandaloneManager.exe" in info.get("ICON", "")
