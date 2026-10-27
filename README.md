# Proxmark3 Standalone Manager

Desktop application for choosing a Standalone module, compiling it with an
existing ProxSpace installation, and writing the resulting fullimage only
when you explicitly authorize that one operation.

The window is in Brazilian Portuguese. This repository is the manager. It
is not the Proxmark firmware, it is not ProxSpace, and it is not an official
RfidResearchGroup product.

Version 2.1.0 is the source published on `main`. The annotated tag
`v2.1.0` identifies that publication. The tags `v1.0.0` and `v2.0.0`
stay where they are. There is no GitHub Release for 2.1.0, and the
binary package stays `PUBLICATION: BLOCKED`.

Source: https://github.com/zaureliu/proxmark3-standalone-manager

**Distribution: Source Code Only**

This repository distributes the original source and the files required to
install, test, and compile the application. It does not distribute a
Windows executable, a zip that contains an executable, Qt, PySide6, or
Shiboken binaries, any other third-party binary library, a compiled
firmware image, ProxSpace, an Iceman checkout, a firmware cache, RFID
dumps, logs, backups, or local preferences.

The MIT license covers only the original material. External dependencies
remain under their own licenses. Publishing or cloning this source is not
an official redistribution of Qt or of the Iceman firmware, and it is not
a Proxmark3, Iceman, ProxSpace, Qt, or PySide6 product. This project does
not own those names.

A person who builds an executable and gives that executable to anyone else
has to comply with the licenses of the dependencies that build includes.
This repository does not supply that permission for Qt or PySide6.

## Main features

- Finds a ProxSpace installation and the Iceman checkout under its `pm3`
  folder, or asks you to select the folder. It does not install either
  project.
- Lists Standalone modules from that checkout's `Makefile.hal` and marks
  them compatible, flash-dependent, uncertain, or incompatible.
- Detects a Proxmark3 COM port from the USB IDs below. The port number is
  not fixed.
- Reads `hw version` and `hw status` through the official client.
- Compiles with `PLATFORM=PM3GENERIC` and `LED_ORDER=PM3EASY`. The LED
  setting selects AT91SAM7S support. It does not identify the board as an
  Easy.
- Adds `PLATFORM_EXTRAS=FLASH` only when you confirm external SPI flash.
- Reuses a fullimage cache when the version, commit, sources, toolchain,
  and configuration still match.
- Flashes only the fullimage, and only for the Apply operation you
  authorized. The bootloader is not updated. `pm3-flash-all` and
  `--unlock-bootloader` are not used.
- Restores the checkout's `Makefile.platform` after a build. An interrupted
  build is restored on the next startup and is not flashed again.
- Reports a partial post-flash check as `OK210`. It does not claim the
  Standalone module was identified.
- Can diagnose an RDV4. It does not compile or flash an RDV4 image.
- Writes an operational log and can open the official client on the
  detected port.
- Includes a local script that can build a windowed Windows executable on
  the user's computer. That executable is not part of this repository and
  does not embed the firmware.
- Reports Iceman and ProxSpace updates from the official GitHub API. The
  **Atualizações** panel stays compact. **Ver detalhes** opens the full
  fields in a separate dialog. The report is informational. The application
  does not pull, compile, or flash because a newer release or commit exists.
  See [Update monitor](docs/updates.md).
- Keeps **Aplicar módulo**, **Recompilar**, **Verificar dispositivo**,
  **Abrir cliente Proxmark3**, and **Visualizar logs** outside any scroll
  area. The module description scrolls on its own.
- Adds a **Diagnóstico** tab. It reads USB identity and, only on request,
  `hw version`, `hw status`, and `hw ping`. It does not compile, flash, or
  change the Makefile. See [Diagnostics](docs/diagnostics.md).
- Adds an offline **Manual** for the 41 Standalone modules in the v4.23346
  catalog, opened with **Ver manual do módulo**. Unknown fields stay
  unknown. See [Module guide](docs/module-guide.md).

Compiling without flashing is a normal, supported action.

## Requirements

- 64-bit Windows with a working USB port.
- Python 3.11 or newer, with the `py` launcher. Continuous integration uses
  Python 3.11. A newer Python is not required.
- ProxSpace, including its MSYS2 shell and the GNU Arm embedded toolchain,
  already installed. This application does not install it.
- An Iceman checkout inside that ProxSpace tree. The laboratory record used
  **Iceman v4.23346**. Another checkout may load. It is not certified here.
