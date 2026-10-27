"""Lê regras de Standalone sem executar make e sem editar Makefile."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pm3manager.modules.catalog import _hal_table

_IDENT = re.compile(r"^[A-Z][A-Z0-9_]*$")
_MODE = re.compile(r"^STANDALONE_MODES\s*(\+=|:=|\?=|=)\s*(.*?)\s*$")
_REQ = re.compile(r"^STANDALONE_MODES_REQ_([A-Z0-9_]+)\s*(\+=|:=|\?=|=)\s*(.*?)\s*$")
_REQUIRED = ("FLASH", "BT", "SMARTCARD")


@dataclass(frozen=True)
class CheckoutRules:
    complete: bool
    reason: str
    modes: frozenset[str] = field(default_factory=frozenset)
    flash: frozenset[str] = field(default_factory=frozenset)
    bluetooth: frozenset[str] = field(default_factory=frozenset)
    smartcard: frozenset[str] = field(default_factory=frozenset)
    rdv4_only: frozenset[str] = field(default_factory=frozenset)
    pm5_standalone: str = "unknown"
    warnings: tuple[str, ...] = ()
    manual_commit: str = ""
    observed_commit: str = ""
    shallow: bool | None = None

    def limits(self, module_id: str) -> tuple[bool, bool, bool, bool]:
        return (
            module_id in self.modes,
            module_id in self.flash,
            module_id in self.bluetooth,
            module_id in self.smartcard or module_id in self.rdv4_only,
        )


def parse_hal(text: str) -> CheckoutRules:
    """Interpreta Makefile.hal. Estrutura inesperada deixa a análise incompleta."""
    body = text or ""
    if "define KNOWN_STANDALONE_DEFINITIONS" not in body or "STANDALONE_MODES" not in body:
        return CheckoutRules(False, "Makefile.hal não tem a tabela ou a lista STANDALONE_MODES.")
    modes: list[str] = []
    groups = {name: [] for name in _REQUIRED}
    seen_mode = False
    seen_req: set[str] = set()
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        mode_match = _MODE.match(line)
        if mode_match:
            operator, payload = mode_match.group(1), mode_match.group(2)
            if operator not in {":=", "+="} or (operator == "+=" and not seen_mode) or (operator == ":=" and seen_mode):
                return CheckoutRules(False, "STANDALONE_MODES usa um operador que esta versão não interpreta.")
            seen_mode = True
            tokens = payload.split()
            if any(not _IDENT.fullmatch(token) for token in tokens):
                return CheckoutRules(False, "STANDALONE_MODES contém um identificador que não foi aceito.")
            modes.extend(tokens)
            continue
        req_match = _REQ.match(line)
        if req_match:
            name, operator, payload = req_match.group(1), req_match.group(2), req_match.group(3)
            if name not in groups:
                return CheckoutRules(False, f"Requisito desconhecido no Makefile.hal: {name}.")
            if operator != ":=" or name in seen_req:
                return CheckoutRules(False, f"STANDALONE_MODES_REQ_{name} não está numa atribuição simples.")
            seen_req.add(name)
            tokens = payload.split()
            if any(not _IDENT.fullmatch(token) for token in tokens):
                return CheckoutRules(False, f"STANDALONE_MODES_REQ_{name} contém um identificador inválido.")
            groups[name] = tokens
    if not seen_mode or not modes:
        return CheckoutRules(False, "STANDALONE_MODES não produziu uma lista utilizável.")
    missing = [name for name in _REQUIRED if name not in seen_req]
    if missing:
        return CheckoutRules(False, "Falta uma lista de requisito: " + ", ".join(missing) + ".")
    mode_set = set(modes)
    if len(mode_set) != len(modes):
        return CheckoutRules(False, "STANDALONE_MODES repete um identificador.")
    for name, tokens in groups.items():
        unknown = [token for token in tokens if token not in mode_set]
        if unknown:
            return CheckoutRules(False, f"STANDALONE_MODES_REQ_{name} cita um modo fora da lista.")
    try:
        _descriptions, rdv4 = _hal_table(body)
    except Exception:
        return CheckoutRules(False, "A tabela KNOWN_STANDALONE_DEFINITIONS não foi interpretada.")
    if any(item not in mode_set for item in rdv4):
        return CheckoutRules(False, "A tabela marca RDV4 num modo que não está em STANDALONE_MODES.")
    return CheckoutRules(
        True,
        "",
        modes=frozenset(modes),
        flash=frozenset(groups["FLASH"]),
        bluetooth=frozenset(groups["BT"]),
        smartcard=frozenset(groups["SMARTCARD"]),
        rdv4_only=frozenset(rdv4),
    )


def pm5_standalone_state(source: str) -> str:
    """blocked só quando o próprio fonte guarda RunMod atrás de PM5. Caso contrário, unknown."""
    if not source or "RunMod()" not in source or "#ifndef PM5" not in source:
        return "unknown"
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if "RunMod()" not in line:
            continue
        before = "\n".join(lines[max(0, index - 12):index])
        after = "\n".join(lines[index:index + 16])
        if "#ifndef PM5" in before and "blocking standalone" in after.lower():
            return "blocked"
    return "unknown"


def load_checkout_rules(
    repo: Path,
    *,
    manual_commit: str = "",
    observed_commit: str = "",
    shallow: bool | None = None,
) -> CheckoutRules:
    hal_path = repo / "armsrc" / "Standalone" / "Makefile.hal"
    app_path = repo / "armsrc" / "appmain.c"
    warnings: list[str] = []
    if shallow is True:
        warnings.append("O checkout local é raso. A análise não trata a árvore como completa.")
    if manual_commit and observed_commit and manual_commit != observed_commit:
        warnings.append(
            "O commit observado não é o usado para documentar o manual. O manual não substitui o Makefile."
        )
    try:
        hal_text = hal_path.read_text(encoding="utf-8", errors="replace") if hal_path.is_file() else ""
    except OSError:
        hal_text = ""
    rules = parse_hal(hal_text) if hal_text else CheckoutRules(False, "Makefile.hal não foi encontrado.")
    try:
        app_text = app_path.read_text(encoding="utf-8", errors="replace") if app_path.is_file() else ""
    except OSError:
        app_text = ""
    state = pm5_standalone_state(app_text)
    return CheckoutRules(
        complete=rules.complete,
        reason=rules.reason,
        modes=rules.modes,
        flash=rules.flash,
        bluetooth=rules.bluetooth,
        smartcard=rules.smartcard,
        rdv4_only=rules.rdv4_only,
        pm5_standalone=state,
        warnings=tuple(warnings),
        manual_commit=manual_commit,
        observed_commit=observed_commit,
        shallow=shallow,
    )


def shallow_checkout(repo: Path) -> bool | None:
    git = repo / ".git"
    if not git.exists():
        return None
    if (repo / ".git" / "shallow").is_file():
        return True
    return False
