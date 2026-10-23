"""Relação entre a instalação local e a referência oficial.

Uma release só conta como mais nova quando a versão parseada é maior e o
commit da release está à frente do commit local na mesma linha de histórico.
Hashes diferentes, sozinhos, não anunciam atualização.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pm3manager.updates.models import UNKNOWN_VERSION, LocalInstall, Relation, RemoteView

_VERSION = re.compile(r"v?(\d+(?:\.\d+)+)")
_SHA = re.compile(r"^[0-9a-fA-F]{7,40}$")


@dataclass(frozen=True)
class ParsedVersion:
    raw: str
    parts: tuple[int, ...]
    known: bool


def parse_version(text: str) -> ParsedVersion:
    raw = (text or "").strip()
    match = _VERSION.search(raw)
    if not match:
        return ParsedVersion(raw, (), False)
    parts = tuple(int(item) for item in match.group(1).split("."))
    if any(part < 0 or part > 1_000_000 for part in parts):
        return ParsedVersion(raw, (), False)
    return ParsedVersion(raw, parts, True)


def version_order(left: ParsedVersion, right: ParsedVersion) -> int | None:
    """-1 se left é mais antiga, 0 se iguais, 1 se left é mais nova."""
    if not left.known or not right.known:
        return None
    width = max(len(left.parts), len(right.parts))
    first = left.parts + (0,) * (width - len(left.parts))
    second = right.parts + (0,) * (width - len(right.parts))
    if first < second:
        return -1
    if first > second:
        return 1
    return 0


def same_commit(left: str, right: str) -> bool:
    first = (left or "").strip().lower()
    second = (right or "").strip().lower()
    if not first or not second:
        return False
    if not _SHA.fullmatch(first) or not _SHA.fullmatch(second):
        return False
    if first == second:
        return True
    short, full = (first, second) if len(first) < len(second) else (second, first)
    return len(short) >= 7 and full.startswith(short)


def classify(local: LocalInstall, remote: RemoteView | None) -> tuple[Relation, str]:
    """Devolve o estado e o identificador de notificação, se houver.

    ``compare_status`` é a comparação do commit local com a ponta da branch
    oficial. ``release_compare`` é a comparação com o commit da última release.
    """
    if remote is None:
        return Relation.UNAVAILABLE, ""
    if not local.commit:
        return Relation.LOCAL_UNKNOWN, ""
    if remote.compare_status in {"diverged", "missing"}:
        return Relation.DIVERGED, ""

    gap = _version_gap(local, remote)
    release = remote.release
    if (
        release is not None
        and gap is not None
        and gap < 0
        and remote.release_compare == "ahead"
    ):
        return Relation.NEW_RELEASE, f"release:{release.tag}" if release.tag else ""
    if remote.compare_status == "ahead":
        token = remote.branch_sha
        return Relation.NEW_COMMITS, f"commit:{token}" if token else ""
    if remote.compare_status == "behind":
        return Relation.LOCAL_AHEAD, ""
    if remote.compare_status in {"identical", "same"} or same_commit(local.commit, remote.branch_sha):
        return Relation.CURRENT, ""
    if remote.compare_status == "":
        return Relation.UNAVAILABLE, ""
    return Relation.UNAVAILABLE, ""


def _version_gap(local: LocalInstall, remote: RemoteView) -> int | None:
    release = remote.release
    if release is None:
        return None
    local_version = parse_version(local.version or local.tag)
    remote_version = parse_version(release.tag or release.name)
    return version_order(local_version, remote_version)


def status_message(key: str, relation: Relation, *, archived: bool, cached: bool) -> str:
    names = {
        Relation.CURRENT: "Iceman atualizado." if key == "iceman" else "ProxSpace atualizado.",
        Relation.NEW_RELEASE: "Nova release disponível.",
        Relation.NEW_COMMITS: "Novos commits disponíveis.",
        Relation.LOCAL_AHEAD: "O checkout local está à frente da referência oficial.",
        Relation.DIVERGED: "O histórico local divergiu da referência oficial.",
        Relation.LOCAL_UNKNOWN: UNKNOWN_VERSION + ".",
        Relation.UNAVAILABLE: "Não foi possível consultar o GitHub.",
    }
    text = names[relation]
    if archived and key == "proxspace":
        text = f"{text} Repositório ProxSpace arquivado."
    elif archived:
        text = f"{text} Repositório arquivado."
    if cached:
        return f"Exibindo resultado da última verificação. {text}"
    return text


def announce_text(key: str, relation: Relation) -> str:
    if relation == Relation.NEW_RELEASE and key == "iceman":
        return "Nova versão do Iceman disponível."
    if relation == Relation.NEW_RELEASE and key == "proxspace":
        return "Nova versão do ProxSpace disponível."
    if relation == Relation.NEW_COMMITS:
        return "Novos commits disponíveis."
    return ""
