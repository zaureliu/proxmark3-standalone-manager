"""Notas recebidas do GitHub são texto não confiável.

O resultado fica em texto puro. Não há HTML, imagem ou comando para executar.
"""

from __future__ import annotations

import re

_TAG = re.compile(r"<[^>]*>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def plain_text(value: str, limit: int = 6000) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _TAG.sub("", text)
    text = _CONTROL.sub("", text)
    text = text.strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "\n…"
    return text


def commit_line(sha: str, message: str) -> str:
    subject = plain_text(message, limit=160).split("\n", 1)[0].strip()
    token = (sha or "").strip()
    short = token[:12] if re.fullmatch(r"[0-9a-fA-F]{7,40}", token) else ""
    if short and subject:
        return f"{short} {subject}"
    return short or subject
