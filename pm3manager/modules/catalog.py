"""Lê os módulos reais de Makefile.hal, Makefile.inc e doc/standalone.

A documentação em doc/standalone avisa que parte do texto foi gerada e pode
estar errada. O requisito de compilação do Makefile.hal prevalece. Quando o
texto pede RDV4 ou flash e o Makefile não exige isso, o módulo fica incerto
e a gravação automática permanece bloqueada.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pm3manager.errors import ProxSpaceError
from pm3manager.models import Category, Compatibility, Environment, Module
from pm3manager.preferences import Preferences

# [ \t] de propósito: \s atravessa a quebra de linha e a linha vazia
# STANDALONE_MODES_REQ_SMARTCARD := engolia a lista de FLASH.
_MODE_LINE = re.compile(r"^STANDALONE_MODES(?: \+=| :=)[ \t]*(.*)$", re.MULTILINE)
_REQ_LINE = re.compile(r"^STANDALONE_MODES_REQ_([A-Z]+) :=[ \t]*(.*)$", re.MULTILINE)
_SRC = re.compile(
    r"WITH_STANDALONE_([A-Z0-9_]+).*?\n\s*SRC_STANDALONE = ([^\n]+)",
    re.DOTALL,
)
_HEADING = re.compile(r"^#\s+.+?[—-]\s+(.+)$", re.MULTILINE)
_HARDWARE = re.compile(r"\*\*Hardware:\*\*\s*(.+)")
_FREQUENCY = re.compile(r"\*\*Frequency:\*\*\s*(.+)")
_WHAT = re.compile(r"## What\s+(.+?)(?:\n## |\Z)", re.DOTALL)


def _hal_table(text: str) -> tuple[dict[str, str], set[str]]:
    try:
        body = text.split("define KNOWN_STANDALONE_DEFINITIONS", 1)[1].split("endef", 1)[0]
    except IndexError as exc:
        raise ProxSpaceError("E002", "Makefile.hal não contém a tabela de Standalone.") from exc
    descriptions: dict[str, str] = {}
    rdv4: set[str] = set()
    current = ""
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        left, right = cells[0], cells[1]
        if left.startswith("(") and current:
            if "RDV4" in left.upper():
                rdv4.add(current)
            continue
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", left):
            current = left
            descriptions[left] = right
        elif current and not left and right:
            descriptions[current] = f"{descriptions.get(current, '')} {right}".strip()
    return descriptions, rdv4


def _mode_ids(text: str) -> list[str]:
    found: list[str] = []
    for match in _MODE_LINE.finditer(text):
        for token in match.group(1).split():
            if token not in found:
                found.append(token)
    return found


def _requirements(text: str) -> dict[str, set[str]]:
    groups = {"BT": set(), "SMARTCARD": set(), "FLASH": set()}
    for match in _REQ_LINE.finditer(text):
        name = match.group(1)
        if name in groups:
            groups[name] = set(match.group(2).split())
    return groups


def _sources(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in _SRC.finditer(text):
        found[match.group(1)] = match.group(2).strip()
    return found


def _doc(repo: Path, module_id: str) -> tuple[str, str, str, str]:
    path = repo / "doc" / "standalone" / f"{module_id.lower()}.md"
    if not path.is_file():
        return "", "", "", ""
    text = path.read_text(encoding="utf-8", errors="replace")
    heading = _HEADING.search(text)
    hardware = _HARDWARE.search(text)
    frequency = _FREQUENCY.search(text)
    what = _WHAT.search(text)
    summary = ""
    if what:
        paragraph = what.group(1).strip().split("\n\n", 1)[0]
        summary = re.sub(r"\s+", " ", paragraph.replace("**", "")).strip()
    return (
        heading.group(1).strip() if heading else "",
        summary,
        hardware.group(1).strip() if hardware else "",
        frequency.group(1).strip() if frequency else "",
    )


def documentation_blocks_auto(hardware: str) -> bool:
    text = (hardware or "").lower()
    if not text:
        return False
    if any(word in text for word in ("recommended", "optional")) and "requires" not in text and "required" not in text:
        return False
    if "generic" in text and "requires" not in text and "required" not in text:
        return False
    return any(word in text for word in ("rdv4", "flash memory", "requires flash", "required"))


def _category(module_id: str) -> Category:
    if module_id == "LF_SKELETON":
        return Category.OTHER
    if module_id == "DANKARMULTI":
        return Category.MULTI
    if module_id.startswith("LF_"):
        return Category.LF
    if module_id.startswith("HF_"):
        return Category.HF
    return Category.OTHER


def _frequency(module_id: str, documented: str) -> str:
    if documented:
        return documented
    if module_id.startswith("LF_"):
        return "LF 125 kHz"
    if module_id.startswith("HF_"):
        return "HF 13.56 MHz"
    if module_id == "DANKARMULTI":
        return "LF + HF"
    return "Não informada"


def _classify(
    module_id: str,
    *,
    rdv4_only: bool,
    requires_flash: bool,
    requires_bt: bool,
    requires_smartcard: bool,
    doc_hardware: str,
    hal_description: str,
) -> tuple[Compatibility, tuple[str, ...]]:
    notes: list[str] = []
    if hal_description:
        notes.append(hal_description)
    if doc_hardware:
        notes.append(f"Documentação local: {doc_hardware}.")
    if "_RDV4" in module_id or rdv4_only or requires_bt or requires_smartcard:
        if rdv4_only or "_RDV4" in module_id:
            notes.append(
                "O Makefile.hal desta versão marca o modo como exclusivo de RDV4. "
                "Ele não será adaptado para PM3GENERIC."
            )
        if requires_bt:
            notes.append("Exige Bluetooth ou FPC USART. O aplicativo não habilita BTADDON.")
        if requires_smartcard:
            notes.append("Exige leitor de smartcard. O hw status deste aparelho não mostrou esse leitor.")
        compatibility = Compatibility.INCOMPATIBLE
    elif requires_flash:
        notes.append(
            "O Makefile exige WITH_FLASH. Em PM3GENERIC isso é PLATFORM_EXTRAS=FLASH, "
            "só depois da flash SPI ser confirmada. Não é tratado como exclusivo de RDV4."
        )
        compatibility = Compatibility.REQUIRES_FLASH
    elif documentation_blocks_auto(doc_hardware):
        notes.append(
            "A documentação local atribui RDV4 ou flash a este modo, mas o Makefile.hal não exige WITH_FLASH. "
            "Como o texto pode estar incorreto, a compilação fica bloqueada até a confirmação manual. "
            "FLASH não será ligado só por causa dessa frase."
        )
        compatibility = Compatibility.UNCERTAIN
    else:
        if "flash" in doc_hardware.lower():
            notes.append(
                "A documentação cita flash como recomendação ou recurso opcional. A compilação não liga FLASH por isso."
            )
        if module_id == "LF_SKELETON":
            notes.append("Modelo de desenvolvimento, não um modo de uso pronto.")
        if module_id == "DANKARMULTI":
            notes.append(
                "A imagem junta vários modos. O make desta versão assume 512 KB quando PLATFORM_SIZE não é definido."
            )
        compatibility = Compatibility.COMPATIBLE
    compatibility, notes = _review(module_id, compatibility, notes)
    return compatibility, tuple(notes)


# A wiki oficial de junho de 2025 e o .c desta árvore prevalecem sobre doc/standalone,
# que o próprio repositório descreve como texto gerado e às vezes incorreto.
_REVIEW_COMPATIBLE = {
    "LF_EM4100RWC": (
        "A wiki oficial marca All. O .c só persiste o slot na flash dentro de #ifdef WITH_FLASH; "
        "sem isso o modo usa RAM. O doc local que exige RDV4 não bloqueia a compilação."
    ),
    "LF_EM4100RSWB": (
        "A wiki oficial marca All. A gravação do ID na flash está em #ifdef WITH_FLASH e é opcional."
    ),
    "LF_EM4100RSWW": (
        "A wiki oficial marca All. O .c diz que, fora do RDV4, o padrão é ler e emular; a flash é opcional."
    ),
    "HF_15SIM": (
        "Não aparece na tabela da wiki de junho de 2025. Nesta árvore o simulador ISO15693 usa BigBuf; "
        "o log em flash é #ifdef WITH_FLASH. O doc local que pede RDV4 não tem respaldo no Makefile nem no .c."
    ),
    "HF_EMVPNG": (
        "Não aparece na tabela da wiki de junho de 2025. O .c não referencia WITH_FLASH, RDV4 nem Bluetooth. "
        "O doc local que exige RDV4 não é corroborado pelo código desta versão."
    ),
}
_REVIEW_UNCERTAIN = {
    "HF_14ASNIFF": (
        "A wiki oficial marca RDV4. O comentário do .c diz que o modo exige RDV4 para gravar o trace na flash. "
        "O sniff em RAM pode existir, mas a compilação automática fica bloqueada até confirmação."
    ),
    "HF_15SNIFF": (
        "A wiki oficial marca RDV4. O .c repete a exigência de RDV4 para gravar o trace. "
        "A compilação automática fica bloqueada até confirmação."
    ),
}
_REVIEW_NOTES = {
    "HF_REBLAY": (
        "A wiki de junho de 2025 marca All, mas o Makefile.hal instalado põe o modo em "
        "STANDALONE_MODES_REQ_BT e na coluna RDV4 only. O .c inclui usart.h para Bluetooth. "
        "O hw status não mostrou o add-on de BT. Permanece incompatível nesta versão."
    ),
    "HF_ST25_TEAROFF": (
        "O .c aborta a compilação sem WITH_FLASH (#error). O comentário do autor diz que testou "
        "num Easy com flash; isso não classifica esta placa. A wiki marca All / RDV4 *. "
        "O Makefile exige FLASH e não marca RDV4 only. Um trecho #if RDV4 || PM5 só muda a modulação."
    ),
    "HF_14BSNIFF": (
        "O Makefile descreve flash ou RAM. Sem WITH_FLASH o .c mantém o trace no BigBuf; "
        "a gravação SPIFFS fica em #ifdef WITH_FLASH. A compilação não exige RDV4."
    ),
}


def _review(
    module_id: str,
    compatibility: Compatibility,
    notes: list[str],
) -> tuple[Compatibility, list[str]]:
    if module_id in _REVIEW_COMPATIBLE and compatibility in {
        Compatibility.UNCERTAIN,
        Compatibility.COMPATIBLE,
    }:
        if compatibility == Compatibility.UNCERTAIN:
            notes = [note for note in notes if "bloqueada" not in note]
            compatibility = Compatibility.COMPATIBLE
        notes.append(_REVIEW_COMPATIBLE[module_id])
    elif module_id in _REVIEW_UNCERTAIN and compatibility in {
        Compatibility.COMPATIBLE,
        Compatibility.UNCERTAIN,
    }:
        notes = [note for note in notes if "bloqueada" not in note]
        notes.append(_REVIEW_UNCERTAIN[module_id])
        compatibility = Compatibility.UNCERTAIN
    extra = _REVIEW_NOTES.get(module_id)
    if extra:
        notes.append(extra)
    return compatibility, notes


def load_modules(env: Environment) -> list[Module]:
    hal_path = env.repo_root / "armsrc" / "Standalone" / "Makefile.hal"
    inc_path = env.repo_root / "armsrc" / "Standalone" / "Makefile.inc"
    if not hal_path.is_file():
        raise ProxSpaceError("E002", "Makefile.hal dos modos Standalone não encontrado.", str(hal_path))
    hal = hal_path.read_text(encoding="utf-8", errors="replace")
    inc = inc_path.read_text(encoding="utf-8", errors="replace") if inc_path.is_file() else ""
    descriptions, rdv4 = _hal_table(hal)
    requirements = _requirements(hal)
    sources = _sources(inc)
    modules: list[Module] = []
    for module_id in _mode_ids(hal):
        name, summary, hardware, frequency = _doc(env.repo_root, module_id)
        hal_description = descriptions.get(module_id, "")
        requires_flash = module_id in requirements["FLASH"]
        requires_bt = module_id in requirements["BT"]
        requires_smartcard = module_id in requirements["SMARTCARD"]
        rdv4_only = module_id in rdv4
        compatibility, notes = _classify(
            module_id,
            rdv4_only=rdv4_only,
            requires_flash=requires_flash,
            requires_bt=requires_bt,
            requires_smartcard=requires_smartcard,
            doc_hardware=hardware,
            hal_description=hal_description,
        )
        modules.append(
            Module(
                id=module_id,
                name=name or hal_description or module_id,
                description=summary or hal_description or "Sem descrição no repositório local.",
                frequency=_frequency(module_id, frequency),
                category=_category(module_id),
                compatibility=compatibility,
                hardware_requirements=hardware or hal_description or "Não informado.",
                limitations=notes,
                hal_description=hal_description,
                doc_hardware=hardware,
                requires_flash=requires_flash,
                requires_bt=requires_bt,
                requires_smartcard=requires_smartcard,
                rdv4_only=rdv4_only,
                source_file=sources.get(module_id, ""),
            )
        )
    return modules


def filter_modules(modules: list[Module], query: str, category: str) -> list[Module]:
    needle = (query or "").casefold().strip()
    selected: list[Module] = []
    for module in modules:
        if category and category != "Todas" and module.category.value != category:
            continue
        if needle:
            blob = " ".join(
                (
                    module.id,
                    module.name,
                    module.description,
                    module.frequency,
                    module.hardware_requirements,
                    module.hal_description,
                )
            ).casefold()
            if needle not in blob:
                continue
        selected.append(module)
    return selected


def can_apply(module: Module, prefs: Preferences) -> tuple[bool, str]:
    from pm3manager.messages import Msg

    if module.compatibility == Compatibility.INCOMPATIBLE:
        return False, Msg.INCOMPATIBLE_MODULE
    if module.compatibility == Compatibility.REQUIRES_FLASH and not prefs.spi_flash_confirmada:
        return False, Msg.FLASH_REQUIRED
    if module.compatibility == Compatibility.UNCERTAIN and module.id not in prefs.confirmed_uncertain_modules:
        return False, Msg.REQUIREMENTS
    return True, ""


def export_catalog(modules: list[Module], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": module.id,
            "nome": module.name,
            "descricao": module.description,
            "frequencia": module.frequency,
            "categoria": module.category.value,
            "compatibilidade": module.compatibility.value,
            "requisitos": module.hardware_requirements,
            "limitacoes": list(module.limitations),
            "requer_flash": module.requires_flash,
            "requer_bt": module.requires_bt,
            "exclusivo_rdv4": module.rdv4_only,
            "fonte": module.source_file,
        }
        for module in modules
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
