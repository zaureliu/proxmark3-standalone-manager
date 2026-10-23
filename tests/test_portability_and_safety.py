"""Portabilidade, cache, concorrência e bloqueio de gravação incompatível.

Nenhum teste grava firmware real.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pm3manager.cache.store import FirmwareCache
from pm3manager.errors import ProxSpaceError
from pm3manager.messages import Msg
from pm3manager.models import BuildConfig, OperationResult
from pm3manager.paths import project_root
from pm3manager.preferences import Preferences
from pm3manager.proxspace.locator import locate
from pm3manager.proxspace.makefile import recover_interrupted
from pm3manager.textutil import bash_invocation, batch_path, to_msys_path
from pm3manager.ui.presentation import present_result
from pm3manager.workflow.context import AppContext
from pm3manager.workflow.lock import OperationLock
from pm3manager.workflow.service import build_config, incompatible_flash
from tests.fakes import VERSION, device, module
from tests.test_workflow import _service


def _install(root: Path, dirname: str = "proxmark3-test", version: str = "Iceman/master/v4.1.0") -> Path:
    repo = root / "pm3" / dirname
    (repo / "armsrc" / "Standalone").mkdir(parents=True, exist_ok=True)
    (repo / "common").mkdir(parents=True, exist_ok=True)
    (repo / "Makefile").write_text("all:\n", encoding="utf-8")
    (repo / "armsrc" / "Standalone" / "Makefile.hal").write_text("hal\n", encoding="utf-8")
    (repo / "pm3").write_text("#!/bin/bash\n", encoding="utf-8")
    (repo / "pm3-flash-fullimage").write_text("#!/bin/bash\n", encoding="utf-8")
    (repo / "common" / "default_version_pm3.c").write_text(
        f'{{ "{version}", "2026-01-01 00:00:00", "abc123" }}\n',
        encoding="utf-8",
    )
    (root / "msys2").mkdir(parents=True, exist_ok=True)
    (root / "runme64.bat").write_text("@echo off\n", encoding="utf-8")
    (root / "msys2" / "msys2_shell.cmd").write_text("@echo off\n", encoding="utf-8")
    return repo


def test_descoberta_explicita_aceita_espaco_e_escolhe_versao_maior(tmp_path):
    root = tmp_path / "Prox Space (x86)"
    _install(root, "proxmark3-v4.9.0", "Iceman/master/v4.9.0")
    _install(root, "proxmark3-v4.10.0", "Iceman/master/v4.10.0")
    (root / "pm3" / "nao-e-repo").mkdir()
    env = locate(root)
    assert env.proxspace_root == root.resolve()
    assert env.repo_root.name == "proxmark3-v4.10.0"
    assert env.available_repos == ("proxmark3-v4.10.0", "proxmark3-v4.9.0")
    assert " " in str(env.proxspace_root)
    script = root / "tarefa.sh"
    script.write_text("echo ok\n", encoding="utf-8")
    msys = to_msys_path(script)
    assert "(" in msys and " " in msys
    assert bash_invocation(msys) == f"bash '{msys}'"


def test_caminho_invalido_nao_cai_na_instalacao_existente(tmp_path, monkeypatch):
    missing = tmp_path / "ausente"
    with pytest.raises(ProxSpaceError) as exc:
        locate(missing)
    assert exc.value.code == "E001"
    monkeypatch.setenv("PM3MANAGER_PROXSPACE", str(missing))
    monkeypatch.delenv("PROXSPACE", raising=False)
    with pytest.raises(ProxSpaceError) as forced:
        locate()
    assert forced.value.code == "E001"
    assert "ausente" in forced.value.technical


def test_preferencia_salva_invalida_nao_e_substituida(tmp_path, monkeypatch):
    for name in ("preferences", "paths", "workflow.context"):
        monkeypatch.setattr(f"pm3manager.{name}.data_dir", lambda: tmp_path)
    Preferences(proxspace_root=str(tmp_path / "errado")).save()
    with pytest.raises(ProxSpaceError) as exc:
        AppContext.load()
    assert exc.value.code == "E001"


def test_variavel_de_ambiente_valida_tem_prioridade(tmp_path, monkeypatch):
    root = tmp_path / "OutroProxSpace"
    _install(root, "proxmark3-v4.8.0", "Iceman/master/v4.8.0")
    monkeypatch.setenv("PM3MANAGER_PROXSPACE", str(root))
    monkeypatch.delenv("PROXSPACE", raising=False)
    env = locate()
    assert env.proxspace_root == root.resolve()
    assert env.repo_root.name == "proxmark3-v4.8.0"


def test_bash_sem_espaco_permanece_sem_aspas(tmp_path):
    script = tmp_path / "task-seguro.sh"
    script.write_text("echo ok\n", encoding="utf-8")
    msys = to_msys_path(script)
    assert bash_invocation(msys) == f"bash {msys}"
    assert batch_path(script) == str(script)


def test_caminho_com_aspas_ou_e_comercial_e_recusado():
    quoted = Path("C:/nao-existe") / 'a"b'
    percent = Path("C:/nao-existe") / "a%b"
    ampersand = Path("C:/nao-existe") / "a&b"
    assert '"' in str(quoted) or "%" in str(percent)
    for path in (quoted, percent, ampersand):
        if any(character in str(path) for character in '"%&'):
            with pytest.raises(ValueError):
                batch_path(path)


def test_diretorio_de_trabalho_nao_muda_a_raiz(tmp_path, monkeypatch):
    from tests.support import require_local_proxspace

    require_local_proxspace()
    monkeypatch.chdir(tmp_path)
    assert project_root().name == "Proxmark3StandaloneManager"
    fake = tmp_path / "ProxSpace"
    _install(fake, "proxmark3-falso", "Iceman/master/v9.9.9")
    monkeypatch.delenv("PM3MANAGER_PROXSPACE", raising=False)
    monkeypatch.delenv("PROXSPACE", raising=False)
    env = locate()
    assert env.repo_root.name == "proxmark3-v4.23346"
    assert env.proxspace_root != fake.resolve()


def test_cache_rejeita_configuracao_e_link_externo(tmp_path, monkeypatch):
    from tests.fakes import make_env

    env = make_env(tmp_path)
    config = BuildConfig("PM3GENERIC", "LF_SAMYRUN")
    image = tmp_path / "fullimage.elf"
    image.write_bytes(b"\x7fELF" + b"\x00" * 20000 + VERSION.encode("utf-8"))
    cache = FirmwareCache(tmp_path / "cache")
    entry = cache.store(env, config, "gcc-teste", image)
    metadata = json.loads((entry.directory / "metadata.json").read_text(encoding="utf-8"))
    metadata["config"]["platform_size"] = "256"
    (entry.directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    assert cache.lookup(env, config, "gcc-teste") is None
    metadata["config"] = config.identity()
    metadata["toolchain"] = "outro"
    (entry.directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    assert cache.lookup(env, config, "gcc-teste") is None
    metadata["toolchain"] = "gcc-teste"
    (entry.directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    outside = tmp_path / "fora.elf"
    outside.write_bytes(image.read_bytes())
    entry.image.unlink()
    try:
        entry.image.symlink_to(outside)
    except OSError:
        entry.image.write_bytes(image.read_bytes())
        image_path = entry.image
        original_link = Path.is_symlink
        original_resolve = Path.resolve

        def pretend_link(self, _original=original_link, _image=image_path):
            if self == _image:
                return True
            return _original(self)

        def pretend_resolve(self, strict=False, _original=original_resolve, _image=image_path, _outside=outside):
            if self == _image:
                return _outside
            return _original(self, strict=strict)

        monkeypatch.setattr(Path, "is_symlink", pretend_link)
        monkeypatch.setattr(Path, "resolve", pretend_resolve)
    assert cache.lookup(env, config, "gcc-teste") is None


def test_mcu_256_obriga_tamanho_e_512_nao_recebe_256():
    small = Preferences(platform_size_256=False, detected_mcu="AT91SAM7S256 256K bytes")
    assert build_config("LF_SAMYRUN", small).platform_size == "256"
    large = Preferences(platform_size_256=True, detected_mcu="AT91SAM7S512 512K bytes")
    assert build_config("LF_SAMYRUN", large).platform_size == ""
    unknown = Preferences(detected_mcu="")
    assert build_config("LF_SAMYRUN", unknown).platform_size == ""
    assert incompatible_flash(small, BuildConfig("PM3GENERIC", "LF_SAMYRUN", platform_size="")) == Msg.FLASH_SIZE_BLOCKED
    assert incompatible_flash(large, BuildConfig("PM3GENERIC", "LF_SAMYRUN", platform_size="256")) == Msg.FLASH_SIZE_BLOCKED
    assert incompatible_flash(unknown, BuildConfig("PM3GENERIC", "LF_SAMYRUN")) == ""
    rdv4 = Preferences(detected_firmware_kind="RDV4", detected_mcu="AT91SAM7S512 512K bytes")
    assert incompatible_flash(rdv4, BuildConfig("PM3GENERIC", "LF_SAMYRUN")) == Msg.FLASH_RDV4_BLOCKED


def test_rdv4_e_diagnostico_e_nao_grava(isolated_data, tmp_path):
    from tests.fakes import FakeShell, make_env

    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.hw_output = f"[ Proxmark3 ]\nFirmware.................. RDV4\n{VERSION}\n"
    service, _, shell = _service(tmp_path, shell)
    checked = service.verify(device())
    assert checked.ok
    assert checked.code == "OK202"
    assert checked.outcome == "verified_restricted"
    view = present_result(checked)
    assert view.status == "Aviso"
    assert view.dialog == "warning"
    assert view.status != "Pronto"
    shell.scripts.clear()
    service.prefs.detected_firmware_kind = ""
    flashed = service.apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert flashed.code == "E303"
    assert flashed.message == Msg.FLASH_RDV4_BLOCKED
    assert any("make -j" in script for script in shell.scripts)
    assert not any("pm3-flash-fullimage" in script for script in shell.scripts)


def test_preferencia_rdv4_bloqueia_antes_de_compilar(isolated_data, tmp_path):
    from tests.fakes import FakeShell, make_env

    shell = FakeShell(make_env(tmp_path).repo_root)
    service, _, shell = _service(
        tmp_path,
        shell,
        prefs=Preferences(detected_firmware_kind="RDV4"),
    )
    result = service.apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert result.code == "E303"
    assert shell.scripts == []


def test_porta_conhecida_ocupada_bloqueia_e_falha_de_abertura_nao(isolated_data, tmp_path):
    from tests.fakes import FakeShell, make_env

    shell = FakeShell(make_env(tmp_path).repo_root)
    service, _, shell = _service(tmp_path, shell)
    service.port_free = lambda port: (False, f"A porta {port} está em uso por outro processo.")
    busy = service.apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert busy.code == "E106"
    assert not any("pm3-flash-fullimage" in script for script in shell.scripts)
    shell.scripts.clear()
    service.port_free = lambda port: (False, "Não foi possível abrir COM5: timeout")
    proceeded = service.apply(module(), device(), force_rebuild=False, flash_authorized=True)
    assert proceeded.code == "OK210"
    assert any("pm3-flash-fullimage" in script for script in shell.scripts)


def test_recuperacao_recusa_makefile_fora_do_checkout(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    target = tmp_path / "fora" / "Makefile.platform"
    target.parent.mkdir()
    target.write_text("ORIGINAL\n", encoding="utf-8")
    backup = tmp_path / "backup" / "Makefile.platform.teste.bak"
    backup.parent.mkdir()
    backup.write_text("BACKUP\n", encoding="utf-8")
    (state / "build_session.json").write_text(
        json.dumps(
            {
                "phase": "open",
                "existed": True,
                "backup": str(backup),
                "target": str(target),
                "standalone": "LF_SAMYRUN",
            }
        ),
        encoding="utf-8",
    )
    note = recover_interrupted(state)
    assert note and "Nada foi restaurado" in note
    assert target.read_text(encoding="utf-8") == "ORIGINAL\n"


def test_lock_consultado_nao_libera_o_dono():
    lock = OperationLock()
    assert lock.locked is False
    assert lock.acquire("dono")
    assert lock.locked is True
    assert lock.owner == "dono"
    assert not lock.acquire("outro")
    lock.release()
    assert lock.locked is False


def test_ok210_nao_virou_diagnostico_de_rdv4():
    partial = present_result(
        OperationResult(True, "OK210", Msg.FLASH_PARTIAL_CHECK, "flash_partial_validation")
    )
    assert partial.status == "Validação parcial"
    assert partial.dialog == "warning"
    restricted = present_result(
        OperationResult(True, "OK202", Msg.RDV4_DIAGNOSTIC, "verified_restricted")
    )
    assert restricted.status == "Aviso"
    assert os.environ.get("PM3MANAGER_ENV") == "teste"
