# Automatic identification and dynamic compatibility

Version 2.2.0 adds two consultive layers on top of the V2.1 protections.
Neither layer starts a build or a flash. Neither layer rewrites
`PLATFORM`, `PLATFORM_EXTRAS`, `LED_ORDER`, or `STANDALONE`.

Version 2.2.0 is the source published on `main`. The annotated tag
`v2.2.0` identifies that publication. The tags `v1.0.0`, `v2.0.0`, and
`v2.1.0` stay where they are. There is no GitHub Release. The binary
package stays `PUBLICATION: BLOCKED`.

## What is identified

The application keeps these facts separate:

| Fact | Meaning |
| --- | --- |
| Physical model | RDV4, PM5, or not confirmed. A commercial name is chosen only from combined client evidence. |
| Detected family | PM3, PM5, or unknown. |
| Configured platform | The `PLATFORM` value read from `Makefile.platform`. It is not a measurement of the board. |
| Reported firmware | The family string parsed from the client, such as `PM3 GENERIC`, `RDV4`, or `PM5`. |
| Confirmed resources | SPI flash, smartcard, and Bluetooth only when the safe client text says present or absent. |

`LED_ORDER=PM3EASY` selects AT91SAM7S support in the Iceman makefiles. It
does not identify a Proxmark3 Easy. `PLATFORM=PM3GENERIC` does not identify
the connected board as a generic commercial model. A saved preference never
raises an identification to confirmed.

## How a device is recognized

On startup, and when the COM port or the selected device changes, the
existing USB detector runs. Known VID/PID pairs (`9AC4:4B8F`, `2D2D:504D`,
`502D:502D`) are a family hint only. `502D:502D` is not treated as an Easy.
A USB name that contains "RDV4" or "Easy" is recorded as a hint and is not
enough to select that model.

When a fresh diagnosis or a safe client reading is available, the profile
uses only `hw version`, `hw status`, and `hw ping`. `hw tune` is not run.
The antenna cross-check that can print a firmware/board mismatch lives in
`hw tune`; if that warning text is already present in captured output it is
treated as a conflict, not as a new command.

Recognition order in the client text is PM5, then RDV4, then PM3 GENERIC.
`Target.... GENERIC` on the RDV4 firmware path is the generic signature of
that firmware. It is not `PM3 GENERIC`, the model stays unknown, and
compile and flash are blocked. Two agreeing RDV4 signals (Target and the
firmware line) confirm RDV4. One signal is only probable. Two agreeing PM5
signals (for example Target PM5 plus the AT32F437 line, or the Proxmark5
banner) confirm PM5. One signal is probable. Contradictory Target lines do
not select a model.

The active reading runs off the Qt thread, with a timeout, cancellation,
USB debounce, and one identification at a time. The existing operation lock
is respected. A compile, a flash, or a busy COM port defers the client
read. Removing the device during the reading discards the result. A
cancelled or timed-out reading discards partial client text, including any
unique identifier that might have been in that fragment. The cache key is
the selected device plus the checkout token. A result is never applied to
another device. Switching devices clears a pending flash authorization.
That authorization is still never stored as true.

## Confidence

| State | When it is used |
| --- | --- |
| Confirmed | At least two agreeing client signals for RDV4 or PM5. A version mismatch with the checkout does not lower this. |
| Probable | One client signal, without a contradiction. |
| Known family, model not confirmed | PM3 GENERIC, or a known Proxmark VID/PID without a commercial model. External SPI does not turn this into Easy or RDV4. |
| Inconclusive | Medium USB confidence, contradictory lines, or `Target GENERIC`. No model is selected. |
| Not identified | No device, or no Proxmark evidence. |

Each state keeps the evidence lines that produced it. Old preferences are
listed as ignored. They cannot promote a state to confirmed.

## Three compatibility levels

For each Standalone module the engine records three answers, plus one
overall label. The overall label is never "100% compatible".

**A. Hardware.** Does the connected device show the physical resources this
mode requires? SPI present, absent, and unknown stay different. Unknown SPI
is confirmation required. Absent SPI is incompatible. Present SPI can
satisfy the hardware check, and the SPI checkbox in the window is still
required before compilation.

