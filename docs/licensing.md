# Licensing

This is a technical record of the license choice and of the Windows package
inspected for version 1.0.0. It is not legal advice.

The copyright holder of the original application is Anderson A. Justino.
The year in the MIT notice is 2026.

## Original code

`LICENSE` is the MIT license. It applies to the Python package, tests,
scripts, icon generator, documentation, and the generated icon, to the
extent the copyright holder has the rights to license that material.

It does not apply to Qt, PySide6, Shiboken6, pyserial, PyInstaller, the
Microsoft runtime libraries, the Iceman firmware, or ProxSpace. Those stay
under their own terms. Nothing in this tree was copied from the Iceman
firmware or from ProxSpace. The icon is generated artwork, not a Proxmark
or Qt logo. `catalog/modulos.json`, when a development machine creates it,
repeats short descriptions from the firmware checkout and is ignored by
Git. It is not part of the MIT grant and it is not put in the zip.

A search of `pm3manager` for a firmware copyright header, an SPDX tag, or
the RfidResearchGroup name found none. That search is repeated by the test
suite. It is not a promise that every future edit will stay that way.

## Choice for PySide6 and Qt

Inspected packages: PySide6 6.12.0 and shiboken6 6.12.0.

Their metadata declares:

```text
License: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only
```

For the libraries conveyed in the Windows build, the distributor selects
**LGPL-3.0-only**. That selection does not put the original application
under the LGPL or the GPL, and it does not create a commercial Qt license.
No commercial Qt agreement is part of this project. The file
`LicenseRef-Qt-Commercial.txt` inside the wheel metadata does not apply
and is not shipped as the license of this build.

The wheels do not contain the GPL or LGPL texts. The build copies
`licenses/GPL-3.0.txt` and `licenses/LGPL-3.0.txt` next to the executable
because LGPL-3.0 is additional permissions on top of GPL-3.0, and both
texts have to accompany the combined work.

## One-directory layout

`Proxmark3StandaloneManager.spec` builds a windowed one-directory folder:

```text
dist\Proxmark3StandaloneManager\Proxmark3StandaloneManager.exe
dist\Proxmark3StandaloneManager\_internal\
```

`upx=False`. Qt6Core, Qt6Gui, Qt6Widgets, Shiboken, PySide6, and the Qt
plugins that PyInstaller collects are files in that folder, not members of
a one-file archive. The procedure for replacing them, and the limits of
that procedure, are in `licenses/PySide6-Qt-NOTICE.txt`.

Putting the DLLs on disk does not, by itself, satisfy the LGPL. In
particular:

- LGPL-3.0 section 4 requires a prominent notice, the GPL and LGPL texts,
  and either a relinkable form of the application or a suitable shared
  library mechanism. This package provides separate DLLs and documents
  in-place replacement. It does not provide object files and a link script.
  Section 4(d)(1), read narrowly, expects a library already present on the
  user's system. This build ships its own copy. Replacement of that copy
  is possible. That fact is not the whole obligation.
- The PyInstaller Qt hook installs `qt.conf` in memory. A recipient cannot
  edit it. In-place replacement inside `_internal` still works. A modified
  Qt that needs a different plugin prefix cannot be redirected without
  rebuilding the executable.
- Conveying the Qt DLLs also conveys the library. The corresponding source
  of that exact version, including any modifications, still has to be
  offered. This project makes no modifications. The archives that match the
  version numbers, and the reason a generic Qt website link is not enough,
  are in [corresponding-source.md](corresponding-source.md).

A test that renames `Qt6Core.dll` and restores the same bytes shows that
the file on disk is the one the process needs. It does not show that a
rebuilt, modified Qt loads. Do not describe that test as LGPL compliance.

## Other dependencies

- pyserial 3.5 is BSD-3-Clause. Copyright (c) 2001-2020 Chris Liechti.
  The text is `licenses/BSD-3-Clause-pyserial.txt`. The application uses it
  to enumerate COM ports. The Windows build includes the package.
- Pillow 13.0.0 is MIT-CMU and is used only while drawing the icon. The
  icon file is original output. The executable does not import Pillow.
  Do not describe the icon as Pillow's work.
- PyInstaller 6.22.3 is GPL-2.0-or-later with the bootloader exception in
  `licenses/PyInstaller-COPYING.txt`. Embedding the unmodified bootloader
  does not, by that exception, place the application under the GPL. The
  exception does not cover a modified bootloader. Runtime hooks and the
  runtime-hook utilities are Apache-2.0. The Apache text is
  `licenses/Apache-2.0.txt`.
- pytest is MIT and stays in the development environment. It is not in the
  executable.
- The Microsoft Visual C++ runtime DLLs follow Microsoft's redistribution
  terms. See `licenses/MICROSOFT-RUNTIME.txt`. The wheel does not include
  Microsoft's own license document. This project does not invent one.

## Firmware and ProxSpace

The application invokes whatever Iceman checkout the user selects. It does
not copy that firmware into this repository. The RfidResearchGroup firmware
is their project. This application is not theirs and does not own the
Proxmark name.

ProxSpace is an external Windows environment:
https://github.com/Gator96100/ProxSpace. That repository was archived by
its owner on 10 September 2026. A ProxSpace download can contain many other
programs. Their licenses bind that bundle, not this executable, as long as
this executable does not copy them.

## Publication

Two states are recorded on purpose.

The source repository may be published as source code only. That tree
contains the original application, its tests, its documentation, and the
scripts a user needs in order to install dependencies and compile. It does
not contain Qt, PySide6, Shiboken, or firmware binaries. Publishing that
source is not an official redistribution of Qt, Iceman, ProxSpace, or
PySide6, and the MIT license does not cover those projects.

The binary package is a different state. `DISTRIBUTION-STATUS.txt` says
`PUBLICATION: BLOCKED` for that package. The MIT license is in place for
the original code. A locally built Windows folder is one-directory, the
LGPL and GPL texts are staged into it, and replacement of the Qt DLLs is
documented. The corresponding source is not yet offered to recipients, and
the wheel has not been shown to match the public source archives byte for
byte. Until those gaps are closed by the person who would distribute the
binary, the zip is a local validation artifact. Do not upload it.

Anyone who builds an executable and gives it to other people must comply
with the licenses of the dependencies included in that build. This
repository does not make that compliance automatic.

See also [packaging.md](packaging.md) and
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
