# Compatibility

Version 2.0.0 compiles one platform: `PM3GENERIC`, with `LED_ORDER=PM3EASY`.
That is the same image rule as 1.0.0. The update monitor does not change it.
That LED setting selects the AT91SAM7S chip support in the Iceman makefiles.
It does not mean the connected board is a Proxmark3 Easy.

`PLATFORM_EXTRAS=FLASH` is added only when the SPI flash checkbox is
confirmed. `PLATFORM_SIZE=256` is forced only when `hw version` reports a
256 KB MCU and not a 512 KB MCU. A 512 KB MCU never receives
`PLATFORM_SIZE=256`. An unknown MCU leaves the size empty, so `make` keeps
its 512 KB default. The size checkbox in the window is informational and
disabled; the MCU text decides.

## USB identification

The port is not fixed. About every 1.5 seconds the application enumerates
serial ports and accepts:

| VID:PID | Treatment |
| --- | --- |
| `9AC4:4B8F` | Iceman USB ID. High confidence. |
| `2D2D:504D` | Legacy ID. High confidence. |
| `502D:502D` | Reported by the local driver profile as Easy. High confidence for the port only. The MCU text still decides the flash size. |

A generic USB serial adapter is ignored. If the text mentions Proxmark but
the VID/PID is unknown, confidence stays medium and flashing is refused.
With more than one accepted device, choose it in the list.

## RDV4

An RDV4 can be recognized from `hw version` / `hw status` and the
application will say so. Diagnosis and the client can still be used.
Compilation of an RDV4 image is not implemented. Flashing the PM3GENERIC
image onto an RDV4 is blocked (`E303`). Do not describe version 1 as RDV4
flashing support.

## Modules

The list is read from `armsrc\Standalone\Makefile.hal` of the selected
checkout, not from a fixed table. On the Iceman v4.23346 checkout used in
development the classification was:

| Classification | Count | Meaning in this application |
| --- | ---: | --- |
| Compatible | 26 | May be compiled for PM3GENERIC. |
| Requires SPI flash | 1 | `HF_ST25_TEAROFF`. Blocked until SPI flash is confirmed. |
| Uncertain | 2 | `HF_14ASNIFF`, `HF_15SNIFF`. Blocked until you confirm that you accept the local requirements. That confirmation does not enable `FLASH`. |
| Incompatible | 12 | RDV4-only, Bluetooth, or smartcard requirements. **Aplicar módulo** stays disabled. |

Incompatible identifiers on that checkout: `HF_BOG`, `HF_CARDHOPPER`,
`HF_COLIN`, `HF_ICECLASS`, `HF_LEGICSIM`, `HF_LEGIC_RDV4`, `HF_MFCSIM`,
`HF_REBLAY`, `LF_HIDFCBRUTE`, `LF_ICEHID`, `LF_NEXID`, `LF_THAREXDE`.

Another firmware version can change this table. The application rebuilds it
from the checkout you select.

## What was physically tried

Only one module has a laboratory record: HF MIFARE Classic chk/ecfill/sim
(MattyRun), on one board, on 23 October 2026. See the README section
`Hardware Validation — MattyRun`. That record is not a compatibility
certificate for the other 40 modules or for other Proxmark models.

The automatic result after a flash is still `OK210` (partial). The
application does not promote a module to "proved" because a person tested
it once.
