# Corresponding source for Qt and PySide6

This file identifies the source that has to travel with, or be offered for,
the Qt and PySide6 libraries in the Windows build. It is not legal advice.
A link on this page is an identifier. It is not, by itself, the written
offer or the copy the distributor must give to recipients.

The application does not modify Qt, PySide6, or Shiboken.

## What the binary actually is

The inspected build uses the PyPI wheels:

| Wheel | Version | License declared by the wheel |
| --- | --- | --- |
| PySide6 | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| shiboken6 | 6.12.0 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |

`Qt6Core.dll` from that PySide6 wheel reports file version 6.12.0.0.
The distributor selects LGPL-3.0-only for those conveyed libraries. See
`licenses/PySide6-Qt-NOTICE.txt`.

The wheel metadata does not include the LGPL or GPL text, and it does not
include the Qt or PySide6 source. Installing PySide6 from PyPI does not
place the corresponding source on the machine.

## Source archives that match the version number

These are the official source archives for the same version numbers.
The SHA-256 values are the ones published by the Qt project for those
file names. They identify the archive. They do not prove that the wheel's
DLLs were built from that archive without a private patch.

| File | Size in bytes | SHA-256 |
| --- | --- | --- |
| `qt-everywhere-src-6.12.0.tar.xz` | 443394020 | `98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165` |
| `pyside-setup-everywhere-src-6.12.0.tar.xz` | 18211772 | `099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751` |

The Qt archive is the source of the Qt libraries. The PySide archive is
the source of the bindings and of Shiboken. Both are required. Qt's
third-party license notices are inside the Qt archive, under the `LICENSES`
directories of the modules, not in a single file that the wheel ships.

A build machine may keep verified copies in the gitignored directory
`third-party-source/`. That directory is not part of the application zip
and not part of the source tree that Git would track. `scripts/fetch_corresponding_source.ps1`
downloads the two archives from the Qt project's own download host and
checks the SHA-256 values above. A failed check deletes the file.

## What does not satisfy the obligation

- Publishing the MIT source of Proxmark3 Standalone Manager.
- Pointing at `https://qt.io`, `https://download.qt.io`, or the Qt Git
  repository without the distributor remaining responsible for the exact
  source, including modifications, for the period the license requires.
- Shipping `licenses/LGPL-3.0.txt` without the library source.
- Telling the user to run `pip install PySide6`. The wheel is the binary,
  not the corresponding source.
- A copy that exists only on the computer that built the executable, if
  recipients of the executable cannot obtain it from the distributor.

GPL-3.0 section 6, which LGPL-3.0 uses for conveying the library, allows a
written offer or a network server. If the source is on a server the
distributor does not control, the distributor is still responsible for
keeping that exact source available. A third-party URL can change or
disappear. This project therefore does not treat the Qt download site as
automatic compliance.

## What the distributor still has to do before publication

1. Keep the two archives, after a SHA-256 check, in a place the distributor
   controls.
2. If the wheel is ever shown to differ from those archives, keep that
   difference as well. The corresponding source is the source of the
   binaries that were conveyed, not a similar upstream tag.
3. Give every recipient of the Windows build either a copy of that source
   or a written offer that meets GPL-3.0 section 6, for at least three
   years and for as long as replacement copies of the binary are offered.
   The offer has to name a way to obtain the source that the distributor
   can still honor. Physical media at cost is one of the license's options.
   A sentence in a README that says "see qt.io" is not.
4. Include any later modification the distributor makes. None are made today.
5. Leave the Qt and PySide6 copyright notices and the LGPL and GPL texts
   with the binary. The `licenses` directory is how this build does that.

Until those steps are true for recipients of a binary, `DISTRIBUTION-STATUS.txt`
stays `PUBLICATION: BLOCKED` for that binary package. Do not upload the zip.
Publishing the Standalone Manager source, which does not contain these
archives or the Qt binaries, is not that offer and is not a redistribution
of Qt.

## Replacement is a different duty

`docs/licensing.md` and `licenses/PySide6-Qt-NOTICE.txt` describe how a
recipient can exchange the Qt DLLs that sit in `_internal`. Being able to
exchange a file is not a substitute for conveying the corresponding source.
Both duties apply to this build. Neither is discharged by the other.
