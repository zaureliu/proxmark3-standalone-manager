"""Atalhos de teste que não alteram o comportamento quando o laboratório está presente."""

from __future__ import annotations

import pytest

from pm3manager.paths import project_root


def require_local_proxspace() -> None:
    """Pula só quando o checkout usado no desenvolvimento não existe.

    Nos runners de CI o ProxSpace não está instalado. Na máquina de
    desenvolvimento o teste continua obrigatório.
    """
    root = project_root().parent / "ProxSpace"
    checkout = root / "pm3" / "proxmark3-v4.23346"
    if not (root / "runme64.bat").is_file() or not (checkout / "Makefile").is_file():
        pytest.skip("ProxSpace local com proxmark3-v4.23346 não está disponível.")
