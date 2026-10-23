# Proxmark3 Standalone Manager

Desktop application for choosing a Standalone module, compiling it with an
existing ProxSpace installation, and writing the resulting fullimage only
when you explicitly authorize that one operation.

The window is in Brazilian Portuguese. This repository is the manager. It
is not the Proxmark firmware, it is not ProxSpace, and it is not an official
RfidResearchGroup product.

Version 1.0.0.

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

## Objective

Standalone mode is selected at compile time. Changing it means building
another fullimage and, if you want the device to run it, flashing that
image. The manager keeps that work in one window: find ProxSpace, list the
modes from the checkout you already have, compile `PM3GENERIC`, and flash
with `pm3-flash-fullimage` only after a confirmation that is not stored.

Compiling without flashing is a normal, supported action.

## Main features

- Finds a ProxSpace installation and the Iceman checkout under its `pm3`
  folder, or asks you to select the folder.
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

## System requirements

- 64-bit Windows with a working USB port.
- ProxSpace, including its MSYS2 shell and the GNU Arm embedded toolchain,
  already installed. See [Installation](docs/install.md).
- An Iceman checkout inside that ProxSpace tree. Development and the
  laboratory record used **Iceman v4.23346**.
- Python 3.11 or newer. The supported way to run this repository is the
  Python source tree below. A locally built executable is optional and is
  not published here.
- A Proxmark3 whose MCU the Iceman `PM3GENERIC` image can run. The tested
  board is described under Hardware Validation. Other boards are not
  certified by this project.

## Dependencies

Runtime:

- PySide6 (Qt for Python), inspected at 6.12.0
- pyserial, inspected at 3.5

Build and tests, not required to run a copy of the executable:

- Pillow, used only to draw the icon
- PyInstaller
- pytest

The compiler, `make`, and the Proxmark client come from ProxSpace. They are
not Python dependencies and they are not inside the executable. Versions and
licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Supported hardware and limitations

| Topic | Version 1.0.0 |
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

## Install and run on Windows

The commands below match this tree. Run them from the repository root, the
directory that contains `pyproject.toml` and `pm3manager`. Do not run
`runme64.bat` as part of these steps. The application starts ProxSpace
commands through `msys2_shell.cmd` itself.

1. Install Python 3.11 or newer for 64-bit Windows, including the `py`
   launcher. The continuous-integration job uses Python 3.11. Confirm the
   launcher with `py -3.11 --version`.
2. Install ProxSpace, or locate an installation you already have. The
   folder must contain `runme64.bat` and `msys2\msys2_shell.cmd`, and an
   Iceman checkout under `pm3\`. This repository does not include either
   project. See [Installation](docs/install.md).
3. Obtain this source tree and open a terminal in its root. There is no
   binary download. After a public remote exists, clone
   `proxmark3-standalone-manager` and use that checkout. This file does
   not name a remote that has not been created.
4. Create a virtual environment:

```text
py -3.11 -m venv .venv
```

5. Install the dependencies:

```text
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

6. Start the application with Python. This does not flash the device:

```text
.venv\Scripts\python.exe -m pm3manager
```

   A health check that does not open the window:

```text
.venv\Scripts\python.exe -m pm3manager --self-check
```

   `"ok": true` in the resulting `self-check.json` means ProxSpace and a
   checkout were found. It does not mean firmware was written.
7. If the window does not find ProxSpace, use **Selecionar ProxSpace** and
   choose the installation folder from step 2.
8. Connect the Proxmark3 by USB.
9. Read the device panel and confirm the COM port it selected. The port
   number is not fixed. **Verificar dispositivo** runs `hw version` and
   `hw status` and does not flash.
10. Select a Standalone module and read its compatibility notes. Confirm
    external SPI flash only when the board has it.
11. **Recompilar** compiles and does not flash. **Aplicar módulo** with the
    flash box clear also compiles and stops at `OK100`. Tick **Autorizar
    gravação real da fullimage no próximo Aplicar módulo** only when that
    next Apply should run `pm3-flash-fullimage`. The authorization is not
    stored and is cleared when that operation finishes or fails.

### Optional local executable

