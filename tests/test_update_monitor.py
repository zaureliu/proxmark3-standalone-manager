"""Monitor de atualizações. A rede, o hardware e o checkout de produção não entram aqui."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import threading
from pathlib import Path

import pytest

from pm3manager.cache.store import FirmwareCache
from pm3manager.models import Environment
from pm3manager.paths import project_root
from pm3manager.preferences import Preferences
from pm3manager.updates.changelog import commit_line, plain_text
from pm3manager.updates.compatibility import NOT_VERIFIED
from pm3manager.updates.github_client import GitHubClient, GitHubError, HttpResponse, validate_api_url
from pm3manager.updates.models import (
    UNKNOWN_VERSION,
    LocalInstall,
    Relation,
    RemoteView,
    ReleaseInfo,
)
from pm3manager.updates.providers import ICEMAN, PROXSPACE
from pm3manager.updates.repository_detector import (
    _GIT_COMMANDS,
    default_git,
    inspect_git_checkout,
    inspect_iceman,
    inspect_proxspace,
)
from pm3manager.updates.update_cache import UpdateCache
from pm3manager.updates.update_checker import check_provider, report_from_dict, report_to_dict
from pm3manager.updates.update_service import UpdateService
from pm3manager.updates.version_comparator import (
    classify,
    parse_version,
    same_commit,
    status_message,
    version_order,
)

LOCAL = "a" * 40
BRANCH = "b" * 40
RELEASE = "c" * 40
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
        stdin=subprocess.DEVNULL,
        creationflags=_NO_WINDOW,
    )


def init_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    created = _run(["git", "init", "-b", "master", str(path)])
    if created.returncode != 0:
        assert _run(["git", "init", str(path)]).returncode == 0
        assert _run(["git", "-C", str(path), "checkout", "-B", "master"]).returncode == 0
    for key, value in (
        ("user.email", "tester@example.com"),
        ("user.name", "Tester"),
        ("core.autocrlf", "false"),
        ("commit.gpgsign", "false"),
    ):
        assert _run(["git", "-C", str(path), "config", key, value]).returncode == 0
    (path / "README.txt").write_text("base\n", encoding="utf-8")
    assert _run(["git", "-C", str(path), "add", "README.txt"]).returncode == 0
    assert _run(["git", "-C", str(path), "commit", "-m", "base"]).returncode == 0
    head = _run(["git", "-C", str(path), "rev-parse", "HEAD"])
    assert head.returncode == 0
    return head.stdout.strip()


def local_at(commit: str = LOCAL, version: str = "v4.23346", **kwargs) -> LocalInstall:
    data = dict(
        present=True,
        kind="checkout",
        path="C:/tmp/iceman",
        version=version,
        version_label=version or UNKNOWN_VERSION,
        commit=commit,
        branch="master",
    )
    data.update(kwargs)
    return LocalInstall(**data)


def _api(url: str, payload, etag: str = "e1", status: int = 200):
    from pm3manager.updates.github_client import ApiResponse

    return ApiResponse(status, payload, etag, False)


class ScriptedClient:
    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls: list[str] = []
        self.rate_remaining = None
        self.rate_reset = 0

    def get_json(self, url: str, etag: str = "", *, missing_ok: bool = False, max_body: int | None = None):
        self.calls.append(url)
        result = self.handler(url, etag, missing_ok)
        if isinstance(result, Exception):
            raise result
        return result


def _release_body(tag: str, web: str, notes: str, html_url: str | None = None) -> dict:
    return {
        "tag_name": tag,
        "name": tag,
        "published_at": "2026-10-01T00:00:00Z",
        "body": notes,
        "html_url": html_url or f"{web}/releases/tag/{tag}",
    }


def _commit_body(sha: str, message: str = "assunto da ponta\n\ndetalhe") -> dict:
    return {
        "sha": sha,
        "commit": {"message": message, "committer": {"date": "2026-10-02T00:00:00Z"}},
    }


def _compare_body(status: str, sha: str) -> dict:
    ahead = 2 if status == "ahead" else 0
    behind = 1 if status == "behind" else 0
    commits = []
    if status == "ahead":
        commits.append({"sha": sha, "commit": {"message": "ajuste do cliente"}})
    return {
        "status": status,
        "ahead_by": ahead,
        "behind_by": behind,
        "commits": commits,
        "files": [{"filename": "armsrc/appmain.c", "patch": "nao guardar"}],
    }


def world(
    *,
    archived: bool = False,
    branch: str = "master",
    branch_sha: str = BRANCH,
    release_tag: str = "v4.23347",
    release_sha: str = RELEASE,
    branch_status: str = "ahead",
    release_status: str = "ahead",
    notes: str = "Correção do cliente\n\n<script>alert(1)</script>",
    html_url: str | None = None,
    missing_release: bool = False,
    repo_payload=None,
):
    """`ahead` na comparação local...remoto significa que o remoto está à frente."""

    def handler(url: str, etag: str, missing_ok: bool):
        proxspace = "/ProxSpace" in url or url.endswith("/ProxSpace")
        web = PROXSPACE.web if proxspace else ICEMAN.web
        if url.rstrip("/").endswith("/proxmark3") or url.rstrip("/").endswith("/ProxSpace"):
            payload = repo_payload if repo_payload is not None else {"default_branch": branch, "archived": archived}
            return _api(url, payload)
        if url.endswith("/releases/latest"):
            if missing_release:
                return _api(url, None, status=404)
            return _api(url, _release_body(release_tag, web, notes, html_url))
        if "/commits/" in url:
            name = url.rstrip("/").rsplit("/", 1)[-1]
            sha = release_sha if name == release_tag else branch_sha
            return _api(url, _commit_body(sha))
        if "/compare/" in url:
            right = url.rsplit("...", 1)[-1]
            status = release_status if right == release_sha else branch_status
            return _api(url, _compare_body(status, right))
        raise AssertionError(url)

    return handler


def _remote(
    *,
    status: str = "identical",
    release_status: str = "identical",
    tag: str = "v4.23346",
    branch_sha: str = LOCAL,
    archived: bool = False,
    branch: str = "master",
) -> RemoteView:
    return RemoteView(
        archived=archived,
        default_branch=branch,
        html_url=ICEMAN.web,
        release=ReleaseInfo(tag, tag, "2026-09-01T00:00:00Z", f"{ICEMAN.web}/releases/tag/{tag}", "notas", branch_sha),
        branch_sha=branch_sha,
        compare_status=status,
        release_compare=release_status,
    )


def test_versao_numerica_nao_e_texto_nem_data():
    older = parse_version("Iceman/master/v4.23346")
    newer = parse_version("v4.23347")
    assert version_order(older, newer) == -1
    assert version_order(parse_version("v4.9"), parse_version("4.9.0")) == 0
    assert parse_version("sem versao").known is False
    assert parse_version("v999999999999.1").known is False
    assert version_order(older, parse_version("ontem")) is None
    assert same_commit(LOCAL, LOCAL[:12]) is True
    assert same_commit(LOCAL, BRANCH) is False


def test_classificacao_separa_release_commit_divergencia_e_adiantamento():
    current, token = classify(local_at(LOCAL, "v4.23346"), _remote())
    assert current is Relation.CURRENT and token == ""

    release, token = classify(
        local_at(LOCAL, "v4.23346"),
        _remote(status="ahead", release_status="ahead", tag="v4.23347", branch_sha=BRANCH),
    )
    assert release is Relation.NEW_RELEASE and token == "release:v4.23347"

    commits, token = classify(
        local_at(LOCAL, "v4.23347"),
        _remote(status="ahead", release_status="identical", tag="v4.23347", branch_sha=BRANCH),
    )
    assert commits is Relation.NEW_COMMITS and token == f"commit:{BRANCH}"

    ahead, token = classify(local_at(LOCAL, "v4.23350"), _remote(status="behind", release_status="behind"))
    assert ahead is Relation.LOCAL_AHEAD and token == ""

    diverged, token = classify(
        local_at(LOCAL, "v4.23346"),
        _remote(status="diverged", release_status="ahead", tag="v4.24000", branch_sha=BRANCH),
    )
    assert diverged is Relation.DIVERGED and token == ""

    unknown, token = classify(local_at("", "v4.23346"), _remote(status="ahead", release_status="ahead", tag="v9"))
    assert unknown is Relation.LOCAL_UNKNOWN and token == ""

    missing, _token = classify(local_at(LOCAL), None)
    assert missing is Relation.UNAVAILABLE

    same_tip, token = classify(
        local_at(LOCAL, "v4.23340"),
        _remote(status="identical", release_status="diverged", tag="v4.23347", branch_sha=LOCAL),
    )
    assert same_tip is Relation.CURRENT and token == ""

    later_but_older, token = classify(
        local_at(LOCAL, "v4.23350"),
        _remote(status="identical", release_status="behind", tag="v4.1", branch_sha=LOCAL),
    )
    assert later_but_older is Relation.CURRENT and token == ""


def test_mensagem_de_divergencia_nao_anuncia_versao_nova():
    assert status_message("iceman", Relation.DIVERGED, archived=False, cached=False).startswith("O histórico local divergiu")
    from pm3manager.updates.version_comparator import announce_text

    assert announce_text("iceman", Relation.DIVERGED) == ""
    assert announce_text("iceman", Relation.NEW_RELEASE) == "Nova versão do Iceman disponível."
    cached = status_message("proxspace", Relation.CURRENT, archived=True, cached=True)
    assert cached.startswith("Exibindo resultado da última verificação.")
    assert "ProxSpace atualizado." in cached
    assert "Repositório ProxSpace arquivado." in cached


def test_deteccao_de_head_branch_tag_detached_e_arvore_suja(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    repo = tmp_path / "checkout"
    head = init_repo(repo)
    assert _run(["git", "-C", str(repo), "tag", "v4.23346"]).returncode == 0
    clean = inspect_git_checkout(repo)
    assert clean.commit == head
    assert clean.branch == "master"
    assert clean.tag == "v4.23346"
    assert clean.detached is False
    assert clean.dirty is False
    assert clean.unpushed is None

    (repo / "README.txt").write_text("alterado\n", encoding="utf-8")
    assert inspect_git_checkout(repo).dirty is True
    assert _run(["git", "-C", str(repo), "checkout", "--", "README.txt"]).returncode == 0
    (repo / "novo.txt").write_text("local\n", encoding="utf-8")
    assert inspect_git_checkout(repo).dirty is True
    (repo / "novo.txt").unlink()
    assert inspect_git_checkout(repo).dirty is False

    assert _run(["git", "-C", str(repo), "checkout", "--detach"]).returncode == 0
    detached = inspect_git_checkout(repo)
    assert detached.detached is True
    assert detached.branch == ""
    assert detached.commit == head
    assert any("HEAD desanexado" in note for note in detached.notes)

    assert _run(["git", "-C", str(repo), "checkout", "master"]).returncode == 0
    assert _run(["git", "-C", str(repo), "checkout", "-b", "local"]).returncode == 0
    (repo / "README.txt").write_text("somente local\n", encoding="utf-8")
    assert _run(["git", "-C", str(repo), "add", "README.txt"]).returncode == 0
    assert _run(["git", "-C", str(repo), "commit", "-m", "local only"]).returncode == 0
    assert _run(["git", "-C", str(repo), "branch", "published", "HEAD~1"]).returncode == 0
    assert _run(["git", "-C", str(repo), "config", "branch.local.remote", "."]).returncode == 0
    assert _run(["git", "-C", str(repo), "config", "branch.local.merge", "refs/heads/published"]).returncode == 0
    ahead = inspect_git_checkout(repo)
    assert ahead.branch == "local"
    assert ahead.unpushed == 1
    assert any("Commits locais" in note for note in ahead.notes)

    makefile = repo / "Makefile.platform"
    makefile.write_text(
        "PLATFORM=PM3GENERIC\nPLATFORM_EXTRAS=FLASH\nSTANDALONE=HF_MATTYRUN\n",
        encoding="utf-8",
    )
    before = makefile.read_bytes()
    env = Environment(
        proxspace_root=tmp_path / "ProxSpace",
        repo_root=repo,
        repo_msys="/pm3/checkout",
        msys_shell=tmp_path / "msys2_shell.cmd",
        version="Iceman/master/v4.23346",
        commit="9ce8a4b6c",
        build_time="",
        external_makefile=None,
        external_makefile_text="",
        source_fingerprint="",
    )
    selected = inspect_iceman(env)
    assert selected.commit == ahead.commit
    assert selected.firmware_commit == "9ce8a4b6c"
    assert selected.commit != selected.firmware_commit
    assert any("Não é o Git HEAD" in note and "9ce8a4b6c" in note for note in selected.notes)
    assert selected.platform == "PM3GENERIC"
    assert selected.standalone == "HF_MATTYRUN"
    assert selected.extras == "FLASH"
    assert selected.version_label == "Iceman/master/v4.23346"
    assert makefile.read_bytes() == before
    assert "Makefile.platform" in _run(["git", "-C", str(repo), "status", "--porcelain"]).stdout


def test_pasta_dentro_de_outro_repositorio_nao_herda_o_pai(tmp_path):
    nested = tmp_path / "aninhado"
    nested.mkdir()
    found = inspect_git_checkout(nested)
    assert found.commit == ""
    assert found.kind == "desconhecido"
    assert found.present is True


def test_git_recusa_comandos_de_atualizacao_e_nao_usa_shell(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["fetch"],
        ["pull"],
        ["reset", "--hard"],
        ["checkout", "main"],
        ["status", "-c", "core.pager=more"],
        ["status", "--"],
    ):
        with pytest.raises(ValueError):
            default_git(repo, args)
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["shell"] = kwargs.get("shell")
        return subprocess.CompletedProcess(command, 0, stdout="true\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    code, output = default_git(repo, ["rev-parse", "--is-inside-work-tree"])
    assert code == 0 and output == "true\n"
    assert seen["shell"] is False
    assert seen["command"][:3] == ["git", "-C", str(repo)]
    assert "fetch" not in _GIT_COMMANDS
    assert "pull" not in _GIT_COMMANDS


def test_proxspace_por_manifesto_pacote_checkout_e_versao_desconhecida(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    absent = inspect_proxspace(None)
    assert absent.present is False
    assert absent.version_label == UNKNOWN_VERSION

    missing = tmp_path / "nao-existe"
    assert inspect_proxspace(missing).version_label == UNKNOWN_VERSION

    package = tmp_path / "ProxSpace"
    package.mkdir()
    (package / "runme64.bat").write_text("@echo off\n", encoding="utf-8")
    version = package / "VERSION"
    version.write_text("v3.11\nsegunda linha\n", encoding="utf-8")
    old = 1_500_000_000
    os.utime(version, (old, old))
    found = inspect_proxspace(package)
    assert found.kind == "pacote"
    assert found.version == "v3.11"
    assert found.version_label == "v3.11"
    assert "://" not in found.version

    (package / "VERSION").write_text("https://example.invalid/v9\n", encoding="utf-8")
    rejected = inspect_proxspace(package)
    assert rejected.version == ""
    assert rejected.version_label == UNKNOWN_VERSION

    unknown = tmp_path / "solto"
    unknown.mkdir()
    loose = inspect_proxspace(unknown)
    assert loose.kind == "desconhecido"
    assert loose.version_label == UNKNOWN_VERSION

    checkout = tmp_path / "clone"
    init_repo(checkout)
    (checkout / "runme64.bat").write_text("@echo off\n", encoding="utf-8")
    cloned = inspect_proxspace(checkout)
    assert cloned.kind == "checkout"
    assert cloned.commit
    assert cloned.version_label == UNKNOWN_VERSION


def test_release_nova_commit_novo_local_a_frente_e_divergente(tmp_path):
    cache = UpdateCache(tmp_path / "updates")
    client = ScriptedClient(world())
    report = check_provider(ICEMAN, local_at(), client, cache, threading.Event())
    assert report.relation is Relation.NEW_RELEASE
    assert report.notification_id == "release:v4.23347"
    assert report.announce is True
    assert report.announce_text == "Nova versão do Iceman disponível."
    assert report.message == "Nova release disponível."
    assert report.fresh is True and report.cached is False
    assert report.compatibility == NOT_VERIFIED
    assert report.remote is not None
    assert report.remote.default_branch == "master"
    assert report.remote.release is not None
    assert "<script>" not in report.remote.release.notes
    assert "Correção do cliente" in report.remote.release.notes
    assert report.remote.commit_lines
    assert report.remote.release.html_url.startswith(ICEMAN.web + "/")
    compared = [body for key, body in cache._provider("iceman").get("bodies", {}).items() if str(key).startswith("compare-")]
    assert compared
    assert all(isinstance(body, dict) and "files" not in body for body in compared)

    commits = check_provider(
        ICEMAN,
        local_at(version="v4.23347"),
        ScriptedClient(world(release_tag="v4.23347", release_sha=LOCAL, release_status="identical")),
        UpdateCache(tmp_path / "commits"),
        threading.Event(),
    )
    assert commits.relation is Relation.NEW_COMMITS
    assert commits.notification_id == f"commit:{BRANCH}"
    assert commits.message == "Novos commits disponíveis."

    ahead = check_provider(
        ICEMAN,
        local_at(version="v4.23350"),
        ScriptedClient(world(branch_status="behind", release_status="behind", release_tag="v4.23340")),
        UpdateCache(tmp_path / "ahead"),
        threading.Event(),
    )
    assert ahead.relation is Relation.LOCAL_AHEAD
    assert ahead.announce is False
    assert ahead.notification_id == ""

    diverged = check_provider(
        ICEMAN,
        local_at(),
        ScriptedClient(world(branch_status="diverged", release_status="ahead", release_tag="v4.24000")),
        UpdateCache(tmp_path / "diverged"),
        threading.Event(),
    )
    assert diverged.relation is Relation.DIVERGED
    assert diverged.announce is False
    assert diverged.announce_text == ""
    assert "nova versão" not in diverged.message.lower()


def test_branch_padrao_vem_da_api_e_release_de_outro_site_e_reescrita(tmp_path):
    client = ScriptedClient(world(branch="main", html_url="https://evil.example/release"))
    report = check_provider(
        ICEMAN,
        local_at(),
        client,
        UpdateCache(tmp_path / "updates"),
        threading.Event(),
    )
    report_calls = client.calls
    assert report.remote is not None
    assert report.remote.default_branch == "main"
    assert report.remote.release is not None
    assert report.remote.release.html_url == f"{ICEMAN.web}/releases/tag/v4.23347"
    assert all("evil.example" not in call for call in report_calls)


def test_proxspace_arquivado_nao_significa_instalacao_inutilizavel(tmp_path):
    same = "d" * 40
    report = check_provider(
        PROXSPACE,
        local_at(same, "v3.11"),
        ScriptedClient(
            world(
                archived=True,
                branch_sha=same,
                release_sha=same,
                release_tag="v3.11",
                notes="Pacote antigo",
            )
        ),
        UpdateCache(tmp_path / "updates"),
        threading.Event(),
    )
    assert report.relation is Relation.CURRENT
    assert report.archived is True
    assert report.message == "ProxSpace atualizado. Repositório ProxSpace arquivado."
    assert report.announce is False
    assert "inutiliz" not in report.message.lower()


def test_commit_ausente_e_versao_ausente_tem_textos_diferentes(tmp_path):
    with_version = check_provider(
        ICEMAN,
        local_at("", "v4.23346"),
        ScriptedClient(world()),
        UpdateCache(tmp_path / "one"),
        threading.Event(),
    )
    assert with_version.relation is Relation.LOCAL_UNKNOWN
    assert with_version.message == "Commit local não identificado."

    without = check_provider(
        PROXSPACE,
        LocalInstall(present=True, kind="pacote", version_label=UNKNOWN_VERSION),
        ScriptedClient(world(archived=True, branch_sha=BRANCH, release_sha=RELEASE)),
        UpdateCache(tmp_path / "two"),
        threading.Event(),
    )
    assert without.relation is Relation.LOCAL_UNKNOWN
    assert without.message == "Versão local não identificada. Repositório ProxSpace arquivado."


def test_falha_de_rede_timeout_json_e_cache_da_ultima_consulta(tmp_path):
    cache = UpdateCache(tmp_path / "updates")
    first = check_provider(ICEMAN, local_at(), ScriptedClient(world()), cache, threading.Event())
    assert first.fresh is True

    def explode(url, etag, missing_ok):
        raise GitHubError("connection", "Não foi possível consultar o GitHub.")

    offline = check_provider(ICEMAN, local_at(), ScriptedClient(explode), cache, threading.Event())
    assert offline.cached is True and offline.fresh is False
    assert offline.announce is False
    assert offline.message.startswith("Exibindo resultado da última verificação.")
    assert offline.relation is Relation.NEW_RELEASE
    assert offline.remote is not None and offline.remote.release is not None

    def timeout(url, headers):
        import socket

        raise socket.timeout("lento")

    client = GitHubClient(transport=timeout)
    with pytest.raises(GitHubError) as caught:
        client.get_json(ICEMAN.api)
    assert caught.value.kind == "timeout"

    def invalid(url, headers):
        return HttpResponse(200, {"x-ratelimit-remaining": "10"}, b"{")

    with pytest.raises(GitHubError) as bad:
        GitHubClient(transport=invalid).get_json(ICEMAN.api)
    assert bad.value.kind == "json"

    broken = check_provider(
        ICEMAN,
        local_at(),
        ScriptedClient(world(repo_payload=["nao", "objeto"])),
        UpdateCache(tmp_path / "badjson"),
        threading.Event(),
    )
    assert broken.relation is Relation.UNAVAILABLE
    assert broken.message == "Não foi possível consultar o GitHub."


def test_rate_limit_nao_e_contornado_e_304_reaproveita_o_corpo(tmp_path):
    calls = {"n": 0}

    def limited(url, headers):
        calls["n"] += 1
        assert "Authorization" not in headers
        assert headers["User-Agent"].startswith("Proxmark3StandaloneManager/")
        assert "token" not in headers["User-Agent"].lower()
        return HttpResponse(
            403,
            {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "5000"},
            b'{"message":"api rate limit exceeded"}',
        )

    client = GitHubClient(transport=limited, now=lambda: 10)
    with pytest.raises(GitHubError) as first:
        client.get_json(ICEMAN.api)
    assert first.value.kind == "rate" and first.value.status == 403
    with pytest.raises(GitHubError):
        client.get_json(ICEMAN.api)
    assert calls["n"] == 1

    def too_many(url, headers):
        return HttpResponse(429, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "20"}, b"")

    with pytest.raises(GitHubError) as second:
        GitHubClient(transport=too_many, now=lambda: 0).get_json(PROXSPACE.api)
    assert second.value.kind == "rate"

    cache = UpdateCache(tmp_path / "updates")
    sha = "d" * 40
    cache.put_body("iceman", "repo", "abc", {"default_branch": "master", "archived": False})
    cache.put_body("iceman", "release", "abc", _release_body("v4.23346", ICEMAN.web, "notas estáveis"))
    cache.put_body("iceman", "release-commit-v4.23346", "abc", _commit_body(sha, "tag"))
    cache.put_body("iceman", "branch-master", "abc", _commit_body(sha, "tag"))
    seen = []

    def not_modified(url, headers):
        seen.append(headers.get("If-None-Match", ""))
        return HttpResponse(304, {"etag": "abc", "x-ratelimit-remaining": "40"}, b"")

    report = check_provider(
        ICEMAN,
        local_at(sha, "v4.23346"),
        GitHubClient(transport=not_modified),
        cache,
        threading.Event(),
    )
    assert seen and set(seen) == {"abc"}
    assert report.fresh is True and report.cached is False
    assert report.remote is not None and report.remote.not_modified is True
    assert report.relation is Relation.CURRENT
    assert report.message == "Iceman atualizado."
    assert "Exibindo resultado" not in report.message
    assert "notas estáveis" in report.remote.release.notes


def test_cache_persiste_substitui_resultado_antigo_e_nao_e_o_cache_de_firmware(tmp_path):
    firmware = tmp_path / "cache"
    marker = firmware / "fullimage.elf"
    FirmwareCache(firmware)
    marker.write_bytes(b"\x7fELF-teste")
    digest = marker.read_bytes()
    cache = UpdateCache(tmp_path / "updates")
    check_provider(ICEMAN, local_at(), ScriptedClient(world(release_tag="v4.23346", release_sha=LOCAL, branch_sha=LOCAL, branch_status="identical", release_status="identical")), cache, threading.Event())
    assert cache.stored_report("iceman")["relation"] == Relation.CURRENT.value
    reloaded = UpdateCache(tmp_path / "updates")
    assert reloaded.etag("iceman", "repo") == "e1"
    assert reloaded.body("iceman", "repo")["default_branch"] == "master"

    updated = check_provider(ICEMAN, local_at(), ScriptedClient(world()), reloaded, threading.Event())
    assert updated.relation is Relation.NEW_RELEASE
    assert updated.message == "Nova release disponível."
    assert "Exibindo resultado" not in updated.message
    assert UpdateCache(tmp_path / "updates").stored_report("iceman")["relation"] == Relation.NEW_RELEASE.value
    assert marker.read_bytes() == digest
    assert not (firmware / "monitor.json").exists()
    assert (tmp_path / "updates" / "monitor.json").is_file()
    raw = (tmp_path / "updates" / "monitor.json").read_text(encoding="utf-8")
    assert "Authorization" not in raw
    assert "ghp_" not in raw

    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "monitor.json").write_text("{", encoding="utf-8")
    assert UpdateCache(broken).stored_report("iceman") is None


def test_consulta_simultanea_cancelamento_e_notificacao_sem_repetir(tmp_path):
    started = threading.Event()
    release = threading.Event()
    calls = []

    def blocking(url, etag, missing_ok):
        calls.append(url)
        started.set()
        assert release.wait(5)
        return world()(url, etag, missing_ok)

    service = UpdateService(ScriptedClient(blocking), UpdateCache(tmp_path / "updates"))
    holder = {}
    finished = threading.Event()

    def run() -> None:
        try:
            holder["first"] = service.check(local_at(), local_at(version="v3"))
        finally:
            finished.set()

    worker = threading.Thread(target=run)
    worker.start()
    assert started.wait(2)
    second = service.check(local_at(), local_at(version="v3"))
    assert second.busy is True
    assert len(calls) == 1
    release.set()
    # join() com tempo no Python 3.11 do Windows pode falhar com violação de
    # acesso quando a thread termina no mesmo instante. O evento cobre o fim.
    assert finished.wait(5)
    assert holder["first"].busy is False
    assert service.running is False

    cache = UpdateCache(tmp_path / "notice")
    client = ScriptedClient(world())
    first = check_provider(ICEMAN, local_at(), client, cache, threading.Event())
    assert first.announce is True
    cache.mark_notified([first.notification_id])
    again = check_provider(ICEMAN, local_at(), ScriptedClient(world()), cache, threading.Event())
    assert again.relation is Relation.NEW_RELEASE
    assert again.announce is False
    assert again.message == "Nova release disponível."
    cache.dismiss([again.notification_id])
    third = check_provider(ICEMAN, local_at(), ScriptedClient(world()), cache, threading.Event())
    assert third.announce is False

    cancel = threading.Event()
    cancel.set()
    cancelled_client = ScriptedClient(world())
    cancelled = check_provider(ICEMAN, local_at(), cancelled_client, UpdateCache(tmp_path / "cancel"), cancel)
    assert cancelled.fresh is False
    assert cancelled.error == "Consulta cancelada."
    assert cancelled_client.calls == []


def test_changelog_e_texto_puro_e_urls_oficiais_sao_as_unicas_aceitas():
    notes = plain_text("## Título\n<img src=x onerror=alert(1)>\nlinha\x00\n<script>alert(1)</script>")
    assert "<" not in notes
    assert "Título" in notes and "linha" in notes
    assert commit_line(LOCAL, "primeiro\nsegundo") == f"{LOCAL[:12]} primeiro"
    assert commit_line("não-é-sha", "assunto") == "assunto"
    for url in (
        "http://api.github.com/repos/RfidResearchGroup/proxmark3",
        "https://example.com/repos/RfidResearchGroup/proxmark3",
        "https://api.github.com/repos/evil/proxmark3",
        ICEMAN.api + "/../../repos/evil/other",
        ICEMAN.api + "?access_token=segredo",
        "https://user:secret@api.github.com/repos/RfidResearchGroup/proxmark3",
        "https://api.github.com:444/repos/RfidResearchGroup/proxmark3",
    ):
        with pytest.raises(GitHubError):
            validate_api_url(url)
    assert validate_api_url(ICEMAN.api + "/releases/latest") == ICEMAN.api + "/releases/latest"
    assert validate_api_url(PROXSPACE.api) == PROXSPACE.api


def test_redirecionamento_timeout_e_corpo_excessivo(monkeypatch):
    responses = []

    class FakeResponse:
        def __init__(self, status, headers, body) -> None:
            self.status = status
            self._headers = headers
            self._body = body

        def getheaders(self):
            return list(self._headers.items())

        def read(self, amount=-1):
            if amount is None or amount < 0:
                data, self._body = self._body, b""
                return data
            data, self._body = self._body[:amount], self._body[amount:]
            return data

    class FakeConnection:
        def __init__(self, host, timeout=None, context=None) -> None:
            self.host = host
            self.sock = None

        def request(self, method, path, headers=None) -> None:
            return None

        def getresponse(self):
            return responses.pop(0)

        def close(self) -> None:
            return None

    monkeypatch.setattr("pm3manager.updates.github_client.HTTPSConnection", FakeConnection)
    from pm3manager.updates.github_client import UrllibTransport

    responses.append(FakeResponse(302, {"Location": "https://github.com/RfidResearchGroup/proxmark3"}, b""))
    with pytest.raises(GitHubError) as redirected:
        UrllibTransport()(ICEMAN.api, {})
    assert redirected.value.kind == "redirect"

    responses.append(FakeResponse(302, {"Location": ICEMAN.api + "/releases/latest"}, b""))
    responses.append(FakeResponse(200, {"ETag": "z"}, b'{"ok": true}'))
    followed = UrllibTransport()(ICEMAN.api, {})
    assert followed.status == 200

    class TimeoutConnection(FakeConnection):
        def request(self, method, path, headers=None) -> None:
            raise TimeoutError("conectou e parou")

    monkeypatch.setattr("pm3manager.updates.github_client.HTTPSConnection", TimeoutConnection)
    with pytest.raises(GitHubError) as timed:
        UrllibTransport()(ICEMAN.api, {})
    assert timed.value.kind == "timeout"

    class DnsConnection(FakeConnection):
        def request(self, method, path, headers=None) -> None:
            import socket

            raise socket.gaierror("dns")

    monkeypatch.setattr("pm3manager.updates.github_client.HTTPSConnection", DnsConnection)
    with pytest.raises(GitHubError) as dns:
        UrllibTransport()(PROXSPACE.api, {})
    assert dns.value.kind == "connection"

    monkeypatch.setattr("pm3manager.updates.github_client.HTTPSConnection", FakeConnection)
    responses.append(FakeResponse(200, {}, b"x" * 1_000_001))
    with pytest.raises(GitHubError) as huge:
        UrllibTransport()(ICEMAN.api, {})
    assert huge.value.kind == "http"


def test_preferencias_de_intervalo_e_inicializacao_sem_rede_nem_proxspace(isolated_data):
    path = isolated_data / "preferences.json"
    path.write_text(
        json.dumps(
            {
                "updates_enabled": "nao",
                "updates_notify": "sim",
                "updates_interval_minutes": 3,
                "nota_local": "preservar",
            }
        ),
        encoding="utf-8",
    )
    loaded = Preferences.load()
    assert loaded.updates_enabled is False
    assert loaded.updates_notify is True
    assert loaded.updates_interval_minutes == 15
    loaded.updates_interval_minutes = 90
    loaded.updates_notify = False
    loaded.save()
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["updates_interval_minutes"] == 90
    assert stored["updates_notify"] is False
    assert stored["nota_local"] == "preservar"
    assert stored["flash_autorizado"] is False
    assert Preferences.load().updates_interval_minutes == 90

    path.write_text("{}", encoding="utf-8")
    defaults = Preferences.load()
    assert defaults.updates_enabled is True
    assert defaults.updates_notify is True
    assert defaults.updates_interval_minutes == 60

    cache = UpdateCache(isolated_data / "updates")
    check_provider(ICEMAN, local_at(LOCAL, "v4.23346"), ScriptedClient(world()), cache, threading.Event())
    service = UpdateService(ScriptedClient(world()), cache)
    preview = LocalInstall(present=True, version="v4.23346", version_label="v4.23346", commit="")
    shown = service.cached_view(preview, LocalInstall(), keep_stored_local=True)
    assert shown.iceman.cached is True
    assert shown.iceman.local.commit == LOCAL
    assert shown.iceman.message.startswith("Exibindo resultado da última verificação.")
    assert shown.proxspace.relation is Relation.LOCAL_UNKNOWN

    def down(url, etag, missing_ok):
        raise GitHubError("connection", "Não foi possível consultar o GitHub.")

    offline = check_provider(PROXSPACE, LocalInstall(), ScriptedClient(down), UpdateCache(isolated_data / "empty"), threading.Event())
    assert offline.relation is Relation.UNAVAILABLE
    assert offline.message == "Não foi possível consultar o GitHub."
    assert offline.local.version_label == UNKNOWN_VERSION


def test_monitor_nao_importa_serial_nem_grava_firmware(tmp_path):
    roots = [project_root() / "pm3manager" / "updates", project_root() / "pm3manager" / "ui" / "updates_panel.py"]
    files = []
    for root in roots:
        files.extend(root.rglob("*.py") if root.is_dir() else [root])
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all("serial" not in alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                assert node.module is None or "serial" not in node.module
        text = path.read_text(encoding="utf-8").lower()
        assert "pm3-flash" not in text
        assert "shell=true" not in text
        assert "subprocess" not in text or path.name == "repository_detector.py"
    firmware = tmp_path / "cache" / "image.elf"
    firmware.parent.mkdir(parents=True)
    firmware.write_bytes(b"imagem")
    check_provider(ICEMAN, local_at(), ScriptedClient(world()), UpdateCache(tmp_path / "updates"), threading.Event())
    assert firmware.read_bytes() == b"imagem"


def test_roundtrip_do_relatorio_e_checkout_real_permanece_intacto():
    remote = _remote(status="ahead", release_status="ahead", tag="v4.23347", branch_sha=BRANCH, archived=True)
    from pm3manager.updates.models import ProviderReport

    report = ProviderReport(
        key="proxspace",
        title="ProxSpace",
        web_url=PROXSPACE.web,
        local=local_at(LOCAL, "v3"),
        remote=remote,
        relation=Relation.NEW_RELEASE,
        message="Nova release disponível.",
        compatibility=NOT_VERIFIED,
        fresh=True,
        cached=False,
        checked_at="2026-10-23T00:00:00+00:00",
        notification_id="release:v4.23347",
    )
    restored = report_from_dict(report_to_dict(report))
    assert restored.remote is not None
    assert restored.remote.archived is True
    assert restored.remote.release is not None and restored.remote.release.tag == "v4.23347"
    assert restored.local.commit == LOCAL
    assert restored.fresh is False and restored.cached is True

    repo = project_root().parent / "ProxSpace" / "pm3" / "proxmark3-v4.23346"
    makefile = repo / "Makefile.platform"
    if not makefile.is_file():
        pytest.skip("checkout de produção ausente")
    before = makefile.read_bytes()
    status_before = _run(["git", "-C", str(repo), "status", "--porcelain"]).stdout
    from pm3manager.proxspace.locator import locate

    inspect_iceman(locate(repo.parent.parent, repo_dirname=repo.name))
    assert makefile.read_bytes() == before
    assert _run(["git", "-C", str(repo), "status", "--porcelain"]).stdout == status_before
