# Changelog

The version number in `pm3manager/__init__.py` and `pyproject.toml` is 2.0.0.
Dates below are the dates the work was prepared, not publication dates.
Version 2.0.0 is on `feature/update-monitor-v2` and is not published.
There is still no `v1.0.0` tag. The published V1 commit on `main` is
`0220808428b7a17e1fd118bb3b2e2a64f7b2c4a6`. A later decision can tag that
commit. This branch does not create the tag.

## 2.0.0 — prepared, not published

### Fixed

- The main window keeps the device, module, update, operation, and progress
  panels readable when the window is resized. Hardware text no longer paints
  over the SPI and `PLATFORM_SIZE` confirmations. The module list prefers a
  vertical scrollbar, and the update panel is no longer capped at a thin strip.
- **Commit local** shows the Git HEAD of the selected checkout. The third
  field of `common/default_version_pm3.c` stays labeled as a source
  fingerprint and is not presented as that commit.

### Added

- Read-only update monitor for the official Iceman and ProxSpace GitHub
  repositories. The **Atualizações** panel shows the local checkout, the
  latest release, and the default-branch commit separately. It repeats the
  check every 60 minutes unless that schedule is disabled, keeps the last
  result when GitHub cannot be reached, and does not pull, compile, or
  flash. See `docs/updates.md`.

## Already on published main

These notes were written while 1.0.0 was being prepared. They are on the
published `main` commit named above. They are not part of the 2.0.0 monitor.

### Fixed

- `.gitignore` no longer ignores `pm3manager/build`. That package is the
  compiler used by the application, and without it the CI import fails.
- Pytest can start on a clean checkout. `--basetemp=var/pytest` requires
  the gitignored `var` directory, which Git does not create. The test
  configuration creates that parent before pytest does, and `var` stays
  out of the published tree.
- Log-isolation tests no longer require the local file `var/logs/app.log`.
  A clean checkout does not contain it. The tests still fail if a run
  creates or changes that file.

### Changed

- The public tree is source code only. It documents how to install Python,
  create a virtual environment, and run `python -m pm3manager`. It does not
  offer an official Windows executable. The local one-directory build
  remains a validation artifact: `DISTRIBUTION-STATUS.txt` marks that
  binary package `PUBLICATION: BLOCKED`. Publishing the source is not
  permission to publish the binary, and it is not a redistribution of Qt
  or Iceman.
- The original application code is under the MIT license. Copyright (c)
  2026 Anderson A. Justino. Third-party components keep their own licenses.
  The optional Windows package is a PyInstaller one-directory folder. Qt
  libraries are files under `_internal`. The local zip remains blocked
  until the Qt and PySide6 corresponding source is offered by whoever
  distributes that package. See `docs/licensing.md`.
- Flash authorization is kept in memory only. Loading preferences always
  starts with it off, saving preferences always writes it as off, and the
  next **Aplicar módulo** is the only operation that uses it. That operation
  clears the authorization when it finishes or fails. Unchecking the box
  clears it as well. Recompile and device verification do not flash and do
  not consume the pending authorization.
- The Windows build script prints the application version and writes a
  SHA-256 checksum for the executable.

### Added

- English project documentation, third-party notices, contribution and
  security guidance, and a Windows CI workflow that runs the tests without
  ProxSpace or a connected Proxmark3.
- Regression tests for the flash-authorization rules.

## 1.0.0 — source prepared

- Desktop application for selecting a Standalone module, compiling a
  PM3GENERIC fullimage through an existing ProxSpace installation, and
  flashing that fullimage only after an explicit authorization.
- Firmware cache, partial post-flash validation (OK210), and RDV4 diagnosis
  without RDV4 compilation or flashing.
- A windowed Windows executable can be built locally with PyInstaller. It
  is not part of the source publication, and the binary package stays
  blocked.
