"""Checks that do not need ProxSpace, a device, or a firmware flash."""

from __future__ import annotations

import re
import tomllib

import pm3manager
import pm3manager.app
import pm3manager.preferences
import pm3manager.workflow.service
from pm3manager.paths import project_root


def test_importa_os_modulos_principais():
    assert pm3manager.__version__ == "2.0.0"
    assert callable(pm3manager.app.self_check)
    assert pm3manager.preferences.Preferences().flash_autorizado is False
    assert pm3manager.workflow.service.ManagerService


def test_pyproject_e_requirements_concordam():
    root = project_root()
    document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert document["project"]["version"] == pm3manager.__version__
    assert document["project"]["requires-python"] == ">=3.11"
    runtime = " ".join(document["project"]["dependencies"]).lower()
    assert "pyside6" in runtime
    assert "pyserial" in runtime
    requirements = (root / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "pyside6" in requirements
    assert "pyserial" in requirements
    assert "pytest" in requirements
    assert "pyinstaller" in requirements


def test_arquivos_de_publicacao_existem_e_a_ci_nao_grava():
    root = project_root()
    for relative in (
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        ".gitignore",
        ".gitattributes",
        "THIRD_PARTY_NOTICES.md",
        "docs/install.md",
        "docs/updates.md",
        "docs/compatibility.md",
        "docs/troubleshooting.md",
        "docs/licensing.md",
        "docs/packaging.md",
        "docs/screenshots/README.md",
        ".github/workflows/ci.yml",
        "scripts/build_exe.ps1",
        "scripts/hash_artifacts.ps1",
        "scripts/stage_distribution.ps1",
        "scripts/fetch_corresponding_source.ps1",
        "DISTRIBUTION-STATUS.txt",
        "docs/corresponding-source.md",
        "licenses/MIT.txt",
        "licenses/GPL-3.0.txt",
        "licenses/LGPL-3.0.txt",
        "licenses/Apache-2.0.txt",
        "licenses/BSD-3-Clause-pyserial.txt",
        "licenses/PyInstaller-COPYING.txt",
        "licenses/PySide6-Qt-NOTICE.txt",
        "licenses/MICROSOFT-RUNTIME.txt",
        "licenses/README.txt",
        "packaging/README-DISTRIBUTION.txt",
    ):
        assert (root / relative).is_file(), relative
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8").lower()
    assert "pytest" in workflow
    assert "pm3-flash" not in workflow
    assert "release" not in workflow
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "Hardware Validation — MattyRun" in readme
    assert "RDV4" in readme


def test_licenca_mit_nomeia_o_titular_e_nao_relicencia_terceiros():
    root = project_root()
    license_text = (root / "LICENSE").read_text(encoding="utf-8")
    assert "Copyright (c) 2026 Anderson A. Justino" in license_text
    assert "Permission is hereby granted, free of charge" in license_text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in license_text
    assert "License decision pending" not in license_text
    assert "GNU GENERAL PUBLIC LICENSE" not in license_text
    mirror = (root / "licenses" / "MIT.txt").read_text(encoding="utf-8")
    assert mirror == license_text
    document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert document["project"]["license"]["text"] == "MIT"
    assert document["project"]["authors"][0]["name"] == "Anderson A. Justino"
    notice = (root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "does not relicense" in notice
    assert "LGPL-3.0-only" in notice
    assert "Chris Liechti" in notice
    status = (root / "DISTRIBUTION-STATUS.txt").read_text(encoding="utf-8")
    assert "PUBLICATION: BLOCKED" in status
    gpl = (root / "licenses" / "GPL-3.0.txt").read_text(encoding="utf-8")
    lgpl = (root / "licenses" / "LGPL-3.0.txt").read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in gpl
    assert "Version 3, 29 June 2007" in gpl
    assert "LESSER GENERAL PUBLIC LICENSE" in lgpl
    assert "Version 3, 29 June 2007" in lgpl
    assert "Chris Liechti" in (root / "licenses" / "BSD-3-Clause-pyserial.txt").read_text(encoding="utf-8")
    copying = (root / "licenses" / "PyInstaller-COPYING.txt").read_text(encoding="utf-8")
    assert "Bootloader Exception" in copying
    assert "Apache License" in (root / "licenses" / "Apache-2.0.txt").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "Copyright (c) 2026 Anderson A. Justino" in readme
    assert "License decision pending" not in readme
    licensing = (root / "docs" / "licensing.md").read_text(encoding="utf-8")
    assert "Anderson A. Justino" in licensing
    assert "corresponding source" in licensing.lower()
    spec = (root / "Proxmark3StandaloneManager.spec").read_text(encoding="utf-8")
    assert "exclude_binaries=True" in spec
    assert "COLLECT(" in spec
    assert "upx=False" in spec
    assert "console=False" in spec
    assert 'contents_directory="_internal"' in spec
    build = (root / "scripts" / "build_exe.ps1").read_text(encoding="utf-8")
    assert r"dist\Proxmark3StandaloneManager\Proxmark3StandaloneManager.exe" in build
    shortcut = (root / "scripts" / "create_shortcut.py").read_text(encoding="utf-8")
    assert '"Proxmark3StandaloneManager"' in shortcut
    assert "Proxmark3StandaloneManager.exe" in shortcut


def test_codigo_original_nao_traz_cabecalho_de_firmware():
    """O monitor cita o dono oficial do repositório. Isso não é o cabeçalho do firmware."""
    root = project_root() / "pm3manager"
    needles = ("SPDX-License-Identifier", "GNU General Public License")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in text, f"{needle} in {path.name}"
        if "updates" not in path.parts:
            assert "RfidResearchGroup" not in text, path.name


def test_documentacao_publica_nao_tem_caminho_de_usuario():
    root = project_root()
    user_path = re.compile(r"(?i)([A-Za-z]:\\Users\\|/Users/|\\Users\\)")
    targets = [root / "README.md", root / "LICENSE", root / "THIRD_PARTY_NOTICES.md"]
    targets.extend((root / "docs").rglob("*.md"))
    targets.extend((root / "pm3manager").rglob("*.py"))
    targets.extend((root / "scripts").glob("*.ps1"))
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert user_path.search(text) is None, path
