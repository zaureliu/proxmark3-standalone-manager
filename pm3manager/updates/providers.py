"""Repositórios oficiais. O monitor não aceita outra origem."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    key: str
    title: str
    owner: str
    name: str
    api: str
    web: str


ICEMAN = Provider(
    key="iceman",
    title="Iceman",
    owner="RfidResearchGroup",
    name="proxmark3",
    api="https://api.github.com/repos/RfidResearchGroup/proxmark3",
    web="https://github.com/RfidResearchGroup/proxmark3",
)

PROXSPACE = Provider(
    key="proxspace",
    title="ProxSpace",
    owner="Gator96100",
    name="ProxSpace",
    api="https://api.github.com/repos/Gator96100/ProxSpace",
    web="https://github.com/Gator96100/ProxSpace",
)

PROVIDERS = (ICEMAN, PROXSPACE)
BY_KEY = {item.key: item for item in PROVIDERS}


def provider_for(key: str) -> Provider:
    try:
        return BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"provedor desconhecido: {key}") from exc
