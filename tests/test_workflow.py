import threading

from pm3manager.cache.store import FirmwareCache
from pm3manager.messages import Msg
from pm3manager.models import Compatibility
from pm3manager.preferences import Preferences
from pm3manager.workflow.lock import OperationLock
from pm3manager.workflow.service import ManagerService
from tests.fakes import device, make_env, module, FakeShell


def _service(tmp_path, shell, prefs=None, devices=None):
    env = make_env(tmp_path)
    prefs = prefs or Preferences()
    detected = devices if devices is not None else [device()]

    def detect():
        return list(detected)

    return ManagerService(
        env,
        prefs,
        shell,
        FirmwareCache(tmp_path / "cache"),
        OperationLock(),
        detect=detect,
        port_free=lambda port: (True, ""),
        sleeper=lambda seconds: None,
    ), env, shell


def test_lock_exclui_segunda_operacao():
    lock = OperationLock()
    assert lock.acquire("a")
    assert not lock.acquire("b")
    lock.release()
    assert lock.acquire("b")


def test_concorrencia_de_threads():
    lock = OperationLock()
    entered = []

    def hold():
        assert lock.acquire("thread")
        entered.append(threading.get_ident())

    thread = threading.Thread(target=hold)
    thread.start()
    thread.join()
    assert not lock.acquire("outra")
    lock.release()


def test_compilacao_sem_autorizacao_nao_grava(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    service, env, shell = _service(tmp_path, shell)
    result = service.apply(
        module(),
        device(),
        force_rebuild=False,
        flash_authorized=False,
    )
    assert result.ok
    assert result.code == "OK100"
    assert result.message == Msg.FLASH_NOT_AUTHORIZED
    assert not any("pm3-flash-fullimage" in script for script in shell.scripts)
    assert any("make clean" in script and "make -j" in script for script in shell.scripts)
    makefile = (env.repo_root / "Makefile.platform").read_text(encoding="utf-8")
    assert "PLATFORM=PM3GENERIC" in makefile
    assert "STANDALONE=LF_SAMYRUN" in makefile
    assert "LED_ORDER=PM3EASY" in makefile
    assert "\nPLATFORM_SIZE=" not in makefile
    before = len(shell.scripts)
    again = service.apply(module(), device(), force_rebuild=False, flash_authorized=False)
    assert again.outcome == "cache_hit"
    assert not any("make -j" in script for script in shell.scripts[before:])


def test_recompilar_ignora_cache(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    service, _, shell = _service(tmp_path, shell)
    assert service.apply(module(), None, force_rebuild=False, flash_authorized=False).ok
    before = len(shell.scripts)
    result = service.recompile(module())
    assert result.ok
    assert result.message == Msg.COMPILE_OK
    assert any("make -j" in script for script in shell.scripts[before:])


def test_falha_de_compilacao_nao_grava(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.fail_build = True
    service, env, shell = _service(tmp_path, shell)
    result = service.apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert not result.ok
    assert result.code == "E200"
    assert result.message == Msg.COMPILE_FAIL
    assert not any("pm3-flash-fullimage" in script for script in shell.scripts)
    assert not (env.repo_root / "Makefile.platform").exists()


def test_make_que_anuncia_rdv4_nao_grava(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.banner_platform = "PM3RDV4"
    service, env, shell = _service(tmp_path, shell)
    original = env.repo_root / "armsrc" / "obj" / "fullimage.elf"
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"\x7fELF" + b"OLD")
    result = service.apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert result.code == "E202"
    assert result.message == Msg.COMPILE_FAIL
    assert not (env.repo_root / "Makefile.platform").exists()
    assert not any("pm3-flash" in script for script in shell.scripts)
    assert original.read_bytes().startswith(b"\x7fELF" + b"OLD")


def test_cache_nao_reusa_configuracao_diferente(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    prefs = Preferences(spi_flash_confirmada=False)
    service, _, shell = _service(tmp_path, shell, prefs=prefs)
    first = service.apply(module(), device(), force_rebuild=True, flash_authorized=False)
    assert first.outcome == "compile_only"
    prefs.spi_flash_confirmada = True
    second = service.apply(module(), device(), force_rebuild=False, flash_authorized=False)
    assert second.outcome == "compile_only"
    assert sum("make -j" in script for script in shell.scripts) == 2


def test_elf_ausente_depois_do_make(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.omit_elf = True
    service, _, shell = _service(tmp_path, shell)
    result = service.apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert result.code == "E201"
    assert not any("pm3-flash" in script for script in shell.scripts)


def test_falha_de_gravacao_simulada(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    shell.fail_flash = True
    service, _, _ = _service(tmp_path, shell)
    result = service.apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert result.code == "E300"
    assert result.message == Msg.FLASH_UNCONFIRMED


def test_gravacao_simulada_valida_comunicacao(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    service, _, shell = _service(tmp_path, shell)
    result = service.apply(module(), device(), force_rebuild=True, flash_authorized=True)
    assert result.ok
    assert result.code == "OK210"
    assert result.outcome == "flash_partial_validation"
    assert result.message.startswith("Validação parcial")
    assert "não foi confirmado" in result.message
    assert Msg.FLASH_VALIDATED not in result.message
    assert result.details["etapa_modulo"] == "nao_confirmado"
    assert result.details["etapa_laboratorio"] == "nao_realizado"
    assert result.details["validacao"] == "parcial"
    assert any("pm3-flash-fullimage" in script and "pm3-flash-all" not in script for script in shell.scripts)
    assert any("hw version" in script for script in shell.scripts)


def test_modulo_incompativel_bloqueado(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    service, _, shell = _service(tmp_path, shell)
    result = service.apply(
        module("HF_REBLAY", Compatibility.INCOMPATIBLE),
        device(),
        force_rebuild=True,
        flash_authorized=True,
    )
    assert result.code == "E104"
    assert result.message == Msg.INCOMPATIBLE_MODULE
    assert shell.scripts == []


def test_operacao_ocupada(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    service, _, _ = _service(tmp_path, shell)
    assert service.lock.acquire("teste")
    result = service.apply(module(), device(), force_rebuild=False, flash_authorized=False)
    assert result.code == "E010"
    service.lock.release()


def test_proxmark_ausente_quando_gravacao_autorizada(isolated_data, tmp_path):
    shell = FakeShell(make_env(tmp_path).repo_root)
    service, _, shell = _service(tmp_path, shell, devices=[])
    result = service.apply(module(), None, force_rebuild=True, flash_authorized=True)
    assert result.code == "E100"
    assert result.message == Msg.NOT_FOUND
    assert shell.scripts == []
