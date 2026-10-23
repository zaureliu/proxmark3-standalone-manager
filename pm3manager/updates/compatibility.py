"""A existência de uma release não prova que ela sirva neste hardware."""

from __future__ import annotations

NOT_VERIFIED = "Compatibilidade da atualização não verificada."

_DETAIL = (
    "A consulta não verifica Makefile, módulos Standalone, toolchain, "
    "bootloader, plataforma ou flash SPI. A imagem produzida por este "
    "aplicativo continua PM3GENERIC. RDV4 não é compilado nem gravado."
)


def compatibility_note(has_remote: bool) -> str:
    if not has_remote:
        return ""
    return NOT_VERIFIED


def compatibility_detail() -> str:
    return _DETAIL
