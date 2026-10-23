"""Consulta um repositório oficial e monta o relatório. Não grava firmware."""

from __future__ import annotations

import re
import threading
from datetime import datetime, timezone

from pm3manager.updates.changelog import commit_line, plain_text
from pm3manager.updates.compatibility import NOT_VERIFIED, compatibility_note
from pm3manager.updates.github_client import GitHubClient, GitHubError, _COMPARE_MAX_BODY
from pm3manager.updates.models import (
    LocalInstall,
    ProviderReport,
    Relation,
    ReleaseInfo,
    RemoteView,
)
from pm3manager.updates.providers import Provider
from pm3manager.updates.update_cache import UpdateCache
from pm3manager.updates.version_comparator import announce_text, classify, status_message

_SHA = re.compile(r"^[0-9a-fA-F]{7,40}$")
_REF = re.compile(r"[A-Za-z0-9._/-]{1,120}")


class Cancelled(Exception):
    pass


def check_provider(
    provider: Provider,
    local: LocalInstall,
    client: GitHubClient,
    cache: UpdateCache,
    cancel: threading.Event,
) -> ProviderReport:
    try:
        remote, not_modified = _read_remote(provider, local, client, cache, cancel)
    except Cancelled:
        return _from_cache_or_unavailable(provider, local, cache, "Consulta cancelada.")
    except GitHubError as exc:
        _diag(f"{provider.key} {exc.kind}")
        return _from_cache_or_unavailable(provider, local, cache, exc.message)
    relation, notification_id = classify(local, remote)
    checked_at = _stamp()
    message = status_message(provider.key, relation, archived=remote.archived, cached=False)
    if relation == Relation.LOCAL_UNKNOWN and local.version:
        message = "Commit local não identificado."
        if remote.archived and provider.key == "proxspace":
            message += " Repositório ProxSpace arquivado."
    report = ProviderReport(
        key=provider.key,
        title=provider.title,
        web_url=provider.web,
        local=local,
        remote=remote,
        relation=relation,
        message=message,
        compatibility=compatibility_note(True),
        fresh=True,
        cached=False,
        checked_at=checked_at,
        notification_id=notification_id,
    )
    if remote is not None:
        remote_copy = remote
        remote_copy = RemoteView(
            archived=remote.archived,
            default_branch=remote.default_branch,
            html_url=remote.html_url,
            release=remote.release,
            branch_sha=remote.branch_sha,
            branch_date=remote.branch_date,
            branch_summary=remote.branch_summary,
            compare_status=remote.compare_status,
            release_compare=remote.release_compare,
            ahead_by=remote.ahead_by,
            behind_by=remote.behind_by,
            commit_lines=remote.commit_lines,
            not_modified=not_modified,
        )
        report.remote = remote_copy
    report.announce = _should_announce(cache, notification_id)
    report.announce_text = announce_text(provider.key, relation) if report.announce else ""
    cache.store_report(provider.key, report_to_dict(report))
    _diag(f"{provider.key} {relation.value}")
    return report


def cached_provider(
    provider: Provider,
    local: LocalInstall,
    cache: UpdateCache,
    *,
    keep_stored_local: bool = False,
) -> ProviderReport:
    return _from_cache_or_unavailable(
        provider,
        local,
        cache,
        "",
        keep_stored_local=keep_stored_local,
    )


def report_to_dict(report: ProviderReport) -> dict:
    local = report.local
    remote = report.remote
    release = None
    if remote and remote.release:
        item = remote.release
        release = {
            "tag": item.tag,
            "name": item.name,
            "published_at": item.published_at,
            "html_url": item.html_url,
            "notes": item.notes,
            "sha": item.sha,
        }
    return {
        "key": report.key,
        "title": report.title,
        "web_url": report.web_url,
        "relation": report.relation.value,
        "message": report.message,
        "compatibility": report.compatibility,
        "checked_at": report.checked_at,
        "error": report.error,
        "notification_id": report.notification_id,
        "local": {
            "present": local.present,
            "kind": local.kind,
            "path": local.path,
            "version": local.version,
            "version_label": local.version_label,
            "commit": local.commit,
            "branch": local.branch,
            "tag": local.tag,
            "detached": local.detached,
            "dirty": local.dirty,
            "unpushed": local.unpushed,
            "remote_url": local.remote_url,
            "platform": local.platform,
            "standalone": local.standalone,
            "extras": local.extras,
            "firmware_commit": local.firmware_commit,
            "notes": list(local.notes),
        },
        "remote": None
        if remote is None
        else {
            "archived": remote.archived,
            "default_branch": remote.default_branch,
            "html_url": remote.html_url,
            "release": release,
            "branch_sha": remote.branch_sha,
            "branch_date": remote.branch_date,
            "branch_summary": remote.branch_summary,
            "compare_status": remote.compare_status,
            "release_compare": remote.release_compare,
            "ahead_by": remote.ahead_by,
            "behind_by": remote.behind_by,
            "commit_lines": list(remote.commit_lines),
            "not_modified": remote.not_modified,
        },
    }


