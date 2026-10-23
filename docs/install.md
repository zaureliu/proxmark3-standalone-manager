# Installation

**Distribution: Source Code Only.** The public tree does not contain a
Windows executable. Install Python, obtain this source, and run
`pm3manager` from a virtual environment. A PyInstaller build is optional
and stays on the computer that builds it.

The application does not contain Proxmark firmware and does not install
ProxSpace. Both have to exist before it can compile or flash. Paths below
are examples. Use the disk and folder you actually have. Do not run
`runme64.bat` as a setup step for this application. The program calls
`msys2_shell.cmd` itself.

## 1. Python

Install Python 3.11 or newer for 64-bit Windows, including the `py`
launcher. The continuous-integration job uses Python 3.11. From any
directory:

```text
py -3.11 --version
```

## 2. ProxSpace and the firmware checkout

Install ProxSpace from its own project, or locate a copy you already have:
https://github.com/Gator96100/ProxSpace.

Extract it to a folder without spaces, for example `C:\Tools\ProxSpace` or
`D:\radio\ProxSpace`. The folder must contain `runme64.bat` and
`msys2\msys2_shell.cmd`.

Inside that installation, the Iceman checkout must be a directory under
`pm3` whose name matches `proxmark3` plus letters, digits, dots, or hyphens.
A typical name is `proxmark3-v4.23346`. The application reads the version
from `common\default_version_pm3.c`. It does not update git and it does not
run `runme64.bat` on every command, because that setup rewrites the MSYS
`fstab` and `/etc/passwd`.

When several checkouts exist, the highest version is selected until you
choose another one in the list.

The `make` program reads `Makefile.platform` inside the checkout. A file
named `Makefile.platform` directly under `pm3\` is ignored by that build and
is not modified.

The laboratory validation used Iceman v4.23346. Another version may load,
but it is not the version this application was exercised against.

## 3. Obtain the Standalone Manager source

Use a checkout of this repository. The intended public name is
`proxmark3-standalone-manager`. This document does not point at a remote
that has not been created. There is no official executable to download.

Open a terminal in the repository root. That directory contains
`pyproject.toml`, `requirements.txt`, and `pm3manager`.

## 4. Create the virtual environment

```text
py -3.11 -m venv .venv
```

## 5. Install the dependencies

```text
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` installs PySide6, pyserial, Pillow, PyInstaller, and
pytest. Pillow and PyInstaller are used only if you later build a local
executable. pytest is used only by the test suite.

## 6. Run the application from Python

```text
.venv\Scripts\python.exe -m pm3manager
```

The same health check, without opening the window and without flashing:

```text
.venv\Scripts\python.exe -m pm3manager --self-check
```

In this development tree the result is `var\self-check.json`. `"ok": true`
means ProxSpace and a checkout were found and the module list loaded. It
does not mean a device was flashed.

## 7. Select the ProxSpace installation

On startup the application looks, in order, at:

1. The folder saved in preferences, if you have selected one.
2. The environment variables `PM3MANAGER_PROXSPACE` or `PROXSPACE`, if set.
   An invalid value is an error. The application does not silently switch
   to another installation.
3. A sibling folder named `ProxSpace` next to the project, then a `ProxSpace`
   folder inside the project, then the current directory.

If nothing is found, the window asks you to select the ProxSpace folder.
You can change it later with **Selecionar ProxSpace**. The selected checkout
appears in the list under that path.

## 8. Connect the Proxmark3

Connect the device by USB after ProxSpace has been selected. Nothing is
flashed because the cable was connected.

## 9. Verify the COM port

The device panel shows the port, how confident the USB identification is,
and the last hardware reading. The port number is not fixed. **Verificar
dispositivo** runs `hw version` and `hw status` with the client already
built in the checkout. That button does not flash and does not consume a
pending flash authorization.

## 10. Select the Standalone module

Choose the checkout if more than one is listed. Select a module and read
its compatibility and limits. Confirm the external SPI flash only if the
hardware has it. The tested board did. The checkbox is what adds
`PLATFORM_EXTRAS=FLASH`.

## 11. Compile, and flash only with authorization

Use **Recompilar** or **Aplicar módulo** while the flash box is clear when
you only want a build. That result is `OK100` when the build succeeds. The
device firmware is unchanged.

Mark **Autorizar gravação real da fullimage no próximo Aplicar módulo**
only when the next **Aplicar módulo** should write the fullimage. Confirm
the dialog once. That operation does not ask again. When it finishes or
fails, the authorization is gone. The only flash command is
`pm3-flash-fullimage`.

Details of ports, modules, and errors are in `docs/compatibility.md` and
`docs/troubleshooting.md`.

## 12. Update monitor

The **Atualizações** section checks the official Iceman and ProxSpace
repositories and does not change either installation. The default period is
60 minutes. Turn it off, or change the period, with **Configurações** in
that section. The behavior, the cache, and the decision not to apply updates
are described in `docs/updates.md`. The check does not need the Proxmark3
to be plugged in.

## Optional: build a one-directory executable locally

This is not part of the source publication. On the same computer:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

The output is `dist\Proxmark3StandaloneManager\Proxmark3StandaloneManager.exe`
plus `_internal`. `dist\` is gitignored. `DISTRIBUTION-STATUS.txt` in the
repository marks that binary package `PUBLICATION: BLOCKED`.

A copy of the folder that is not sitting in a development tree uses:

```text
%LOCALAPPDATA%\Proxmark3StandaloneManager
```

That is where preferences, logs, and the firmware cache go. The development
tree keeps those files in `var\` because the tree contains the marker
`.pm3manager-root`. Do not rely on that marker for a copy you give to
someone else.

If you redistribute an executable you built, you must comply with the
licenses of PySide6, Qt, Shiboken, pyserial, PyInstaller, the Microsoft
runtime libraries, and any other component that build includes. The MIT
license does not cover them. See `docs/licensing.md` and
`docs/packaging.md`.

`scripts\install.ps1` is a local developer helper. It runs the tests, builds
the executable, and creates a desktop shortcut. It is not the installation
procedure for this source tree, and it does not publish anything.