The repository keeps the PyInstaller script so you can build a
one-directory folder on your own computer. That build is not an official
download, and the first publication of this source does not include it.

```text
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

The script creates `.venv` when needed, installs `requirements.txt`, and
writes:

```text
dist\Proxmark3StandaloneManager\Proxmark3StandaloneManager.exe
```

`dist\` is not part of the Git history. Copying that folder to another
computer is a local choice. A copy that is not inside a development tree
stores preferences, logs, and cache in
`%LOCALAPPDATA%\Proxmark3StandaloneManager`. It does not read a developer's
`var` folder. Checksums and the folder layout are in
[docs/packaging.md](docs/packaging.md).

`DISTRIBUTION-STATUS.txt` keeps the binary package marked
`PUBLICATION: BLOCKED`. Building the folder locally does not make that
package a public release of Qt or of this project.

If you redistribute an executable you built, you must comply with the
licenses of every dependency included in that build, including PySide6,
Qt, Shiboken, pyserial, PyInstaller, and the Microsoft runtime libraries.
The MIT license of this project does not cover those components. Read
[docs/licensing.md](docs/licensing.md) before giving the folder to anyone
else.

## ProxSpace location

The application does not ship ProxSpace and does not move or update it.

Search order:

1. Folder already saved in preferences.
2. `PM3MANAGER_PROXSPACE` or `PROXSPACE` if one of those variables is set.
   An invalid value is reported. There is no silent fallback.
3. A `ProxSpace` directory next to the project, then inside the project,
   then the current working directory.

Use **Selecionar ProxSpace** to point at another disk. The checkout list
shows the accepted `proxmark3*` directories under that installation's `pm3`
folder. The highest version is the default.

Commands run through `msys2_shell.cmd -mingw64 -defterm -no-start`. They do
not call `runme64.bat`.

## Automatic COM detection

The program enumerates serial ports about every 1.5 seconds. Only the USB
IDs in the hardware table are treated as a Proxmark3. A generic serial
adapter is ignored. An unknown VID/PID that merely mentions Proxmark in the
text stays at medium confidence, and flashing is refused. If two accepted
devices are connected, select one. The status line names the port that was
found.

**Verificar dispositivo** runs `hw version` and `hw status` on that port
with the client already built in the checkout.

## Standalone module selection

Search by name, protocol, or identifier, or filter by LF, HF, multi-mode,
or other. The details panel shows the description, compatibility,
requirements, and limits taken from the checkout.

- Incompatible modules leave **Aplicar módulo** disabled. The application
  does not rewrite them for `PM3GENERIC`.
- Uncertain modules stay blocked until you confirm that you accept their
  requirements on this board. That confirmation does not turn on SPI flash.
- `HF_ST25_TEAROFF`, on the tested checkout, stays blocked until SPI flash
  is confirmed, because the makefile requires it.

The catalog is regenerated from the checkout. A generated JSON file on a
development machine is not a second source of truth and is not part of the
Git history.

## Compilation and flashing

**Aplicar módulo** runs off the UI thread.

1. Checks module compatibility.
2. If flashing is authorized, checks that a single accepted device is
   present and that the image is not blocked for this MCU or for an RDV4.
3. Reuses the cache or runs `make clean` and `make -j` inside ProxSpace.
   During that build it writes a marked `Makefile.platform` in the checkout
   root and restores the previous file afterwards.
4. If flashing is not authorized, it stops with `OK100`. The device is
   unchanged.
5. If flashing is authorized, it runs `./pm3-flash-fullimage` once. The
   confirmation already shown when you ticked the box is not repeated.
6. Waits for the device to reappear and runs `hw version` and `hw status`.

**Recompilar** always rebuilds and never flashes. **Verificar dispositivo**
never flashes. Neither button consumes a pending flash authorization.

The authorization checkbox starts cleared every time the application opens.
A value left in `preferences.json` by an older build is ignored and rewritten
as false. The other preference fields are kept. The authorization is cleared
again when the authorized Apply finishes or fails, and when you clear the
checkbox. There is no second question in the middle of that Apply.

While the box is checked, the panel states that the next Apply will write
the real fullimage. While it is clear, the panel states that Apply only
compiles.

The progress bar is indeterminate. This build does not report a real
percentage.

If the bootloader is waiting for the button, disconnect USB, hold the
button, connect the cable, and release it. The software does not press the
button.

## Meaning of partial validation OK210

`OK210` means all of the following happened:

- the flash script reported `All done`
- the device reconnected
- the client could talk to it again
- the firmware version matches the checkout

It does **not** mean the Standalone module was confirmed. On the tested
Iceman version, `hw version` and `hw status` do not reliably name the
active module. The row you selected is not proof. A banner string is not
proof that this compile produced that module. `OK200` is reserved for a
laboratory proof, and the application does not emit it.

A failed flash script stays `E300` even if a device is visible afterwards.
A reconnect without `All done` is not a successful flash. An RDV4 that
answers is `OK202` when nothing was written, and `E303` if a write was
refused.

## Firmware cache

Cache entries live in the data folder (`var\cache` in a development tree,
otherwise under `%LOCALAPPDATA%\Proxmark3StandaloneManager\cache`). Each
entry stores `fullimage.elf` and `metadata.json`.

A hit requires the same version, commit, source fingerprint, toolchain,
platform, extras, module, and size. The ELF is hashed again before it is
used, and it is checked again before `pm3-flash-fullimage`. Files larger
than the old skip threshold are included in the fingerprint. Symlinks are
not followed. A metadata mismatch or a hash mismatch discards the entry.

**Recompilar** bypasses the cache on purpose.

## Security and backups

- Nothing is flashed at startup.
- Nothing is flashed because a preference file says so.
- The only flash command is `pm3-flash-fullimage`.
- Before a compile, the current fullimage and the bootrom objects are
  snapshotted. The bootrom tree is put back afterwards so a `make -j` does
  not leave a newly built bootloader as the one on disk. The device's
  bootloader is not programmed.
- `Makefile.platform` backups and the build-session file are in the data
  folder. Restoration refuses a target that is not `Makefile.platform`
  inside a `proxmark3*` checkout.
- Logs redact Windows profile names and values labeled as serial numbers,
  passwords, tokens, or unique IDs. Still read a log before you share it.
- Do not commit `var\`, dumps, or preferences. See `.gitignore`.

Use Standalone mode only with tags you are allowed to copy or emulate.
Unplug USB before relying on standalone behavior. A successful flash is not
a radio test.

## Known limitations

- RDV4 compilation and flashing are not implemented.
- One module, MattyRun, has one laboratory record. The other modules do not.
- `OK210` remains a partial check.
- The bootloader is intentionally left as it was.
- A locally built Windows folder is one-directory so the Qt DLLs are files
  under `_internal`. That layout does not, by itself, meet the LGPL. The
  source repository and the binary package are different things: this
  source tree may be published without those binaries, and
  `DISTRIBUTION-STATUS.txt` still marks the binary package
  `PUBLICATION: BLOCKED` until whoever distributes that package offers the
  corresponding source of the exact Qt and PySide6 binaries. See
  [docs/licensing.md](docs/licensing.md).
- The application does not update Iceman or ProxSpace and does not run on
  macOS or Linux.
- Screenshots are not in the tree. The reason is
  [docs/screenshots/README.md](docs/screenshots/README.md).

## Troubleshooting

Common codes (`E001` missing ProxSpace, `E106` port busy, `E200` compile
failure, `E300` flash not confirmed, `E303` RDV4 or size block, `OK100`
compile only) are explained in
[docs/troubleshooting.md](docs/troubleshooting.md), with the log paths.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Do not send tag dumps, keys, or
device serial numbers. The CI workflow installs dependencies, compiles the
Python package, and runs pytest. It does not flash and it does not assume
ProxSpace is installed on the runner.

## License

The original application code is under the MIT license. Copyright (c) 2026 Anderson A. Justino.
See [LICENSE](LICENSE). That grant does not relicense
Qt, PySide6, or the other components named in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

A Windows executable built from this tree conveys PySide6 and Qt under
LGPL-3.0-only, which is one of the alternatives declared by those wheels.
That executable is not in this repository. What the LGPL requires, and why
the local zip is still not for publication, is in
[docs/licensing.md](docs/licensing.md).

## Credits and references

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
