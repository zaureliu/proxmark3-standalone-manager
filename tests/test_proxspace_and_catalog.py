from pm3manager.models import Compatibility
from pm3manager.modules.catalog import filter_modules, load_modules
from pm3manager.proxspace.locator import locate
from tests.support import require_local_proxspace


def test_localiza_proxspace_real():
    require_local_proxspace()
    env = locate()
    assert env.proxspace_root.name == "ProxSpace"
    assert (env.proxspace_root / "runme64.bat").is_file()
    assert env.repo_root.name == "proxmark3-v4.23346"
    assert env.version == "Iceman/master/v4.23346"
    assert env.commit == "9ce8a4b6c"
    assert env.repo_msys == "/pm3/proxmark3-v4.23346"
    parent = env.proxspace_root / "pm3" / "Makefile.platform"
    assert env.external_makefile == parent
    assert parent.parent != env.repo_root
    assert "PLATFORM=PM3GENERIC" in env.external_makefile_text
    assert "PLATFORM_EXTRAS=FLASH" in env.external_makefile_text
    repo_platform = env.repo_root / "Makefile.platform"
    if repo_platform.is_file():
        managed = repo_platform.read_text(encoding="utf-8")
        assert "BEGIN Proxmark3 Standalone Manager" in managed
        assert "PLATFORM=PM3GENERIC" in managed
    assert (env.repo_root / "pm3-flash-fullimage").is_file()
    assert (env.repo_root / "client" / "proxmark3.exe").is_file()


def test_catalogo_real_filtra_rdv4_e_incertos():
    require_local_proxspace()
    modules = load_modules(locate())
    by_id = {module.id: module for module in modules}
    assert len(modules) >= 40
    for required in (
        "LF_EM4100RWC",
        "LF_SAMYRUN",
        "LF_MULTIHID",
        "HF_UNISNIFF",
        "HF_AVEFUL",
        "HF_LEGIC",
        "DANKARMULTI",
    ):
        assert required in by_id
    assert by_id["LF_SAMYRUN"].compatibility == Compatibility.COMPATIBLE
    assert by_id["HF_AVEFUL"].compatibility == Compatibility.COMPATIBLE
    assert by_id["HF_UNISNIFF"].compatibility == Compatibility.COMPATIBLE
    assert by_id["DANKARMULTI"].compatibility == Compatibility.COMPATIBLE
    assert by_id["LF_EM4100RWC"].compatibility == Compatibility.COMPATIBLE
    assert by_id["LF_EM4100RSWB"].compatibility == Compatibility.COMPATIBLE
    assert by_id["LF_EM4100RSWW"].compatibility == Compatibility.COMPATIBLE
    assert by_id["HF_15SIM"].compatibility == Compatibility.COMPATIBLE
    assert by_id["HF_EMVPNG"].compatibility == Compatibility.COMPATIBLE
    assert by_id["HF_14ASNIFF"].compatibility == Compatibility.UNCERTAIN
    assert by_id["HF_15SNIFF"].compatibility == Compatibility.UNCERTAIN
    assert any("wiki oficial marca All" in note for note in by_id["LF_EM4100RWC"].limitations)
    assert any("BigBuf" in note for note in by_id["HF_15SIM"].limitations)
    assert any("não referencia WITH_FLASH" in note for note in by_id["HF_EMVPNG"].limitations)
    assert by_id["HF_ST25_TEAROFF"].compatibility == Compatibility.REQUIRES_FLASH
    assert any("#error" in note for note in by_id["HF_ST25_TEAROFF"].limitations)
    assert by_id["HF_REBLAY"].compatibility == Compatibility.INCOMPATIBLE
    assert any("REQ_BT" in note for note in by_id["HF_REBLAY"].limitations)
    assert by_id["HF_CARDHOPPER"].compatibility == Compatibility.INCOMPATIBLE
    assert by_id["HF_LEGIC_RDV4"].compatibility == Compatibility.INCOMPATIBLE
    assert by_id["LF_HIDFCBRUTE"].compatibility == Compatibility.INCOMPATIBLE
    automatic = {module.id for module in modules if module.compatibility == Compatibility.COMPATIBLE}
    assert "HF_REBLAY" not in automatic
    assert "HF_LEGIC_RDV4" not in automatic
    assert "LF_ICEHID" not in automatic
    assert "HF_14ASNIFF" not in automatic
    assert "HF_15SNIFF" not in automatic
    assert "HF_ST25_TEAROFF" not in automatic
    assert len(modules) == 41
    found = filter_modules(modules, "samy", "Low Frequency (LF)")
    assert [module.id for module in found] == ["LF_SAMYRUN"]
    hf = filter_modules(modules, "", "High Frequency (HF)")
    assert all(module.category.value.startswith("High") for module in hf)
    assert "LF_SAMYRUN" not in {module.id for module in hf}