def report_from_dict(payload: dict, local: LocalInstall | None = None) -> ProviderReport:
    remote_raw = payload.get("remote")
    remote = _remote_from_dict(remote_raw) if isinstance(remote_raw, dict) else None
    stored_local = payload.get("local") if isinstance(payload.get("local"), dict) else {}
    chosen = local if local is not None else _local_from_dict(stored_local)
    try:
        relation = Relation(str(payload.get("relation") or Relation.UNAVAILABLE.value))
    except ValueError:
        relation = Relation.UNAVAILABLE
    return ProviderReport(
        key=str(payload.get("key") or ""),
        title=str(payload.get("title") or ""),
        web_url=str(payload.get("web_url") or ""),
        local=chosen,
        remote=remote,
        relation=relation,
        message=str(payload.get("message") or ""),
        compatibility=str(payload.get("compatibility") or ""),
        fresh=False,
        cached=True,
        checked_at=str(payload.get("checked_at") or ""),
        error=str(payload.get("error") or ""),
        notification_id=str(payload.get("notification_id") or ""),
        announce=False,
        announce_text="",
    )


def _read_remote(provider, local, client, cache, cancel) -> tuple[RemoteView, bool]:
    _checkpoint(cancel)
    repo, repo_cached = _get(client, cache, provider.key, "repo", provider.api, cancel)
    if not isinstance(repo, dict):
        raise GitHubError("json", "Resposta JSON inválida.")
    branch_name = _ref(str(repo.get("default_branch") or ""))
    archived = repo.get("archived") is True
    _checkpoint(cancel)
    release_payload, release_cached = _get(
        client,
        cache,
        provider.key,
        "release",
        f"{provider.api}/releases/latest",
        cancel,
        missing_ok=True,
    )
    release = _release(provider, release_payload) if isinstance(release_payload, dict) else None
    release_sha = ""
    release_cached_commit = False
    if release is not None:
        _checkpoint(cancel)
        release_commit, release_cached_commit = _get(
            client,
            cache,
            provider.key,
            f"release-commit-{release.tag}",
            f"{provider.api}/commits/{_ref(release.tag)}",
            cancel,
            missing_ok=True,
        )
        if isinstance(release_commit, dict) and _SHA.fullmatch(str(release_commit.get("sha") or "")):
            release_sha = str(release_commit["sha"])
            release = ReleaseInfo(
                tag=release.tag,
                name=release.name,
                published_at=release.published_at,
                html_url=release.html_url,
                notes=release.notes,
                sha=release_sha,
            )
    _checkpoint(cancel)
    branch_payload, branch_cached = _get(
        client,
        cache,
        provider.key,
        f"branch-{branch_name}",
        f"{provider.api}/commits/{branch_name}",
        cancel,
    )
    if not isinstance(branch_payload, dict):
        raise GitHubError("json", "Resposta JSON inválida.")
    branch_sha = str(branch_payload.get("sha") or "")
    if not _SHA.fullmatch(branch_sha):
        raise GitHubError("json", "Commit remoto inválido.")
    commit = branch_payload.get("commit") if isinstance(branch_payload.get("commit"), dict) else {}
    message = str(commit.get("message") or "")
    committer = commit.get("committer") if isinstance(commit.get("committer"), dict) else {}
    branch_date = str(committer.get("date") or "")
    branch_compare = "identical" if _same(local.commit, branch_sha) else ""
    release_compare = "identical" if release_sha and _same(local.commit, release_sha) else ""
    ahead = behind = 0
    lines: tuple[str, ...] = ()
    branch_compare_cached = True
    release_compare_cached = True
    if local.commit and _SHA.fullmatch(local.commit) and not _same(local.commit, branch_sha):
        _checkpoint(cancel)
        _compared, branch_compare_cached, ahead, behind, lines, branch_compare = _compare(
            provider, local.commit, branch_sha, client, cache, cancel, "branch"
        )
    if release_sha and branch_sha and _same(release_sha, branch_sha):
        release_compare = branch_compare or release_compare
        release_compare_cached = branch_compare_cached
    elif local.commit and release_sha and _SHA.fullmatch(local.commit) and not _same(local.commit, release_sha):
        _checkpoint(cancel)
        _payload, release_compare_cached, _ahead, _behind, release_lines, release_compare = _compare(
            provider, local.commit, release_sha, client, cache, cancel, "release"
        )
        if release_compare == "ahead" and release_lines:
            lines = release_lines
    elif release_sha and _same(local.commit, release_sha):
        release_compare = "identical"
    not_modified = all(
        (
            repo_cached,
            release_cached,
            branch_cached,
            release_cached_commit or release is None,
            branch_compare_cached,
            release_compare_cached,
        )
    )
    remote = RemoteView(
        archived=archived,
        default_branch=branch_name,
        html_url=provider.web,
        release=release,
        branch_sha=branch_sha,
        branch_date=branch_date,
        branch_summary=commit_line(branch_sha, message),
        compare_status=branch_compare,
        release_compare=release_compare,
        ahead_by=ahead,
        behind_by=behind,
        commit_lines=lines,
        not_modified=not_modified,
    )
    return remote, not_modified


