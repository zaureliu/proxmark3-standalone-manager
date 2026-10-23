Proxmark3 Standalone Manager 1.0.0 for Windows x64
===================================================

Extract this whole folder. Do not copy only the .exe file. Start:

    Proxmark3StandaloneManager.exe

The program has no console window. Libraries and Qt plugins are in
`_internal`. Leave them there. Replacing a Qt library is described in
`licenses\PySide6-Qt-NOTICE.txt`. Read that file before replacing anything,
and keep a copy of the folder first.

On a computer that did not build this program, preferences, logs, and the
firmware cache are stored in:

    %LOCALAPPDATA%\Proxmark3StandaloneManager

The application does not need to write that data into this folder. Do not
put ProxSpace, firmware images, or tag dumps into this folder.

ProxSpace is not included. The first window asks for it when it is not
found beside this folder.

This copy is a local validation artifact, not the source publication.
`DISTRIBUTION-STATUS.txt` says `PUBLICATION: BLOCKED` for this binary
folder. Do not publish it. The source repository, when published, does not
include this executable. The MIT license in `LICENSE` covers the original
application only. Qt and PySide6 stay under the terms in `licenses\`.
Redistributing this folder requires compliance with those terms.

A health check that does not open the window and does not flash firmware:

    Proxmark3StandaloneManager.exe --self-check

The result is `self-check.json` in the data folder named above.
