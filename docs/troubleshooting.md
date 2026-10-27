# Troubleshooting

Logs are the first place to look. **Visualizar logs** opens the operational
log. When you run from this source tree that file is `var\logs\app.log`.
For a locally built executable copied out of the development tree it is
under `%LOCALAPPDATA%\Proxmark3StandaloneManager\logs\`. The published tree
does not include either log.
Build and flash transcripts are separate files in the same logs folder.
`operations.jsonl` is the structured history. Test runs do not write the
operational log.

The window has no console. `--self-check` writes `self-check.json` beside
the preferences and returns without flashing.

## Messages you can act on

| Code | What it means | What to do |
| --- | --- | --- |
| `E001` | ProxSpace was not found, or the saved folder is no longer valid. | Select the folder that contains `runme64.bat` and `msys2\msys2_shell.cmd`. A bad saved path is not replaced automatically. |
| `E002` | The checkout has no readable firmware version. | Point at a complete Iceman checkout under `pm3\`. |
| `E010` | A compile or flash is already running. | Wait. Closing the window is blocked during that operation. |
| `E103` | The client could not confirm communication, or the reported version does not match the checkout. | Check the USB cable and that no other program has the COM port. This is not an RDV4 block. |
| `E104` / `E105` | The module is incompatible or its extra requirements were not confirmed. | Choose another module, or confirm SPI flash / uncertain requirements when the panel says that is the reason. |
| `E106` | The known COM port is in use. | Close the Proxmark client or any other serial program and try again. Other open failures do not use this block. |
| `E200` | `make` failed. | Open `logs\build-<module>.log`. The checkout's `Makefile.platform` is restored. The device is not flashed. |
| `E300` | The flash command did not end in a confirmed write. A later reconnect is not proof. | Do not assume the new image is active. Read `logs\flash-<module>.log`. Authorization is cleared. |
| `E303` | Compile or flash was refused. The device was identified as RDV4 or PM5, the identification is contradictory, or the internal flash size does not match the image. | Leave the official firmware in place. This application has no RDV4 or PM5 image. A PM3GENERIC image is not sent to either one. |
| `E400` | Unexpected failure. | Read the technical detail in the log. |
| `OK100` | Compile finished, or the cache was reused. If flashing was not authorized, the device was not written. | This is the expected result of **Recompilar** and of **Aplicar módulo** with the flash box clear. |
| `OK202` | Communication worked and the firmware identifies itself as RDV4. | Diagnosis only. The PM3GENERIC image was not written. |
| `OK210` | Partial validation after a flash. See the README. | The module was not identified by `hw version` / `hw status`. |
| `OK000` | Self-check finished and a checkout was loaded. | Not a hardware test. |

`OK200` is reserved for a laboratory proof the application itself does not
perform. You should not see it from the current buttons.

## Diagnostics

The **Diagnóstico** tab is consultive. **Desconectado** means no Proxmark3
was selected for that reading. It does not mean the device is defective.
**Porta COM ocupada** means another program already has the port. Close
that program. The diagnosis does not force the port open. A missing
bootrom line or an unnamed firmware family stays unverified. It is not an
automatic incompatibility. If a compile or a flash is running, the
diagnosis refuses to start and does not cancel that operation.

The exported report redacts home-directory paths, e-mail addresses, tokens,
USB serial numbers, processor unique IDs, flash unique IDs, and lines that
look like a card UID or a dump. It is not a certificate. A version suffix
`-suspect` is not treated as a proved cause, and the diagnosis does not
flash the device to remove it. See [diagnostics](diagnostics.md).

**Ver manual do módulo** only opens the offline card. If a module from a
newer checkout has no reviewed card, the manual says **Sem revisão**
instead of inventing LEDs or buttons. See [module guide](module-guide.md).

## Device identification and module marks

The line under **Dispositivo** is a summary. The tooltip has the confidence,
firmware, and configured platform. **Ver diagnóstico completo** opens the
existing diagnosis tab. It does not flash.

A module mark is an icon plus text. It is not a certificate. **Todos**
always returns the full list. If the selected module disappears from a
narrower filter, the list says so and does not pretend the module is still
selected.

These notices are one line, with the reason in the module details:

- The device was not identified with confidence, or the client lines
  contradict each other. No commercial model is chosen. Compile and flash
  stay blocked when the lines conflict.
- The mode needs SPI flash and the reading did not confirm it. Confirm the
  checkbox only when the board has that memory. The checkbox is still
  required before compilation even if the reading already says SPI is
  present.
- The mode is incompatible with the PM3GENERIC catalog on this installation,
  or it is marked RDV4-only and the connected device was not identified as
  RDV4.
- Standalone is unavailable on the PM5 firmware that was analyzed. The 41
  PM3 identifiers in the catalog are not PM5 support.
- `Makefile.platform` names a different family from the identified hardware.
  The file is not rewritten to match the device.
- The selected checkout does not contain the mode, or its `Makefile.hal`
  could not be read safely. Nothing is unlocked because the parse failed.
- The installed firmware version and the local checkout are not proved to
  be the same revision. That warning does not change the detected model.

An evaluation from a previous device is marked stale and is not reused.
See [device compatibility](device-compatibility.md).

## Update monitor

**Não foi possível consultar o GitHub.** means the live request failed.
If a previous result exists, the panel also says **Exibindo resultado da
última verificação.** Those lines are the last successful check, not a new
one. **Repositório ProxSpace arquivado.** means GitHub reports the official
ProxSpace repository as archived. It does not mean the local folder is
broken. **Compatibilidade da atualização não verificada.** means a release
was seen and was not tested against this board.

The monitor never flashes and never runs `git pull`. A repeated notice for
the same release is not shown again. **Ver detalhes** opens the dialog that
contains **Configurações**. That is where the schedule can be turned off.
The interval is stored as `updates_interval_minutes` in the preferences
file. Details are in `docs/updates.md`.

## Bootloader button

If the device waits for the button, disconnect USB, hold the button,
connect the cable, and release the button. The application does not press
the button and does not treat a disappearing COM port during that step as
a finished failure by itself.

## Compile uses the wrong platform

Confirm the active checkout in the window. The file that matters is
`Makefile.platform` in that checkout. After a failed or interrupted build
the next startup restores it from `var\backups` (or the equivalent data
folder) and does not flash. A session that was intentionally kept is not
restored.

## The flash box came back on

It should not. Startup forces it off, including when an older
`preferences.json` still contains `"flash_autorizado": true`. That file is
rewritten with the flag false and the other fields kept. If a future build
enables flashing without the dialog, treat that as a defect.

## Cache looks stale

**Recompilar** ignores the cache. A cache hit requires the same firmware
version, commit, source fingerprint, toolchain, platform, extras, module,
and size, plus a matching SHA-256 of the ELF. Symlinks that escape the
cache entry are rejected.
