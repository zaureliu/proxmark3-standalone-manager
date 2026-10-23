import json

from pm3manager.cache.store import FirmwareCache
from pm3manager.models import BuildConfig
from pm3manager.preferences import Preferences
from pm3manager.proxspace.makefile import (
    MakefileSession,
    active_assignments,
    recover_interrupted,
    render_makefile,
)
from tests.fakes import VERSION, make_env


ORIGINAL = """# comentario preservado
PLATFORM=PM3RDV4
#PLATFORM=PM3GENERIC
PLATFORM_EXTRAS=FLASH
#STANDALONE=HF_UNISNIFF
INSTALLSUDO=sudo
"""


def test_render_preserva_comentario_e_nao_duplica_chaves():
    config = BuildConfig("PM3GENERIC", "LF_SAMYRUN")
    text = render_makefile(ORIGINAL, config)
    found = active_assignments(text)
    assert found["PLATFORM"] == ["PM3GENERIC"]
    assert found["STANDALONE"] == ["LF_SAMYRUN"]
    assert found["LED_ORDER"] == ["PM3EASY"]
    assert found["PLATFORM_EXTRAS"] == []
    assert "# comentario preservado" in text
    assert "#PLATFORM=PM3GENERIC" in text
    assert "INSTALLSUDO=sudo" in text
    assert "PM3RDV4" not in "".join(found["PLATFORM"])
    again = render_makefile(text, config)
    assert active_assignments(again)["PLATFORM"] == ["PM3GENERIC"]
    assert again.count("BEGIN Proxmark3 Standalone Manager") == 1


def test_render_com_flash_e_tamanho():
    config = BuildConfig("PM3GENERIC", "HF_ST25_TEAROFF", extras=("FLASH",), platform_size="256")
    text = render_makefile("", config)
    found = active_assignments(text)
    assert found["PLATFORM_EXTRAS"] == ["FLASH"]
    assert found["PLATFORM_SIZE"] == ["256"]


def test_sessao_mantem_arquivo_quando_pedido(tmp_path):
    env = make_env(tmp_path)
    state = tmp_path / "state"
    backup = tmp_path / "backup"
    config = BuildConfig("PM3GENERIC", "LF_SAMYRUN", extras=("FLASH",))
    with MakefileSession(env.repo_root, state, backup, config) as session:
        session.keep()
    text = (env.repo_root / "Makefile.platform").read_text(encoding="utf-8")
    assert "PLATFORM=PM3GENERIC" in text
    assert "PLATFORM_EXTRAS=FLASH" in text
    assert "STANDALONE=LF_SAMYRUN" in text
    state_text = (state / "build_session.json").read_text(encoding="utf-8")
    assert '"phase": "kept"' in state_text


def test_sessao_restaura_arquivo_ausente(tmp_path):
    env = make_env(tmp_path)
    state = tmp_path / "state"
    backup = tmp_path / "backup"
    config = BuildConfig("PM3GENERIC", "LF_SAMYRUN")
    with MakefileSession(env.repo_root, state, backup, config):
        current = (env.repo_root / "Makefile.platform").read_text(encoding="utf-8")
        assert "STANDALONE=LF_SAMYRUN" in current
        assert (state / "build_session.json").is_file()
    assert not (env.repo_root / "Makefile.platform").exists()


def test_recuperacao_de_sessao_interrompida(tmp_path):
    env = make_env(tmp_path)
    state = tmp_path / "state"
    backup = tmp_path / "backup"
    original = "PLATFORM=PM3GENERIC\n# nota\n"
    target = env.repo_root / "Makefile.platform"
    target.write_text(original, encoding="utf-8")
    session = MakefileSession(env.repo_root, state, backup, BuildConfig("PM3GENERIC", "LF_MULTIHID"))
    session.__enter__()
    assert "LF_MULTIHID" in target.read_text(encoding="utf-8")
    note = recover_interrupted(state)
    assert note
    assert target.read_text(encoding="utf-8") == original


def test_mcu_512_nao_forca_tamanho_256(tmp_path):
    from pm3manager.build.compiler import preserve_bootrom, snapshot_artifacts
    from pm3manager.workflow.service import build_config, size_option_allowed

    prefs = Preferences(platform_size_256=True, detected_mcu="AT91SAM7S512 512K bytes", spi_flash_confirmada=True)
    assert size_option_allowed(prefs) is False
    config = build_config("LF_SAMYRUN", prefs)
    assert config.platform_size == ""
    assert config.extras == ("FLASH",)
    small = Preferences(platform_size_256=True, detected_mcu="AT91SAM7S256 256K bytes")
    assert build_config("LF_SAMYRUN", small).platform_size == "256"
    repo = tmp_path / "repo"
    boot = repo / "bootrom" / "obj" / "bootrom.elf"
    boot.parent.mkdir(parents=True)
    boot.write_bytes(b"BOOT-ANTIGO")
    snapshot = snapshot_artifacts(repo, tmp_path / "backup")
    boot.write_bytes(b"BOOT-NOVO")
    (repo / "bootrom" / "obj" / "novo.o").write_bytes(b"o")
    (repo / "recovery").mkdir()
    (repo / "recovery" / "recovery.bin").write_bytes(b"REC")
    preserve_bootrom(repo, snapshot)
    assert boot.read_bytes() == b"BOOT-ANTIGO"
    assert not (repo / "bootrom" / "obj" / "novo.o").exists()
    assert not (repo / "recovery" / "recovery.bin").exists()


def test_preferencias_isoladas(isolated_data):
    prefs = Preferences(last_module_id="HF_AVEFUL", flash_autorizado=False)
    prefs.save()
    loaded = Preferences.load()
    assert loaded.last_module_id == "HF_AVEFUL"
    assert loaded.flash_autorizado is False
    assert loaded.spi_flash_recusada is False
    assert loaded.detected_mcu == ""
    assert Preferences.path().parent == isolated_data


def test_cache_rejeita_hash_antigo(tmp_path):
    env = make_env(tmp_path)
    config = BuildConfig("PM3GENERIC", "LF_SAMYRUN")
    image = tmp_path / "fullimage.elf"
    image.write_bytes(b"\x7fELF" + b"\x00" * 20000 + VERSION.encode("utf-8"))
    cache = FirmwareCache(tmp_path / "cache")
    entry = cache.store(env, config, "gcc-teste", image)
    assert cache.lookup(env, config, "gcc-teste") is not None
    assert cache.lookup(env, config, "outro-gcc") is None
    entry.image.write_bytes(b"\x7fELF" + b"\x11" * 20000 + VERSION.encode("utf-8"))
    assert cache.lookup(env, config, "gcc-teste") is None
    metadata = json.loads((entry.directory / "metadata.json").read_text(encoding="utf-8"))
    metadata["source_fingerprint"] = "mudou"
    (entry.directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    image.write_bytes(b"\x7fELF" + b"\x00" * 20000 + VERSION.encode("utf-8"))
    env.source_fingerprint = "fingerprint-teste"
    assert cache.lookup(env, config, "gcc-teste") is None
