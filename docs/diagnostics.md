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
serial numbers, flash unique IDs, and lines that look like a card UID or a
dump are redacted. The report is not a certificate.

## Limits

Not every hardware variant returns the same lines. Missing bootrom text,
missing MCU text, or an unnamed firmware family stays "Não identificado" or
"Não verificado". External SPI flash is "present" only when the client says
so. A module that requires `WITH_FLASH` stays "confirmation required" until
that line is present, and the SPI checkbox in **Operações** is still
required before compilation. RDV4 text from the client, or a module the
catalog already marks incompatible, stays blocked.
