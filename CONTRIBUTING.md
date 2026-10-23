# Contributing

This repository is source code only. Do not add Windows executables, Qt or
PySide6 binaries, compiled firmware, a ProxSpace tree, an Iceman checkout,
RFID dumps, logs, backups, or local preferences. Build scripts may stay.
Each contributor installs the dependencies and can build locally.

## What belongs here

This repository is only the Standalone Manager. Do not add a ProxSpace
installation, an Iceman checkout, compiled firmware, tag dumps, card data,
or the Qt and PySide6 source archives downloaded for a local license check.
Those archives belong in `third-party-source\`, which is gitignored.

The interface is Brazilian Portuguese. Keep user-visible strings in that
language unless the owner asks for a translation. Documentation for GitHub is
English.

## Local setup

Python 3.11 or newer and a Windows machine are required. ProxSpace is
required only for tests marked as needing the local checkout, and for
actually compiling firmware. See `docs/install.md`.

```text
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest tests
```

A normal test run must not flash a Proxmark3. Do not call
`pm3-flash-fullimage`, `pm3-flash-all`, `pm3-flash-bootrom`, or
`--unlock-bootloader` from a test or from CI.

## Changes that need extra care

- Flash authorization must stay off at startup, must not be restored from
  `preferences.json`, and must cover only the Apply operation that the user
  confirmed.
- `OK210` means partial validation. Do not turn it into a claim that the
  Standalone module was proved.
- RDV4 devices may be recognized and diagnosed. Do not add RDV4 compilation
  or flashing unless that work is separately specified and tested.
- The `Makefile.platform` read by `make` is the one inside the active
  checkout. Do not write the copy that sits directly under `pm3/`.
- Do not put a personal path, Windows user name, COM port, USB serial number,
  or hardware unique ID in source, tests, or documentation.

## What not to commit

`.gitignore` excludes virtual environments, `build/`, `dist/`, `var/`,
firmware images, logs, preferences, and the generated module catalog. If a
file contains a dump, a key, a serial number, or a machine-specific path,
leave it out even if Git does not ignore it automatically.

## Tests

Run the full `pytest` suite before handing a change back. Tests that need
the laboratory ProxSpace checkout skip themselves when that checkout is
absent; they must still pass on a machine where it is present. The CI
workflow in `.github/workflows/ci.yml` is the same idea: install, compile
the Python sources, and run pytest. It must not gain a deploy or firmware
job.

## Conduct

See `CODE_OF_CONDUCT.md`. Experiment only on equipment, tags, and systems
you own or are explicitly allowed to test.
