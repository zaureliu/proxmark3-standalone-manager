"""Texto, hashes e validação de argumentos que entram em subprocesso."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_MODULE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_COM = re.compile(r"^COM([0-9]{1,3})$", re.IGNORECASE)
_BATCH_UNSAFE = re.compile(r'[\x00-\x1f"!%&^|<>]')
_MSYS_SAFE = re.compile(r"/[A-Za-z0-9_./() -]+")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_module_id(value: str) -> bool:
    return bool(_MODULE.fullmatch(value or ""))


def normalize_com(value: str) -> str:
    match = _COM.fullmatch((value or "").strip())
    if not match:
        raise ValueError(f"Porta COM inválida: {value!r}")
    return f"COM{int(match.group(1))}"


def batch_path(path: Path) -> str:
    """Caminho seguro para um .bat entre aspas. Rejeita aspas, % e quebras de linha."""
    text = str(path)
    if not text.isascii() or _BATCH_UNSAFE.search(text):
        text = _short_windows_path(path)
    if not text or not text.isascii() or _BATCH_UNSAFE.search(text):
        raise ValueError(f"Caminho não é seguro para o script do ProxSpace: {path}")
    return text


def to_msys_path(path: Path) -> str:
    resolved = Path(batch_path(path)).resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive or not drive.isalpha():
        raise ValueError(f"Caminho sem unidade: {resolved}")
    rest = resolved.as_posix().split(":", 1)[1]
    msys = f"/{drive}{rest}"
    if not _MSYS_SAFE.fullmatch(msys):
        raise ValueError(f"Caminho MSYS não é seguro para o shell: {msys}")
    return msys


def bash_invocation(msys_script: str) -> str:
    if re.fullmatch(r"/[A-Za-z0-9_./-]+", msys_script):
        return f"bash {msys_script}"
    if "'" in msys_script or not _MSYS_SAFE.fullmatch(msys_script):
        raise ValueError(f"Caminho MSYS não é seguro para o shell: {msys_script}")
    return f"bash '{msys_script}'"


def _short_windows_path(path: Path) -> str:
    if not path.exists():
        return ""
    import ctypes

    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    if not length:
        return ""
    return buffer.value
