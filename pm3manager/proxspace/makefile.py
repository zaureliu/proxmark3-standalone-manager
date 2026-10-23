"""Grava o Makefile.platform na raiz do checkout, que é o único arquivo lido pelo make.

O padrão do código, sem esse arquivo, é PM3RDV4. O arquivo em ``pm3/Makefile.platform``
não entra no include e não é modificado. Uma compilação bem-sucedida mantém o arquivo
do checkout; uma falha ou interrupção restaura o estado anterior.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from pm3manager.errors import MakefileError
from pm3manager.models import BuildConfig

HEADER = "# --- BEGIN Proxmark3 Standalone Manager ---"
FOOTER = "# --- END Proxmark3 Standalone Manager ---"
_KEYS = ("PLATFORM", "PLATFORM_EXTRAS", "PLATFORM_SIZE", "STANDALONE", "LED_ORDER")
_BACKUP_NAME = re.compile(r"Makefile\.platform\..+\.bak")
_ASSIGN = re.compile(
    r"^(?P<indent>\s*)(?P<export>export\s+)?"
    r"(?P<key>PLATFORM|PLATFORM_EXTRAS|PLATFORM_SIZE|STANDALONE|LED_ORDER)"
    r"(?P<op>\s*[:?+]?=)(?P<value>.*)$"
)


def active_assignments(text: str) -> dict[str, list[str]]:
    found = {key: [] for key in _KEYS}
    for line in text.splitlines():
        match = _ASSIGN.match(line)
        if match:
            found[match.group("key")].append(match.group("value").strip())
    return found


def strip_managed_blocks(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == HEADER:
            skipping = True
            continue
        if line.strip() == FOOTER:
            skipping = False
            continue
        if not skipping:
            output.append(line)
    return "\n".join(output).rstrip() + ("\n" if output else "")


def render_makefile(original: str, config: BuildConfig) -> str:
    config.validate()
    base = strip_managed_blocks(original)
    rewritten: list[str] = []
    for line in base.splitlines():
        match = _ASSIGN.match(line)
        if match:
            rewritten.append(f"# {line}  # preservado pelo Proxmark3 Standalone Manager")
        else:
            rewritten.append(line)
    while rewritten and rewritten[-1] == "":
        rewritten.pop()
    block = [
        "",
        HEADER,
        "# Mantido neste checkout para o make não voltar ao padrão PM3RDV4.",
        "# LED_ORDER=PM3EASY só define CHIP_AT91SAM7S no alvo PM3GENERIC. Não identifica o modelo.",
        "PLATFORM=PM3GENERIC",
        "LED_ORDER=PM3EASY",
        f"STANDALONE={config.standalone}",
    ]
    if config.extras:
        block.append(f"PLATFORM_EXTRAS={' '.join(config.extras)}")
    if config.platform_size:
        block.append(f"PLATFORM_SIZE={config.platform_size}")
    block.append(FOOTER)
    text = "\n".join(rewritten + block) + "\n"
    validate_rendered(text, config)
    return text


def validate_rendered(text: str, config: BuildConfig) -> None:
    found = active_assignments(text)
    expected_extras = [" ".join(config.extras)] if config.extras else []
    expected_size = [config.platform_size] if config.platform_size else []
    problems: list[str] = []
    if found["PLATFORM"] != ["PM3GENERIC"]:
        problems.append(f"PLATFORM={found['PLATFORM']}")
    if found["STANDALONE"] != [config.standalone]:
        problems.append(f"STANDALONE={found['STANDALONE']}")
    if found["LED_ORDER"] != ["PM3EASY"]:
        problems.append(f"LED_ORDER={found['LED_ORDER']}")
    if found["PLATFORM_EXTRAS"] != expected_extras:
        problems.append(f"PLATFORM_EXTRAS={found['PLATFORM_EXTRAS']}")
    if found["PLATFORM_SIZE"] != expected_size:
        problems.append(f"PLATFORM_SIZE={found['PLATFORM_SIZE']}")
    if problems:
        raise MakefileError("E003", "Makefile.platform gerado ficou inconsistente.", "; ".join(problems))


def _assert_platform_target(target: Path) -> None:
    """Só o Makefile.platform de um checkout em pm3/proxmark3* pode ser substituído."""
    if target.is_symlink() or target.name != "Makefile.platform":
        raise MakefileError(
            "E003",
            "Makefile.platform é um link ou não tem o nome esperado. Nada foi alterado.",
            str(target),
        )
    repo = target.parent
    pm3 = repo.parent
    if repo.is_symlink() or pm3.is_symlink() or pm3.name != "pm3" or not repo.name.startswith("proxmark3"):
        raise MakefileError(
            "E003",
            "Makefile.platform fora de pm3/proxmark3. Nada foi alterado.",
            str(target),
        )


def _assert_backup(backup: Path) -> None:
    if backup.is_symlink() or not _BACKUP_NAME.fullmatch(backup.name):
        raise MakefileError(
            "E003",
            "O backup do Makefile.platform não é um arquivo comum com o nome esperado.",
            str(backup),
        )


class MakefileSession:
    def __init__(self, repo: Path, state_dir: Path, backup_dir: Path, config: BuildConfig) -> None:
        self.target = repo / "Makefile.platform"
        self.state_path = state_dir / "build_session.json"
        self.backup_dir = backup_dir
        self.config = config
        self.backup_path: Path | None = None

    def __enter__(self) -> "MakefileSession":
        _assert_platform_target(self.target)
        if self.backup_dir.is_symlink():
            raise MakefileError("E003", "A pasta de backup é um link. Nada foi alterado.", str(self.backup_dir))
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.backup_path = self.backup_dir / f"Makefile.platform.{stamp}.bak"
        _assert_backup(self.backup_path)
        existed = self.target.is_file()
        self.backup_path.write_bytes(self.target.read_bytes() if existed else b"")
        state = {
            "phase": "open",
            "existed": existed,
            "backup": str(self.backup_path),
            "target": str(self.target),
            "standalone": self.config.standalone,
        }
        self._write_state(state)
        original = self.target.read_text(encoding="utf-8", errors="replace") if existed else ""
        try:
            rendered = render_makefile(original, self.config)
            self.target.write_bytes(rendered.encode("utf-8"))
        except Exception:
            self.restore()
            raise
        return self

    def keep(self) -> None:
        """Mantém o Makefile.platform do checkout. Sem ele o próximo make volta a PM3RDV4."""
        if not self.state_path.is_file():
            return
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if state.get("phase") == "open":
            state["phase"] = "kept"
            self._write_state(state)

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.state_path.is_file():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if state.get("phase") == "open":
                self.restore()
        return False

    def restore(self) -> None:
        if not self.state_path.is_file():
            return
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if state.get("phase") == "restored":
            return
        backup = Path(state["backup"])
        target = Path(state["target"])
        try:
            _assert_platform_target(target)
            if state.get("existed"):
                _assert_backup(backup)
        except MakefileError:
            state["phase"] = "rejected"
            self._write_state(state)
            raise
        if state.get("existed"):
            if not backup.is_file():
                raise MakefileError("E003", "Backup do Makefile.platform desapareceu.", str(backup))
            target.write_bytes(backup.read_bytes())
        elif target.is_file():
            current = target.read_text(encoding="utf-8", errors="replace")
            if HEADER in current:
                target.unlink()
        state["phase"] = "restored"
        self._write_state(state)

    def _write_state(self, state: dict) -> None:
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)


def recover_interrupted(state_dir: Path) -> str | None:
    state_path = state_dir / "build_session.json"
    if not state_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if state.get("phase") != "open":
        return None
    session = MakefileSession(
        repo=Path(state["target"]).parent,
        state_dir=state_dir,
        backup_dir=Path(state["backup"]).parent,
        config=BuildConfig(platform="PM3GENERIC", standalone="LF_SAMYRUN"),
    )
    session.state_path = state_path
    try:
        session.restore()
    except MakefileError:
        return (
            "Uma compilação anterior apontava para um Makefile.platform fora do checkout. "
            "Nada foi restaurado."
        )
    return "Uma compilação anterior foi interrompida. O Makefile.platform original foi restaurado."