def _compare(provider, local_sha, remote_sha, client, cache, cancel, slot):
    url = f"{provider.api}/compare/{local_sha}...{remote_sha}"
    payload, cached = _get(client, cache, provider.key, f"compare-{slot}-{local_sha}-{remote_sha}", url, cancel, missing_ok=True)
    if payload is None:
        return None, cached, 0, 0, (), "missing"
    if not isinstance(payload, dict):
        raise GitHubError("json", "Resposta JSON inválida.")
    status = str(payload.get("status") or "")
    if status not in {"ahead", "behind", "diverged", "identical"}:
        raise GitHubError("json", "Comparação de commits inválida.")
    ahead = payload.get("ahead_by") if isinstance(payload.get("ahead_by"), int) else 0
    behind = payload.get("behind_by") if isinstance(payload.get("behind_by"), int) else 0
    commits = payload.get("commits") if isinstance(payload.get("commits"), list) else []
    lines = []
    for item in commits[-8:]:
        if not isinstance(item, dict):
            continue
        inner = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        lines.append(commit_line(str(item.get("sha") or ""), str(inner.get("message") or "")))
    return payload, cached, ahead, behind, tuple(line for line in lines if line), status


def _get(client, cache, provider, slot, url, cancel, missing_ok=False):
    _checkpoint(cancel)
    etag = cache.etag(provider, slot)
    compare = "/compare/" in url
    limit = _COMPARE_MAX_BODY if compare else None
    result = client.get_json(url, etag=etag, missing_ok=missing_ok, max_body=limit)
    if result.not_modified:
        cached = cache.body(provider, slot)
        if cached is None:
            result = client.get_json(url, etag="", missing_ok=missing_ok, max_body=limit)
            if result.not_modified:
                raise GitHubError("http", "O GitHub respondeu HTTP 304 sem conteúdo em cache.")
        else:
            return cached, True
    if result.status == 404:
        return None, False
    data = _shrink_compare(result.data) if compare else result.data
    cache.put_body(provider, slot, result.etag, data)
    return data, False


def _shrink_compare(payload):
    """A comparação oficial traz o diff inteiro. O cache fica só com o resumo."""
    if not isinstance(payload, dict):
        return payload
    commits = payload.get("commits") if isinstance(payload.get("commits"), list) else []
    short = []
    for item in commits[-8:]:
        if not isinstance(item, dict):
            continue
        inner = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        message = inner.get("message") if isinstance(inner.get("message"), str) else ""
        short.append({"sha": str(item.get("sha") or ""), "commit": {"message": message}})
    return {
        "status": payload.get("status"),
        "ahead_by": payload.get("ahead_by") if isinstance(payload.get("ahead_by"), int) else 0,
        "behind_by": payload.get("behind_by") if isinstance(payload.get("behind_by"), int) else 0,
        "commits": short,
    }


def _release(provider: Provider, payload: dict) -> ReleaseInfo | None:
    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        return None
    try:
        _ref(tag)
    except GitHubError:
        return None
    name = plain_text(str(payload.get("name") or tag), limit=120)
    published = str(payload.get("published_at") or "")
    notes = plain_text(str(payload.get("body") or ""))
    candidate = str(payload.get("html_url") or "")
    html_url = candidate if candidate.startswith(provider.web + "/") else f"{provider.web}/releases/tag/{tag}"
    return ReleaseInfo(tag=tag, name=name or tag, published_at=published, html_url=html_url, notes=notes)


