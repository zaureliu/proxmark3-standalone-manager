"""Cliente da API REST do GitHub. Não usa token e não faz scraping."""

from __future__ import annotations

import json
import socket
import ssl
from dataclasses import dataclass
from http.client import HTTPException, HTTPSConnection
from urllib.parse import urlsplit

from pm3manager import __version__
from pm3manager.updates.providers import PROVIDERS

_ALLOWED_PREFIXES = tuple(item.api for item in PROVIDERS)
_MAX_BODY = 1_000_000
_COMPARE_MAX_BODY = 4_000_000
_MAX_REDIRECTS = 3


class GitHubError(Exception):
    def __init__(self, kind: str, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class ApiResponse:
    status: int
    data: dict | list | None
    etag: str
    not_modified: bool


def user_agent() -> str:
    return (
        f"Proxmark3StandaloneManager/{__version__} "
        "(+https://github.com/zaureliu/proxmark3-standalone-manager)"
    )


def validate_api_url(url: str) -> str:
    """Só https://api.github.com nos dois repositórios oficiais, sem query."""
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise GitHubError("url", "URL fora da API oficial do GitHub.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise GitHubError("url", "URL da API recusada.")
    if parsed.port not in {None, 443}:
        raise GitHubError("url", "Porta da API recusada.")
    if any(part == ".." for part in parsed.path.split("/")):
        raise GitHubError("url", "Caminho da API recusado.")
    if not any(url.startswith(prefix + "/") or url == prefix for prefix in _ALLOWED_PREFIXES):
        raise GitHubError("url", "Repositório fora da lista oficial.")
    return url


class UrllibTransport:
    """Uma conexão HTTPS por chamada, com tempos separados de conexão e leitura."""

    def __init__(self, connect_timeout: float = 10.0, read_timeout: float = 20.0) -> None:
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

    def __call__(self, url: str, headers: dict[str, str], max_body: int | None = None) -> HttpResponse:
        current = validate_api_url(url)
        context = ssl.create_default_context()
        last_error: Exception | None = None
        for _ in range(_MAX_REDIRECTS + 1):
            parsed = urlsplit(current)
            connection = HTTPSConnection(parsed.hostname, timeout=self.connect_timeout, context=context)
            try:
                path = parsed.path or "/"
                try:
                    connection.request("GET", path, headers=headers)
                    if connection.sock is not None:
                        connection.sock.settimeout(self.read_timeout)
                    response = connection.getresponse()
                except socket.timeout as exc:
                    raise GitHubError("timeout", "Tempo esgotado ao consultar o GitHub.") from exc
                except (TimeoutError, socket.gaierror, OSError, HTTPException) as exc:
                    raise GitHubError("connection", "Não foi possível consultar o GitHub.") from exc
                status = response.status
                response_headers = {key.lower(): value for key, value in response.getheaders()}
                if status in {301, 302, 303, 307, 308}:
                    location = response_headers.get("location", "")
                    response.read(1024)
                    try:
                        current = validate_api_url(location)
                    except GitHubError as exc:
                        raise GitHubError("redirect", "Redirecionamento recusado.", status) from exc
                    continue
                limit = _MAX_BODY if max_body is None else max_body
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise GitHubError("http", "Resposta do GitHub grande demais.", status)
                return HttpResponse(status=status, headers=response_headers, body=body)
            finally:
                connection.close()
        raise GitHubError("redirect", "Redirecionamentos demais.") from last_error


class GitHubClient:
    def __init__(self, transport=None, now=None) -> None:
        self.transport = transport or UrllibTransport()
        self._now = now or __import__("time").time
        self.rate_remaining: int | None = None
        self.rate_reset: float = 0

    def get_json(
        self,
        url: str,
        etag: str = "",
        *,
        missing_ok: bool = False,
        max_body: int | None = None,
    ) -> ApiResponse:
        validate_api_url(url)
        if self.rate_remaining == 0 and self._now() < self.rate_reset:
            raise GitHubError("rate", "Limite da API do GitHub atingido.", 429)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": user_agent(),
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if etag:
            headers["If-None-Match"] = etag
        try:
            if max_body is None:
                response = self.transport(url, headers)
            else:
                response = self.transport(url, headers, max_body)
        except GitHubError:
            raise
        except socket.timeout as exc:
            raise GitHubError("timeout", "Tempo esgotado ao consultar o GitHub.") from exc
        except (TimeoutError, socket.gaierror, OSError) as exc:
            raise GitHubError("connection", "Não foi possível consultar o GitHub.") from exc
        self._remember_rate(response.headers)
        if response.status == 304:
            return ApiResponse(304, None, response.headers.get("etag", etag), True)
        if response.status == 404 and missing_ok:
            return ApiResponse(404, None, "", False)
        if response.status in {403, 429} and _rate_limited(response):
            raise GitHubError("rate", "Limite da API do GitHub atingido.", response.status)
        if response.status >= 400:
            raise GitHubError("http", f"O GitHub respondeu HTTP {response.status}.", response.status)
        try:
            data = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubError("json", "Resposta JSON inválida.") from exc
        if not isinstance(data, (dict, list)):
            raise GitHubError("json", "Resposta JSON inválida.")
        return ApiResponse(response.status, data, response.headers.get("etag", ""), False)

    def _remember_rate(self, headers: dict[str, str]) -> None:
        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")
        if remaining is not None and remaining.isdigit():
            self.rate_remaining = int(remaining)
        if reset is not None and reset.isdigit():
            self.rate_reset = int(reset)


def _rate_limited(response: HttpResponse) -> bool:
    remaining = response.headers.get("x-ratelimit-remaining", "")
    if remaining == "0":
        return True
    try:
        text = response.body.decode("utf-8", errors="replace").lower()
    except Exception:
        return False
    return "rate limit" in text or "secondary rate" in text
