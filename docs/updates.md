# Update monitor

Version 2.0.0 adds a read-only monitor for two official repositories. It
does not update either project, and it does not compile or flash because a
newer release exists.

The window stays in Brazilian Portuguese. This document is the English
description of that behavior.

## What is checked

| Panel | Repository | API |
| --- | --- | --- |
| Iceman | https://github.com/RfidResearchGroup/proxmark3 | `https://api.github.com/repos/RfidResearchGroup/proxmark3` |
| ProxSpace | https://github.com/Gator96100/ProxSpace | `https://api.github.com/repos/Gator96100/ProxSpace` |

The client uses the GitHub REST API over HTTPS. It does not scrape HTML and
it does not ask for a personal token. Public requests are enough. A token is
not stored and is not written to the log.

On startup the window paints the last saved result, then asks GitHub from a
worker thread. The same check repeats while the window is open. The default
interval is **60 minutes**. The allowed range is 15 to 1440 minutes.
**Configurações** in the **Atualizações** panel can turn the automatic check
off, change the interval, or turn the visual notice off. **Verificar
atualizações** runs one check immediately. Nothing in that panel runs `git
pull`, `git fetch`, `git checkout`, `git reset`, a ProxSpace reinstall, an
MSYS2 install, a compile, or a flash.

The default branch is the `default_branch` field returned for that
repository. The monitor does not assume `master`.

## Releases and commits

**Última release** is the newest GitHub release (`/releases/latest`), when
one exists. **Commit da branch** is the tip of the default branch. Those are
different facts. A newer commit is not described as a stable release, and a
release is not called newer only because its date is later.

A release is reported as available only when the parsed version is greater
and GitHub's compare API says that release commit is ahead of the local
commit on the same history. Different hashes alone do not mean an update.
If the histories have diverged, the panel says so and does not send a "new
version" notice.

The firmware string read from the Proxmark3 is not the version of the
checkout on disk. The monitor shows the checkout.

**Commit local** is `git rev-parse HEAD` for the selected checkout. It is
not the third quoted field of `common/default_version_pm3.c`. Iceman's
`tools/mkversion.sh` writes that field as the first nine hex digits of a
SHA-256 over the firmware sources. On the validated tree the file contains
`9ce8a4b6c`, while HEAD is the release commit tagged `v4.23346`. That
fingerprint is not a Git object in the shallow checkout, and the panel does
not display it in **Commit local**. The observation line labels it as the
version-file identifier.

## Archived ProxSpace

The ProxSpace repository was archived in September 2026. The monitor shows
that state when GitHub reports `archived: true`. An archived repository does
not mean the local installation is out of date or unusable. The local
version comes from a `VERSION` file (or `version.txt`, `PROXSPACE_VERSION`,
or the same names under `setup\`) or from a git tag when the folder is a
checkout. File dates are not used. If none of those sources exist, the panel
says **Versão local não identificada**.

## Cache, offline use, and rate limits

Results are stored in the application data directory, in `updates\monitor.json`.
In this source tree that is `var\updates\`. It is not the firmware cache
(`var\cache\`) and it is not part of the published tree.

A successful response can send `ETag`. The next request sends
`If-None-Match`. HTTP 304 means the cached body is still current. If GitHub
cannot be reached, the panel keeps the previous result and prefixes it with
**Exibindo resultado da última verificação.** That text means the lines are
not a live result.

The compare call can return every changed file. The client accepts up to
4 MB for that one response and stores only the status and the latest commit
subjects returned. Patch text is not kept. Other responses stay limited to 1 MB.
A comparison larger than 4 MB is reported as unavailable instead of being truncated.

HTTP 403 or 429 that indicates a rate limit stops further calls until the
reset time from `X-RateLimit-Reset`. The monitor does not bypass the limit.
A failed check does not delete the firmware cache and does not change
`Makefile.platform`.

The same release or commit is not announced twice. **Dispensar** hides the
notice and leaves the panel text in place.

## Compatibility and supervised updates

Seeing a release does not mean it is safe to build or flash on the connected
board. The panel says **Compatibilidade da atualização não verificada.**
The validated image remains `PM3GENERIC` for the AT91SAM7S512 board with
512 KB of internal flash and external SPI flash. This application still does
not build or flash an RDV4 image.

**Ver instruções de atualização** only shows that explanation. There is no
**Atualizar agora** button in this version. A later, separate design would
have to add a backup, a separate checkout, and an explicit authorization
before any file is changed.

## Preferences

These keys live in `preferences.json` next to the other application
preferences. They are not a flash authorization.

| Key | Default | Meaning |
| --- | --- | --- |
| `updates_enabled` | true | Repeat the check while the window is open. |
| `updates_interval_minutes` | 60 | Period of that check. Values outside 15–1440 are clamped. |
| `updates_notify` | true | Show the one-line notice for a new release or new commits. |

`flash_autorizado` is still stored as false and is still ignored when the
file is loaded.

## Baseline tag

There is no `v1.0.0` tag in this repository yet. The published V1 source is
`main` at `0220808428b7a17e1fd118bb3b2e2a64f7b2c4a6`. A tag can be created
later, on that commit, after a separate decision. This branch does not
create or push tags.

## Network and hardware

The remote check needs internet and does not use the COM port. The window
still opens when the Proxmark3 is unplugged and when ProxSpace is missing;
the local side is then reported as not identified, and a failed request is
reported as **Não foi possível consultar o GitHub.**
