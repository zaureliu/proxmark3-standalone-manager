"""Códigos internos de erro. A mensagem ao usuário fica em português; o detalhe vai para o log."""

from __future__ import annotations


class AppError(Exception):
    def __init__(self, code: str, message: str, technical: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.technical = technical or message


class ProxSpaceError(AppError):
    pass


class MakefileError(AppError):
    pass


class BuildError(AppError):
    pass


class FlashError(AppError):
    pass


class SecurityError(AppError):
    pass


class BusyError(AppError):
    def __init__(self) -> None:
        super().__init__("E010", "Já existe uma compilação ou gravação em andamento.")
