# Security

Proxmark3 Standalone Manager can compile firmware and, after an explicit
in-memory authorization, write a fullimage to a connected Proxmark3. Treat
that as a physical operation on hardware you own or are authorized to
modify.

## Use

- Test only your own tags, readers, and access systems, or equipment for
  which you have permission.
- Do not send tag contents, keys, dumps, USB serial numbers, or unique
  hardware identifiers when you report a problem.
- The executable does not contain the Proxmark firmware and does not replace
  ProxSpace. Obtain those from their own projects and review their terms.
- Flash authorization is not saved. A stored `flash_autorizado` value is
  discarded on startup. Do not add a bypass that flashes without the
  confirmation shown for the next Apply operation.
- The application does not update the bootloader and does not run
  `pm3-flash-all` or `--unlock-bootloader`. Do not add those commands as a
  convenience or a recovery shortcut.

## Reports

Report a vulnerability privately to the project owner. Do not open a public
issue for a vulnerability that is not yet fixed. When the repository is
public, use its private vulnerability reporting rather than a public issue.

A useful report describes the version, what you expected, and what happened.
Logs may be attached after paths, user names, serial numbers, and unique IDs
are removed. The application already redacts some of those fields; still
read a log before sharing it.

## Not in scope

The Iceman firmware, ProxSpace, Qt, and the Proxmark hardware have their own
maintainers. A defect that exists only in those projects should go to them.
This application is not an official RfidResearchGroup product.

There is no bug-bounty program.
