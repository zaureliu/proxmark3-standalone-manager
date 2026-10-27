"""URLs que a ficha pode abrir. `master` não é aceito para código."""

from __future__ import annotations

from urllib.parse import urlparse

_HOST = "github.com"
_ROOT = "/rfidresearchgroup/proxmark3"
_WIKI = "/rfidresearchgroup/proxmark3/wiki/standalone-mode"
_COMMIT = r"0123456789abcdef"


def is_allowed(url: str) -> bool:
    text = (url or "").strip()
    if not text or any(char.isspace() for char in text):
        return False
    parsed = urlparse(text)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query:
        return False
    if (parsed.hostname or "").lower() != _HOST:
        return False
    path = parsed.path.rstrip("/")
    lowered = path.casefold()
    if ".." in path or "\\" in path:
        return False
    if lowered == _ROOT or lowered == _WIKI:
        return True
    marker = "/rfidresearchgroup/proxmark3/blob/"
    tree = "/rfidresearchgroup/proxmark3/tree/"
    for prefix in (marker, tree):
        if not lowered.startswith(prefix):
            continue
        rest = path[len(prefix):]
        commit, _sep, tail = rest.partition("/")
        if len(commit) != 40 or any(char not in _COMMIT for char in commit.lower()):
            return False
        if not tail or tail.startswith("/"):
            return False
        return True
    return False


def is_relative_source(path: str) -> bool:
    text = (path or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or ".." in text.split("/"):
        return False
    if "://" in text or ":" in text:
        return False
    return True
