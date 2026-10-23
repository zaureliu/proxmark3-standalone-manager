# Packaging

This describes how to build a Windows one-directory folder and a local zip
on your own computer. The public repository is source code only and does
not contain that folder. `DISTRIBUTION-STATUS.txt` says
`PUBLICATION: BLOCKED` for the binary package. Do not attach `dist\` to a
public download until the conditions in `docs/licensing.md` and
`docs/corresponding-source.md` are actually met by the person distributing
the binary. A folder of separate Qt DLLs is not enough. Publishing the
source does not publish Qt.

If you redistribute an executable you built, you must comply with the
licenses of every dependency that build includes. The MIT license does not
cover Qt, PySide6, Shiboken, pyserial, PyInstaller, or the Microsoft
runtime libraries.

## Version

The version is `pm3manager.__version__`, currently `1.0.0`, and the same
value in `pyproject.toml`. `scripts\build_exe.ps1` prints it before
PyInstaller runs. Change both places together. The executable name stays
`Proxmark3StandaloneManager.exe`. The zip name includes the version:
`Proxmark3StandaloneManager-v1.0.0-windows-x64.zip`.

## Reproduce the build

On Windows, from any directory:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

The script creates `.venv` if needed, installs `requirements.txt`, redraws
`assets\icon.ico`, runs PyInstaller on `Proxmark3StandaloneManager.spec`,
then runs `scripts\stage_distribution.ps1`. It does not modify the system
`PATH`, does not flash firmware, and does not upload the zip.

The spec is one-directory and windowed (`console=False`, `upx=False`,
`contents_directory="_internal"`). The output is:

```text
dist\Proxmark3StandaloneManager\Proxmark3StandaloneManager.exe
dist\Proxmark3StandaloneManager\_internal\
```

After staging, the same folder also contains `LICENSE`,
`THIRD_PARTY_NOTICES.md`, `DISTRIBUTION-STATUS.txt`,
`CORRESPONDING-SOURCE.md`, `README.txt`, `licenses\`, and
`SHA256SUMS.txt`. The zip is created beside the folder, not inside it:

```text
dist\Proxmark3StandaloneManager-v1.0.0-windows-x64.zip
dist\SHA256SUMS.txt
```

`dist\SHA256SUMS.txt` lists the zip and the executable. The sums file
inside the folder lists the files in the folder and is itself inside the
zip. `scripts\hash_artifacts.ps1` only refreshes the outer file. It does
not rebuild the zip.

To fetch the Qt and PySide6 source archives into `third-party-source\` and
check their SHA-256 values:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\fetch_corresponding_source.ps1
```

Those archives are gitignored. They are not placed in the zip. Holding
them on the build machine does not make the zip publishable. See
`docs/corresponding-source.md`.

## Files required to build

| Path | Role |
| --- | --- |
| `pm3manager\` | Application source |
| `assets\icon.ico` | Window and executable icon |
| `Proxmark3StandaloneManager.spec` | PyInstaller one-dir spec |
| `requirements.txt` | Runtime, build, and test packages |
| `pyproject.toml` | Runtime package metadata |
| `scripts\build_exe.ps1` | Build entry point |
| `scripts\stage_distribution.ps1` | Notices, checksums, local zip |
| `scripts\make_icon.py` | Regenerates the icon with Pillow |
| `scripts\hash_artifacts.ps1` | Refreshes the outer SHA-256 file |
| `scripts\fetch_corresponding_source.ps1` | Local Qt and PySide6 source archives |
| `scripts\create_shortcut.py` | Optional local shortcut on the builder's desktop |
| `licenses\` | Texts copied into the folder |
| `.pm3manager-root` | Marks a development tree so its executable keeps using `var\` |

Not required, and not shipped: ProxSpace, the Iceman checkout, `var\`,
firmware cache, backups, `catalog\modulos.json`, `.venv`, and
`third-party-source\`. The development marker is not copied into `dist\`.

## What the folder contains

The application bytecode, the icon, the PyInstaller bootloader, pyserial,
PySide6 and Shiboken, the Qt DLLs and plugins those hooks collect, and the
Microsoft Visual C++ runtime DLLs those binaries need. Pillow is not
imported by the application. The exact DLL list moves if PyInstaller or
PySide6 changes. Inspect `_internal` before any future publication, and do
not commit `build\` or `dist\`.

The old one-file executable, `dist\Proxmark3StandaloneManager.exe` as a
file rather than a directory, is removed by the staging script when it is
still present. The shortcut has to point at the executable inside the
folder. Its working directory is that folder.

## Checksums

After a build, `dist\SHA256SUMS.txt` is already written. To recompute the
outer lines without rebuilding the zip:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\hash_artifacts.ps1
```

Compare the hex value with the file. The checksum files are outputs, not
source. Do not publish them next to a download while
`DISTRIBUTION-STATUS.txt` says publication is blocked.

## Data directories

A one-dir executable that is still inside this development tree finds
`.pm3manager-root` by looking at its own folder, the parent, and the
grandparent. It keeps using `var\`. A copy that does not contain that
marker, and whose parent and grandparent do not contain it either, uses
`%LOCALAPPDATA%\Proxmark3StandaloneManager`. It does not need write access
to the folder that contains the executable. The generated module catalog
is written in the data directory. It is written into the source tree only
for a development tree.

## Local shortcut

```text
.venv\Scripts\python.exe .\scripts\create_shortcut.py
```

The shortcut name is `Proxmark3 Standalone Manager`. It targets the one-dir
executable and uses that executable's folder as the working directory.
`scripts\install.ps1` is a local developer helper. It is not a publication
pipeline.
