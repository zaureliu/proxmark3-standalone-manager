# Changelog

The version number in `pm3manager/__init__.py` and `pyproject.toml` is 1.0.0.
Nothing in this tree has been pushed to a public remote. Dates below are
the dates the work was prepared, not publication dates.

## Unreleased

### Fixed

- `.gitignore` no longer ignores `pm3manager/build`. That package is the
  compiler used by the application, and without it the CI import fails.

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
