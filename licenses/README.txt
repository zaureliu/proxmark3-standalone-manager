License texts shipped with Proxmark3 Standalone Manager
=======================================================

The MIT text applies only to original material of Proxmark3 Standalone
Manager for which the copyright holder, Anderson A. Justino, has the rights
to grant that license. It does not relicense Qt, PySide6, Shiboken6,
pyserial, PyInstaller, the Microsoft runtime libraries, the Iceman firmware,
or ProxSpace.

Files in this directory:

- MIT.txt
    Official MIT license for the original application code.
- GPL-3.0.txt
    GNU General Public License, version 3. Required alongside the LGPL
    because LGPL-3.0 is written as additional permissions on top of GPL-3.0.
- LGPL-3.0.txt
    GNU Lesser General Public License, version 3. This is the license
    selected by the distributor, among the three alternatives declared by
    PySide6 6.12.0 and shiboken6 6.12.0, for the Qt, PySide6, and Shiboken
    libraries conveyed with the Windows build.
- PySide6-Qt-NOTICE.txt
    Which Qt and PySide6 components are conveyed, how they are linked, and
    how to replace the shared libraries. Read this with
    CORRESPONDING-SOURCE.md. Presence of the DLLs is not, by itself,
    compliance with the LGPL.
- BSD-3-Clause-pyserial.txt
    License of pyserial 3.5. Copyright (c) 2001-2020 Chris Liechti.
- PyInstaller-COPYING.txt
    PyInstaller 6.22.3 terms, including the bootloader exception and the
    Apache-2.0 grant for runtime hooks. The exception applies only to the
    unmodified bootloader.
- Apache-2.0.txt
    Apache License 2.0, for the PyInstaller runtime hooks and runtime
    modules that the exception text identifies.
- MICROSOFT-RUNTIME.txt
    Notice for the Visual C++ runtime DLLs. Those DLLs are not MIT and not
    LGPL. The wheel does not include Microsoft's own license document.

DISTRIBUTION-STATUS.txt separates the source repository from a built
folder. The source may be published without binaries. A local validation
build remains `PUBLICATION: BLOCKED` and is not a public release. Anyone
who redistributes their own executable must still comply with the licenses
in this directory.