- A Proxmark3 whose MCU the Iceman `PM3GENERIC` image can run. The tested
  board is described under Hardware Validation. Other boards are not
  certified by this project.

Runtime Python packages are PySide6 and pyserial. Pillow, PyInstaller, and
pytest are installed by `requirements.txt` for a local build and for the
test suite. The compiler, `make`, and the Proxmark client come from
ProxSpace. They are not Python dependencies. Versions and licenses:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Quick start

Run these commands from a new directory. They do not flash a device.

```text
git clone https://github.com/zaureliu/proxmark3-standalone-manager.git
cd proxmark3-standalone-manager
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pm3manager
```

Diagnosis, without opening the window:

```text
.venv\Scripts\python.exe -m pm3manager --self-check
```

`"ok": true` in `var\self-check.json` means ProxSpace and a checkout were
found. It does not mean firmware was written. Without ProxSpace the check
fails with `E001`.

If the window does not find ProxSpace, choose the installation folder when
asked, or use **Selecionar ProxSpace**. Then connect the Proxmark3, use
**Verificar dispositivo**, and compile with **Recompilar**. Tick the flash
authorization only when the next **Aplicar módulo** should run
`pm3-flash-fullimage`.

## Installation

The complete Windows procedure — Python, ProxSpace, the Iceman checkout,
this clone, the virtual environment, device detection, compilation, and
explicit flashing — is in [docs/install.md](docs/install.md).

Do not run `runme64.bat` as part of starting this application. Commands go
through `msys2_shell.cmd`.

### Optional local executable

The repository keeps the PyInstaller script so you can build a
one-directory folder on your own computer. That build is not an official
download.

