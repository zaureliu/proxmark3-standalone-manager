"""Estados do monitor. A comparação não usa só o texto da versão."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

MIN_INTERVAL_MINUTES = 15
MAX_INTERVAL_MINUTES = 24 * 60
DEFAULT_INTERVAL_MINUTES = 60

UNKNOWN_VERSION = "Versão local não identificada"


class Relation(str, Enum):
    CURRENT = "atualizado"
    NEW_RELEASE = "nova_release"
    NEW_COMMITS = "novos_commits"
    LOCAL_AHEAD = "local_a_frente"
    DIVERGED = "divergente"
    LOCAL_UNKNOWN = "versao_desconhecida"
    UNAVAILABLE = "indisponivel"


def clamp_interval(value: object) -> int:
    try:
        minutes = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_MINUTES
    if minutes < MIN_INTERVAL_MINUTES:
        return MIN_INTERVAL_MINUTES
    if minutes > MAX_INTERVAL_MINUTES:
        return MAX_INTERVAL_MINUTES
    return minutes


@dataclass(frozen=True)
class LocalInstall:
    present: bool = False
    kind: str = "ausente"
    path: str = ""
    version: str = ""
    version_label: str = UNKNOWN_VERSION
    commit: str = ""
    branch: str = ""
    tag: str = ""
    detached: bool = False
    dirty: bool = False
    unpushed: int | None = None
    remote_url: str = ""
    platform: str = ""
    standalone: str = ""
    extras: str = ""
    firmware_commit: str = ""
    notes: tuple[str, ...] = ()

    @property
    def commit_short(self) -> str:
        text = self.commit.strip()
        return text[:12] if text else ""


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    name: str
    published_at: str
    html_url: str
    notes: str
    sha: str = ""


@dataclass(frozen=True)
class RemoteView:
    archived: bool = False
    default_branch: str = ""
    html_url: str = ""
    release: ReleaseInfo | None = None
    branch_sha: str = ""
    branch_date: str = ""
    branch_summary: str = ""
    compare_status: str = ""
    release_compare: str = ""
    ahead_by: int = 0
    behind_by: int = 0
    commit_lines: tuple[str, ...] = ()
    not_modified: bool = False

    @property
    def branch_short(self) -> str:
        return self.branch_sha[:12] if self.branch_sha else ""


@dataclass
class ProviderReport:
    key: str
    title: str
    web_url: str
    local: LocalInstall
    remote: RemoteView | None
    relation: Relation
    message: str
    compatibility: str
    fresh: bool
    cached: bool
    checked_at: str
    error: str = ""
    notification_id: str = ""
    announce: bool = False
    announce_text: str = ""

    @property
    def archived(self) -> bool:
        return bool(self.remote and self.remote.archived)


@dataclass
class MonitorReport:
    iceman: ProviderReport
    proxspace: ProviderReport
    busy: bool = False
