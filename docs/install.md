# Installation

Public source:

https://github.com/zaureliu/proxmark3-standalone-manager

**Distribution: Source Code Only.** The repository does not contain a
Windows executable, Qt libraries, ProxSpace, or Iceman firmware. Install
Python, clone this source, and run `pm3manager` from a virtual environment.
A PyInstaller build is optional and stays on the computer that builds it.

This application does not install ProxSpace or Iceman, and it does not
update either one because a newer release exists. Both have to be installed
separately before it can compile or flash. Paths below are examples of the
shape the program expects. Use the disk and folder you actually have. Do
not run `runme64.bat` as a setup step for this application. The program
calls `msys2_shell.cmd` itself.

A clone of this repository contains `.pm3manager-root`. Preferences, logs,
`self-check.json`, and the firmware cache then stay in `var\` inside that
clone. `var\` is not part of Git.

## 1. Python

Install Python 3.11 or newer for 64-bit Windows from python.org, including
the `py` launcher and "Add python.exe to PATH" if the installer offers it.
The continuous-integration job uses Python 3.11. The application does not
require a newer minimum. From any directory:

```text
py -3.11 --version
```

No project package should be installed into the global interpreter. The
virtual environment below is the supported runtime.

## 2. ProxSpace

Install ProxSpace from its own project, or locate a copy you already have:

https://github.com/Gator96100/ProxSpace

This repository does not download or extract it. Follow that project's own
instructions. The folder you will select must contain `runme64.bat` and
`msys2\msys2_shell.cmd`. A folder without spaces is easier for the MSYS
tools, for example `C:\Tools\ProxSpace` or `D:\radio\ProxSpace`.

## 3. Iceman checkout

Place a compatible Iceman checkout inside that installation, under `pm3`.
The directory name must be `proxmark3` followed only by letters, digits,
dots, or hyphens. A typical name is `proxmark3-v4.23346`. The official
firmware project is:

https://github.com/RfidResearchGroup/proxmark3

The application reads the version from `common\default_version_pm3.c`. The
third quoted field in that file is a source fingerprint from
`tools\mkversion.sh`, not the Git commit. It does not run `git pull`,
`git fetch`, or `runme64.bat`. `runme64.bat` rewrites the MSYS `fstab` and
`/etc/passwd`, so this program does not use it.

The checkout must contain `Makefile`, `armsrc\Standalone\Makefile.hal`,
`pm3`, and `pm3-flash-fullimage`. The laboratory record used Iceman
v4.23346. Another version may load, but it is not the version this
application was exercised against.

When several checkouts exist, the highest version is selected until you
choose another one in the list.

`make` reads `Makefile.platform` inside the checkout. A file named
`Makefile.platform` directly under `pm3\` is ignored by that build and is
not modified.

## 4. Obtain this source

There is no official executable to download. From the directory where you
want the project:

```text
git clone https://github.com/zaureliu/proxmark3-standalone-manager.git
cd proxmark3-standalone-manager
```

The repository root is the directory that contains `pyproject.toml`,
`requirements.txt`, and `pm3manager`. Run every later command there.

## 5. Virtual environment

```text
py -3.11 -m venv .venv
```

`.venv` is gitignored. Create it again on each computer. Do not copy
someone else's environment, preferences, or firmware cache.

## 6. Dependencies

```text
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` installs PySide6, pyserial, Pillow, PyInstaller, and
pytest into that environment. Pillow and PyInstaller are used only if you
later build a local executable. pytest is used only by the test suite.
Nothing else has to be installed globally.

## 7. Start the application

This command opens the window. It does not flash the device:

```text
.venv\Scripts\python.exe -m pm3manager
```

The same health check, without opening the window and without flashing:

```text
.venv\Scripts\python.exe -m pm3manager --self-check
```

In a clone of this repository the result is `var\self-check.json`.
`"ok": true` means ProxSpace and a checkout were found and the module list
loaded. It does not mean a device was flashed. If ProxSpace is not
installed or not found, the check exits with a failure and the file reports
`E001`. Qt can still have loaded. That is the expected result on a computer
that does not have ProxSpace yet.

If the window starts and ProxSpace was not found, it asks whether you want
to select the folder. Choosing **Não** closes the program without writing
firmware. Choosing **Sim** opens a folder dialog.

## 8. Select the ProxSpace directory

On startup the application looks, in order, at:

1. The folder saved in preferences, if you have selected one.
2. The environment variables `PM3MANAGER_PROXSPACE` or `PROXSPACE`, if set.
   An invalid value is an error. The application does not silently switch
   to another installation.
3. A sibling folder named `ProxSpace` next to the project, then a `ProxSpace`
   folder inside the project, then the current directory.

If nothing is found, use the startup question or **Selecionar ProxSpace**
and choose the folder from step 2, the one that contains `runme64.bat`.
You can change it later with the same button. The selected checkout appears
in the list under that path.

## 9. Detect the Proxmark3

Connect the device by USB after ProxSpace has been selected. Nothing is
flashed because the cable was connected. The device panel shows the COM
port, how confident the USB identification is, and the last hardware
reading. The port number is not fixed. Only the USB IDs listed in the
README are treated as a Proxmark3.

## 10. Verify communication

**Verificar dispositivo** runs `hw version` and `hw status` with the client
already built in the checkout. That button does not flash and does not
consume a pending flash authorization. **Abrir cliente Proxmark3** opens
the official client on the detected port. It does not flash either.

## 11. Select and compile a module

Choose the checkout if more than one is listed. Select a module and read
its description, compatibility, and limits. Confirm external SPI flash only
when the board has it. That checkbox is what adds `PLATFORM_EXTRAS=FLASH`.

**Recompilar** compiles and does not flash. **Aplicar módulo** with the
authorization box clear also compiles and stops at `OK100`. The device
firmware is unchanged.

## 12. Flash only with explicit authorization

Mark **Autorizar gravação real da fullimage no próximo Aplicar módulo**
only when the next **Aplicar módulo** should write the fullimage. Confirm
the dialog once. That operation does not ask again. When it finishes or
fails, the authorization is gone. It is not saved for the next startup.
The only flash command is `pm3-flash-fullimage`. The bootloader is not
updated. RDV4 compilation and flashing are not implemented.

`OK210` after a flash means the script reported success, the device
reconnected, and the firmware version matches the checkout. It does not
prove which Standalone module is active. See the README section "Meaning of
partial validation OK210".

Details of ports, modules, and errors are in [compatibility](compatibility.md)
and [troubleshooting](troubleshooting.md).

## Update monitor

The **Atualizações** panel stays compact. It checks the official Iceman and
ProxSpace repositories and does not change either installation. **Ver
detalhes** opens the dialog with the full fields. **Configurações**, inside
that dialog, can turn the automatic check off or change its period. The
default period is 60 minutes. There is no **Atualizar agora** button. The
check does not need the Proxmark3 to be plugged in. See
[updates](updates.md).

## Tests

From the repository root, with the virtual environment above:

```text
.venv\Scripts\python.exe -m compileall -q pm3manager tests scripts
.venv\Scripts\python.exe -m pytest tests
```

Tests that need a ProxSpace directory next to the project, containing the
`proxmark3-v4.23346` checkout, are skipped when that checkout is absent.
They do not download it. The GitHub Actions job does not have ProxSpace or
a Proxmark3. On that runner the same suite reports the skipped tests
instead of failing.

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

That is where preferences, logs, and the firmware cache go. Do not rely on
`.pm3manager-root` for a copy you give to someone else.

Building that folder does not authorize you to redistribute Qt, PySide6,
Shiboken, or the other libraries it contains. If you redistribute an
executable you built, you must comply with the licenses of PySide6, Qt,
Shiboken, pyserial, PyInstaller, the Microsoft runtime libraries, and any
other component that build includes. The MIT license does not cover them.
See [licensing](licensing.md) and [packaging](packaging.md).

`scripts\install.ps1` is a local developer helper. It runs the tests, builds
the executable, and creates a desktop shortcut. It is not the installation
procedure for this source tree, and it does not publish anything.