**B. Checkout and firmware.** Does the selected Iceman tree list the mode,
and do its platform rules allow it? A mode missing from `STANDALONE_MODES`
is unavailable. On the analyzed v4.23346 tree, `armsrc/appmain.c` keeps
`RunMod()` behind a PM5 block. Every PM3 module is then unavailable on that
PM5 firmware. The catalog IDs are not treated as PM5 support.

**C. Operational support in this application.** PM3GENERIC keeps the
existing compile and flash pipeline. RDV4 is consultive: the technical
summary can be favorable and the pipeline stays blocked. PM5 is consultive
and experimental: it does not reuse the PM3 client interpreter, hardware
commands, or flash pipeline, and compile and flash stay blocked.

A favorable RDV4 summary says that technical compatibility may be favorable
and that compilation and flashing are unavailable in this application.
That module is not in the "recommended" filter.

## Where the rules come from

The engine reads `armsrc/Standalone/Makefile.hal` and, for the PM5 limit,
`armsrc/appmain.c`. It does not run `make`, `git pull`, or any command that
edits the checkout.

`STANDALONE_MODES` must be a `:=` list followed only by `+=` continuations.
`STANDALONE_MODES_REQ_FLASH`, `STANDALONE_MODES_REQ_BT`, and
`STANDALONE_MODES_REQ_SMARTCARD` must each be one simple `:=` assignment.
An unknown requirement name, `+=` on a requirement line, a repeated
requirement, or a token that is not in `STANDALONE_MODES` marks the whole
analysis incomplete. An empty smartcard list is valid. An incomplete
analysis cannot be reported as compatible. RDV4-only rows come from the
existing `KNOWN_STANDALONE_DEFINITIONS` table. If that table cannot be
read, the analysis is incomplete.

## Precedence

1. Capabilities proved by the hardware reading.
2. Restrictions proved by the selected Iceman checkout.
3. Existing platform rules and flash protections.
4. Reviewed catalog metadata.
5. Documented fields of the interactive manual.
6. Inferences and incomplete information.

The manual cannot override a Makefile restriction. An inferred manual field
is not a confirmed physical requirement. A documented manual flag that
disagrees with the Makefile is a conflict: a result that would have been
compatible becomes confirmation required, and the Makefile restriction
remains the one that blocks. If the reviewed catalog still marks a mode
uncertain, a compatible-looking result is lowered to confirmation required.
`can_apply` is unchanged: incompatible modes stay blocked, SPI-required
modes stay blocked until the checkbox, and uncertain modes stay blocked
until that confirmation. Parse failures do not unlock a blocked operation.

## Filters and notices

The module list can show modules recommended for this device, compatible
ones, those that need confirmation, incompatible ones, or all of them.
Icons and text are both shown. The default remains the full list. After a
reliable client or diagnosis reading, the list may start on the compatible
filter once. **Todos** stays available, and a module the user already
selected is kept when it is still visible. Changing only the filter does
not open the COM port again.

The device line on **Operações** is one line, for example
"Dispositivo: Proxmark3 | Família: PM3 | Modelo: não confirmado" or
"Dispositivo: Proxmark3 RDV4 | Identificação confirmada". Firmware,
platform, and confidence are in the tooltip. **Ver diagnóstico completo**
opens the existing **Diagnóstico** tab.

Notices are a single line, not a popup. They cover an uncertain
identification, unconfirmed SPI, a PM3GENERIC incompatibility, an RDV4-only
mode, Standalone unavailable on the analyzed PM5 firmware, a platform that
disagrees with the identified hardware, a checkout that does not contain
the mode, and a firmware version that is not proved to match the local
checkout. The same notice is not repeated.

## Limits

RDV4 and PM5 compilation and flashing are not implemented. A PM5 reading
must not be given a PM3 image. A PM3GENERIC image must not be given to an
RDV4. An inconclusive or contradictory identification blocks the PM3GENERIC
pipeline. No physical RDV4 or PM5 was required for the automated tests.
A live PM3-family reading, when a board is connected, confirms only what
the safe commands actually returned.
