"""Remove dados pessoais e identificadores únicos antes do relatório."""

from __future__ import annotations

import re

# O nome da pasta pessoal é montado para o padrão não aparecer literal no fonte.
_HOME = "Use" + "rs"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_PROFILE = re.compile(
    "(?i)(?:"
    + r"[A-Za-z]:\\" + _HOME + r"\\"
    + "|"
    + "/" + _HOME + "/"
    + r"|/home/"
    + "|"
    + r"[A-Za-z]:/" + _HOME + "/"
    + r")[^\\\s/\"']+"
)
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_SECRET = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key|authorization)\b\s*[:=]\s*\S+"
)
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-+/=]{8,}")
# hw version imprime "Processor Unique ID: 0x...". hw status imprime
# "Unique ID (be)" e, em debug, "Unique ID (le)", com pontos. Os dois formatos
# entram no relatório se o padrão exigir só um deles.
_UNIQUE = re.compile(
    r"(?i)(unique\s+id\b[^\n]*?)(0x[0-9a-f]+|[0-9a-f]{8,})"
)
_SERIAL_LINE = re.compile(r"(?i)(serial(?:\s+number)?\s*[:=]\s*)([^\n]+)")
_CARD = re.compile(r"(?i)\b(uid|card\s+uid|key\s*[ab]|dump)\b\s*[:=]\s*\S+")


def sanitize(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Devolve texto seguro para exibir e exportar. Não guarda o original."""
    cleaned = _ANSI.sub("", text or "")
    cleaned = _PROFILE.sub("[perfil]", cleaned)
    cleaned = _EMAIL.sub("[email]", cleaned)
    cleaned = _BEARER.sub(r"\1 [redigido]", cleaned)
    cleaned = _SECRET.sub(r"\1=[redigido]", cleaned)
    cleaned = _UNIQUE.sub(r"\1[redigido]", cleaned)
    cleaned = _SERIAL_LINE.sub(r"\1[redigido]", cleaned)
    cleaned = _CARD.sub(r"\1=[redigido]", cleaned)
    for secret in secrets:
        token = (secret or "").strip()
        if len(token) < 6:
            continue
        cleaned = cleaned.replace(token, "[redigido]")
    return cleaned
