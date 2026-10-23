"""Orquestra as duas consultas. Uma verificação não entra por cima da outra."""

from __future__ import annotations

import threading

from pm3manager.updates.github_client import GitHubClient
from pm3manager.updates.models import LocalInstall, MonitorReport, ProviderReport, Relation
from pm3manager.updates.providers import ICEMAN, PROXSPACE
from pm3manager.updates.update_cache import UpdateCache
from pm3manager.updates.update_checker import cached_provider, check_provider
from pm3manager.updates.version_comparator import status_message


class UpdateService:
    def __init__(self, client: GitHubClient | None = None, cache: UpdateCache | None = None) -> None:
        self.client = client or GitHubClient()
        self.cache = cache or UpdateCache()
        self._gate = threading.Lock()

    @property
    def running(self) -> bool:
        locked = not self._gate.acquire(blocking=False)
        if not locked:
            self._gate.release()
        return locked

    def check(
        self,
        iceman: LocalInstall,
        proxspace: LocalInstall,
        cancel: threading.Event | None = None,
    ) -> MonitorReport:
        if not self._gate.acquire(blocking=False):
            report = self.cached_view(iceman, proxspace)
            report.busy = True
            return report
        try:
            token = cancel or threading.Event()
            return MonitorReport(
                iceman=check_provider(ICEMAN, iceman, self.client, self.cache, token),
                proxspace=check_provider(PROXSPACE, proxspace, self.client, self.cache, token),
            )
        finally:
            self._gate.release()

    def cached_view(
        self,
        iceman: LocalInstall,
        proxspace: LocalInstall,
        *,
        keep_stored_local: bool = False,
    ) -> MonitorReport:
        return MonitorReport(
            iceman=cached_provider(ICEMAN, iceman, self.cache, keep_stored_local=keep_stored_local),
            proxspace=cached_provider(PROXSPACE, proxspace, self.cache, keep_stored_local=keep_stored_local),
        )


def unavailable(key: str, title: str, web: str, local: LocalInstall) -> ProviderReport:
    relation = Relation.LOCAL_UNKNOWN if not local.present else Relation.UNAVAILABLE
    return ProviderReport(
        key=key,
        title=title,
        web_url=web,
        local=local,
        remote=None,
        relation=relation,
        message=status_message(key, relation, archived=False, cached=False),
        compatibility="",
        fresh=False,
        cached=False,
        checked_at="",
    )
