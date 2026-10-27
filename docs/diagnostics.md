# Diagnostics

Version 2.1.0 adds a **Diagnóstico** tab. It is a read-only, consultive
check. It does not certify compatibility, it does not change
`Makefile.platform`, and it does not authorize flashing.

The result is one of:

- Compatible according to the checks that ran
- Partial compatibility
- Confirmation required
- Identified incompatibility
- Not enough information

The window never says "100% compatible". A disconnected device is not
treated as defective. An unknown firmware family is not treated as
incompatible by itself. A dangerous configuration is reported before a
flash, but the existing compile and flash refusals stay in force. The
diagnosis does not loosen them and does not start **Aplicar módulo** or
**Recompilar**.

## What is read

When you press **Executar diagnóstico** and a Proxmark3 is selected, the
official client may run only:

- `hw version`
- `hw status`
- `hw ping`

Those three were checked in `client/src/cmdhw.c` of the local Iceman
v4.23346 tree. `hw ping` is sent with no `--len`. The diagnosis does not
run `hw bootloader`, `hw reset`, `hw readmem`, `hw tearoff`, `hw tia`, any
`lf` or `hf` command, `git pull`, `git fetch`, `git checkout`, `git reset`,
or `make`. It does not scan RFID tags. **Atualizar informações** reads the
local environment again and does not open the client, and it does not reuse
an older client answer as a new detection.

USB enumeration still supplies the COM port, VID/PID, and the USB text.
That text is not a confirmed board model. `LED_ORDER=PM3EASY` means the
build selects AT91SAM7S support. It does not mean the connected board is an
Easy, and a Makefile assignment is not treated as a part that was measured.

## Provenance

Every technical line has an origin:

| Origin | Meaning |
| --- | --- |
| Detected | Read from the device or from a file that is present. |
| Configured | Declared in `Makefile.platform` or in a saved preference. |
| Documented | Taken from an identifiable source file or platform rule. |
| Inferred | A conclusion from partial evidence. |
| Not verified | The check did not confirm it. |
| Unavailable | The check could not be performed. |

"MCU configured: AT91SAM7S512" is not "physical MCU confirmed". A value
stored in preferences is not updated by the diagnosis, and the firmware
cache is not updated either. The in-memory report is tied to the port,
VID/PID, selected module, Git commit, and version token. The USB serial
number is not part of that key. If the device or the module changes, the
previous report is marked stale. It is not reused as proof of the new
device.

## Automatic identification

Version 2.2.0 can build a hardware profile from the USB hint plus a
diagnosis that is still valid for the same port, VID, and PID. The USB
serial is not part of the context key and is not copied into the profile
evidence. The profile does not write `detected_*` preferences. **Verificar
dispositivo** still does. A new diagnosis feeds the profile without opening
the port a second time. If a compile or a flash holds the operation lock,
the automatic client read waits. It does not cancel that operation and it
does not start one. See [device compatibility](device-compatibility.md).

## Safety

The client runs off the Qt thread, with a timeout, a cancel button, and a
single diagnostics owner on the existing operation lock. A compile or a
flash that already holds the lock is not interrupted. If the COM port is
busy, the diagnosis says so and does not open it again. Closing the window
cancels a running diagnosis and waits for the child process. Closing is
still refused while a compile or a flash is running.

## Export

**Copiar resumo** and **Exportar relatório** write JSON or plain text.
The file includes the time, the application version, the checkout version
when it was read, the origin of each fact, the checks, the limits, and the
module verdict. Paths under a home directory, e-mail addresses, tokens,
serial numbers, processor unique IDs, flash unique IDs in either byte
order, and lines that look like a card UID or a dump are redacted. The
client answer is cleaned before it becomes a fact, a check, or the
technical section. A timed-out or cancelled reading does not keep a partial
client answer in that section. The report is not a certificate.

## Version suffix `-suspect`

A client, firmware, or bootrom line may end in `-suspect` or `-unclean`.
In the Iceman v4.23346 sources this check was compared with,
`include/common.h` documents the `clean` flag as 1 when the tree was clean,
0 when it was unclean, and 2 when that state could not be determined.
`common/commonutil.c` appends `-unclean` for 0 and `-suspect` for 2.
`tools/mkversion.sh` starts that flag at 2 and records 0 or 1 only when
the script is invoked with `--undecided` and git is available.

`-suspect` means the recorded flag was 2. By itself it does not prove a
dirty tree, a failed flash, a hardware fault, or a modified image. The
diagnosis copies the version text and does not invent a cause. It does not
strip the suffix, and it does not update or reflash the device to remove it.

## Limits

Not every hardware variant returns the same lines. Missing bootrom text,
missing MCU text, or an unnamed firmware family stays "Não identificado" or
"Não verificado". External SPI flash is "present" only when the client says
so. A module that requires `WITH_FLASH` stays "confirmation required" until
that line is present, and the SPI checkbox in **Operações** is still
required before compilation. RDV4 text from the client, or a module the
catalog already marks incompatible, stays blocked.