def _ref(value: str) -> str:
    if not value or ".." in value or value.startswith("/") or value.endswith("/") or "\\" in value:
        raise GitHubError("url", "Referência recusada.")
    if not _REF.fullmatch(value):
        raise GitHubError("url", "Referência recusada.")
    return value


def _same(left: str, right: str) -> bool:
    from pm3manager.updates.version_comparator import same_commit

    return same_commit(left, right)


def _checkpoint(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise Cancelled()


def _from_cache_or_unavailable(
    provider,
    local,
    cache,
    error: str,
    *,
    keep_stored_local: bool = False,
) -> ProviderReport:
    stored = cache.stored_report(provider.key)
    if stored:
        report = report_from_dict(stored, None if keep_stored_local else local)
        report.fresh = False
        report.cached = True
        report.announce = False
        report.announce_text = ""
        report.error = error
        report.message = status_message(
            provider.key,
            report.relation,
            archived=report.archived,
            cached=True,
        )
        if report.remote is not None and not report.compatibility:
            report.compatibility = NOT_VERIFIED
        return report
    if error:
        relation = Relation.UNAVAILABLE
        message = status_message(provider.key, relation, archived=False, cached=False)
    elif not local.commit and not local.version:
        relation = Relation.LOCAL_UNKNOWN
        message = status_message(provider.key, relation, archived=False, cached=False)
    else:
        relation = Relation.UNAVAILABLE
        message = "Ainda não verificado."
    return ProviderReport(
        key=provider.key,
        title=provider.title,
        web_url=provider.web,
        local=local,
        remote=None,
        relation=relation,
        message=message,
        compatibility="",
        fresh=False,
        cached=False,
        checked_at="",
        error=error,
    )


def _should_announce(cache: UpdateCache, notification_id: str) -> bool:
    if not notification_id:
        return False
    if notification_id in cache.dismissed() or notification_id in cache.notified():
        return False
    return True


def _local_from_dict(payload: dict) -> LocalInstall:
    unpushed = payload.get("unpushed")
    return LocalInstall(
        present=bool(payload.get("present")),
        kind=str(payload.get("kind") or "ausente"),
        path=str(payload.get("path") or ""),
        version=str(payload.get("version") or ""),
        version_label=str(payload.get("version_label") or ""),
        commit=str(payload.get("commit") or ""),
        branch=str(payload.get("branch") or ""),
        tag=str(payload.get("tag") or ""),
        detached=bool(payload.get("detached")),
        dirty=bool(payload.get("dirty")),
        unpushed=unpushed if isinstance(unpushed, int) else None,
        remote_url=str(payload.get("remote_url") or ""),
        platform=str(payload.get("platform") or ""),
        standalone=str(payload.get("standalone") or ""),
        extras=str(payload.get("extras") or ""),
        firmware_commit=str(payload.get("firmware_commit") or ""),
        notes=tuple(str(item) for item in payload.get("notes", []) if isinstance(payload.get("notes"), list)),
    )


def _remote_from_dict(payload: dict) -> RemoteView:
    release_raw = payload.get("release")
    release = None
    if isinstance(release_raw, dict):
        release = ReleaseInfo(
            tag=str(release_raw.get("tag") or ""),
            name=str(release_raw.get("name") or ""),
            published_at=str(release_raw.get("published_at") or ""),
            html_url=str(release_raw.get("html_url") or ""),
            notes=str(release_raw.get("notes") or ""),
            sha=str(release_raw.get("sha") or ""),
        )
    lines = payload.get("commit_lines")
    return RemoteView(
        archived=payload.get("archived") is True,
        default_branch=str(payload.get("default_branch") or ""),
        html_url=str(payload.get("html_url") or ""),
        release=release,
        branch_sha=str(payload.get("branch_sha") or ""),
        branch_date=str(payload.get("branch_date") or ""),
        branch_summary=str(payload.get("branch_summary") or ""),
        compare_status=str(payload.get("compare_status") or ""),
        release_compare=str(payload.get("release_compare") or ""),
        ahead_by=payload.get("ahead_by") if isinstance(payload.get("ahead_by"), int) else 0,
        behind_by=payload.get("behind_by") if isinstance(payload.get("behind_by"), int) else 0,
        commit_lines=tuple(str(item) for item in lines) if isinstance(lines, list) else (),
        not_modified=bool(payload.get("not_modified")),
    )


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _diag(message: str) -> None:
    try:
        from pm3manager.logging_setup import log

        log(20, "U001", message, component="updates", operation="consulta")
    except Exception:
        return
