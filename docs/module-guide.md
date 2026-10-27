# Standalone module guide

Version 2.1.0 adds a **Manual** tab and **Ver manual do módulo** on the
module list. The guide is offline. Opening a card does not contact GitHub,
does not run an RFID command, and does not compile or flash.

The existing catalog remains the list of module IDs. The guide does not
invent new IDs and does not replace the compatibility class used by
**Aplicar módulo**. A card can be more specific about what was read in
source, but a consultive note does not make an incompatible module
compilable.

## Evidence

Cards were reviewed against the local Iceman checkout v4.23346 at commit
`dc0110c29d320e04b37ea436ee2924901407ae72`. The sources are
`armsrc/Standalone/Makefile.hal`, the mode's `.c` file when a field was
actually checked there, and `armsrc/appmain.c` for the common start:
the button is held for one second (`BUTTON_HOLD`) and then `RunMod()` runs.
Standalone mode is not entered when the compiled target is PM5. Only the
mode compiled into the fullimage starts.

`armsrc/Standalone/readme.md` in that checkout says its per-mode pages were
generated and may be wrong. Those pages were not used as field evidence.
The wiki page
`https://github.com/RfidResearchGroup/proxmark3/wiki/Standalone-mode`
is linked as a pointer and is labeled as not used for the fields. Source
links use that commit, not `master`.

A field that was not confirmed says "Não documentado" or "Não verificado".
The guide does not fill LED sequences, button sequences, or memory sizes
from a generic description. `generic_hardware` is left unknown unless a
source confirms it. It is not set just because a mode lacks an RDV4 mark.

## Coverage

The shipped file `pm3manager/guide/data/reviewed.json` has one card for each
of the 41 IDs in the v4.23346 catalog. Tests fail if an ID is missing,
duplicated, or extra. A module that appears in a newer checkout and is not
in that file is shown as "Sem revisão", with the short `Makefile.hal` line
only. That is not a reviewed card.

Of those 41 cards, none is marked fully reviewed. All 41 are partial: each
still has at least one field without enough evidence. HF_MATTYRUN and
LF_EM4100RWC were read in the mode sources. Even those two leave LEDs, and
for LF_EM4100RWC the button sequence, unverified where the comments and the
code do not agree. No card key, compiled ID, or attack procedure is copied
into the application.

The **Hardware Validation — MattyRun** section of the README is an older
laboratory record for one scenario. It is not a certification of the
HF_MATTYRUN card.

## Filters and links

Search and filters use known fields only: HF, LF, generic hardware, RDV4,
SPI flash required, complete documentation, partial documentation, and
unverified information. RDV4 and SPI filters follow the Makefile marks
(`RDV4 only`, `_RDV4`, `STANDALONE_MODES_REQ_FLASH`). They are not a
measurement of the connected board.

On the v4.23346 checkout those marks are not the same set as the catalog
class. `STANDALONE_MODES_REQ_FLASH` lists 11 modes, and the guide filter
"Requer flash SPI" follows that list. Ten of them are already incompatible
with this application's PM3GENERIC build, mostly because `Makefile.hal`
marks them RDV4-only. The catalog class "Requer flash SPI" stays at one
mode, HF_ST25_TEAROFF: flash is required and the mode is not already
rejected for another reason. The guide does not change that class.

**Abrir referência** opens only `https://github.com/RfidResearchGroup/proxmark3`
URLs that the application already allows: the repository root, the
Standalone wiki page, or a `blob`/`tree` URL pinned to a 40-character
commit. `master`, other hosts, `file:`, and `javascript:` URLs are refused.
Card text is plain text. It is not HTML, and it is not executed.

## Responsible use

Some modes can read, emulate, clone, or test authentication. The card says
to use only cards, tags, and systems you own or are allowed to test. The
manual does not add a transmit, clone, or attack action.
