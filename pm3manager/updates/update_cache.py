"""Cache das consultas. Fica no diretório de dados, separado do cache de firmware."""

from __future__ import annotations

import json
from pathlib import Path

from pm3manager import paths as paths_module


class UpdateCache:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory if directory is not None else paths_module.data_dir() / "updates"
        self.path = self.directory / "monitor.json"
        self._data = {
            "notified": [],
            "dismissed": [],
            "providers": {},
        }
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        notified = raw.get("notified", [])
        dismissed = raw.get("dismissed", [])
        providers = raw.get("providers", {})
        self._data = {
            "notified": [str(item) for item in notified] if isinstance(notified, list) else [],
            "dismissed": [str(item) for item in dismissed] if isinstance(dismissed, list) else [],
            "providers": providers if isinstance(providers, dict) else {},
        }

    def save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def etag(self, provider: str, slot: str) -> str:
        return str(self._provider(provider).get("etags", {}).get(slot, "") or "")

    def body(self, provider: str, slot: str):
        bodies = self._provider(provider).get("bodies", {})
        if not isinstance(bodies, dict) or slot not in bodies:
            return None
        return bodies[slot]

    def put_body(self, provider: str, slot: str, etag: str, body) -> None:
        entry = self._provider(provider)
        etags = entry.setdefault("etags", {})
        bodies = entry.setdefault("bodies", {})
        if isinstance(etag, str):
            etags[slot] = etag
        bodies[slot] = body
        self.save()

    def stored_report(self, provider: str) -> dict | None:
        report = self._provider(provider).get("report")
        return report if isinstance(report, dict) else None

    def store_report(self, provider: str, payload: dict) -> None:
        self._provider(provider)["report"] = payload
        self.save()

    def notified(self) -> set[str]:
        return set(self._data["notified"])

    def dismissed(self) -> set[str]:
        return set(self._data["dismissed"])

    def mark_notified(self, identifiers: tuple[str, ...] | list[str]) -> None:
        known = self.notified()
        changed = False
        for item in identifiers:
            if item and item not in known:
                self._data["notified"].append(item)
                known.add(item)
                changed = True
        if changed:
            self.save()

    def dismiss(self, identifiers: tuple[str, ...] | list[str]) -> None:
        known = self.dismissed()
        changed = False
        for item in identifiers:
            if item and item not in known:
                self._data["dismissed"].append(item)
                known.add(item)
                changed = True
        if changed:
            self.save()

    def _provider(self, provider: str) -> dict:
        providers = self._data["providers"]
        entry = providers.get(provider)
        if not isinstance(entry, dict):
            entry = {}
            providers[provider] = entry
        return entry