```text
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

The script writes `dist\Proxmark3StandaloneManager\Proxmark3StandaloneManager.exe`.
`dist\` is not part of the Git history. `DISTRIBUTION-STATUS.txt` keeps the
binary package marked `PUBLICATION: BLOCKED`. Building the folder locally
does not authorize redistribution of Qt or PySide6. Read
[docs/licensing.md](docs/licensing.md) before giving the folder to anyone
else. Checksums and the folder layout are in
[docs/packaging.md](docs/packaging.md).

## Supported hardware

| Topic | Version 2.0.0 |
| --- | --- |
| Tested MCU | AT91SAM7S512, 512 KB internal flash, external SPI flash reported as 2048 Kb |
| Image this app builds | `PM3GENERIC` only |
| 512 KB internal flash | `PLATFORM_SIZE` is left empty. `256` is not forced. |
| 256 KB internal flash | `PLATFORM_SIZE=256` is forced when the MCU text says 256 and not 512. This was not the tested board. |
| Unknown MCU | Size stays empty. The validated path is not blocked only because the MCU line is missing. |
| USB `9AC4:4B8F` | Accepted as an Iceman Proxmark3. |
| USB `2D2D:504D` | Accepted as a legacy Proxmark3. |
| USB `502D:502D` | Accepted because the driver profile calls it Easy. That label does not select a 256 KB image. |
| RDV4 | May be recognized and diagnosed (`OK202`). RDV4-specific compilation and flashing are not implemented. Writing the PM3GENERIC image to an RDV4 is blocked. |
| Bluetooth or smartcard modes | Classified incompatible when the checkout says they require that hardware. |
| Bootloader | Not programmed by this application. |

More detail, including the module counts from the v4.23346 checkout, is in
[docs/compatibility.md](docs/compatibility.md).

## Hardware Validation — MattyRun

On 23 October 2026 one physical test was completed. It applies only to the
combination below.

Environment:

- Proxmark3 with MCU AT91SAM7S512
- 512 KB of internal flash
- External SPI flash of 2048 Kb
- Iceman v4.23346
- Platform `PM3GENERIC`
- HF MIFARE Classic chk/ecfill/sim — MattyRun

Procedure:

1. The module was selected in Standalone Manager.
2. The firmware was compiled and flashed from the application.
3. The device was restarted and communication was established again.
4. The device was powered independently from a power bank.
5. Standalone mode was activated on the device.
6. A MIFARE tag owned by the laboratory was copied.
7. The copied tag was emulated.
8. A smartphone recognized that emulation.

Result: this scenario worked. The record does not certify every Standalone
module, every tag type, or every Proxmark3 model. The application still
reports the automatic post-flash check as partial validation (`OK210`). A
human test is not something the program can see, and the program does not
store tag contents.

Test only equipment, tags, and systems that you own or that you are
explicitly authorized to test. This document does not include tag data,
keys, dumps, or identifiers from that test.

## Update monitor

The application watches the official Iceman and ProxSpace GitHub repositories.
The compact **Atualizações** panel shows a notice and a short summary.
**Ver detalhes** opens a separate dialog. **Configurações** is in that
dialog, not on the compact strip. The monitor does not install updates, does
not run `git pull`, and does not flash. There is no **Atualizar agora**
button. See [docs/updates.md](docs/updates.md).

## Tests

From the repository root, after the Quick start install:

```text
.venv\Scripts\python.exe -m compileall -q pm3manager tests scripts
.venv\Scripts\python.exe -m pytest tests
```

Tests that need a ProxSpace folder next to the project, with the
`proxmark3-v4.23346` checkout, are skipped when that checkout is absent.
Continuous integration has no ProxSpace and no Proxmark3. It installs
`requirements.txt`, runs `compileall`, and runs pytest. It does not flash
and it does not publish an executable.

## Further documentation

- [Installation](docs/install.md)
- [Compatibility](docs/compatibility.md)
- [Diagnostics](docs/diagnostics.md)
- [Standalone module guide](docs/module-guide.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Update monitor](docs/updates.md)
- [Licensing](docs/licensing.md)
- [Packaging](docs/packaging.md)
- [Contributing](CONTRIBUTING.md)

Screenshots are not in the tree. The reason is
[docs/screenshots/README.md](docs/screenshots/README.md).

## Compilation, flashing, and OK210

**Aplicar módulo** runs off the UI thread. It checks compatibility, reuses
the cache or runs `make clean` and `make -j` inside ProxSpace, and restores
`Makefile.platform` afterwards. If flashing is not authorized, it stops with
`OK100`. The device is unchanged.

If flashing is authorized, it runs `./pm3-flash-fullimage` once. The
confirmation already shown when you ticked the box is not repeated. It then
waits for the device to reappear and runs `hw version` and `hw status`.

**Recompilar** always rebuilds and never flashes. **Verificar dispositivo**
never flashes. Neither button consumes a pending flash authorization. The
checkbox starts cleared every time the application opens. A value left in
`preferences.json` is ignored and rewritten as false.

`OK210` means all of the following happened:

- the flash script reported `All done`
- the device reconnected
- the client could talk to it again
- the firmware version matches the checkout

It does **not** mean the Standalone module was confirmed. On the tested
Iceman version, `hw version` and `hw status` do not reliably name the
active module. `OK200` is reserved for a laboratory proof, and the
application does not emit it.

Nothing is flashed at startup or because a preference file says so. The
only flash command is `pm3-flash-fullimage`. The device bootloader is not
programmed. Common error codes are in
[docs/troubleshooting.md](docs/troubleshooting.md).

## Limitations

- The project is distributed as source only. ProxSpace and the Iceman
  firmware are not included.
- Compatibility depends on the connected hardware and on the Iceman checkout
  you already have. One module, MattyRun, has one laboratory record. The
  other modules do not.
- RDV4 compilation and flashing are not implemented.
- `OK210` remains a partial check. It is not proof that every module works.
- The update monitor reports official releases and commits. It does not
  install them, and a newer release is not assumed to be compatible.
- The application does not run on macOS or Linux.
- A locally built Windows folder is not a public release. Generating it
  does not authorize redistribution of Qt, PySide6, or the other libraries
  under that folder. See [docs/licensing.md](docs/licensing.md).

## License and credits

The original application code is under the MIT license. Copyright (c) 2026 Anderson A. Justino.
See [LICENSE](LICENSE). That grant does not relicense
Qt, PySide6, or the other components named in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

- Iceman firmware, RfidResearchGroup:
  https://github.com/RfidResearchGroup/proxmark3
- Standalone mode notes:
  https://github.com/RfidResearchGroup/proxmark3/wiki/Standalone-mode
- ProxSpace, the Windows build environment this program drives but does not
  include: https://github.com/Gator96100/ProxSpace
- Qt for Python (PySide6): https://doc.qt.io/qtforpython/
- pyserial: https://github.com/pyserial/pyserial
- PyInstaller: https://pyinstaller.org/

Proxmark3, Iceman, the RfidResearchGroup name, ProxSpace, Qt, and PySide6
are not owned by this project. Qt is a trademark of its owner. This
application is an independent, unofficial tool. It calls those projects on
the machine where you installed them. It does not redistribute them.
