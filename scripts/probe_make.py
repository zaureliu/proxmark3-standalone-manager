"""Mostra PLATFORM, extras e STANDALONE que o make realmente lê. Não compila."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pm3manager.proxspace.locator import locate
from pm3manager.proxspace.shell import ProxSpaceShell

SCRIPT = """#!/bin/bash
cd /pm3/proxmark3-v4.23346
if test -f Makefile.platform; then echo REPO_FILE_YES; else echo REPO_FILE_NO; fi
if test -f /pm3/Makefile.platform; then echo PARENT_FILE_YES; cat /pm3/Makefile.platform; else echo PARENT_FILE_NO; fi
if test -f .Makefile.options.cache; then echo CACHE_YES; cat .Makefile.options.cache; else echo CACHE_NO; fi
summarize() {
  echo SCENARIO_$1
  make -n __pm3manager_probe__ > /tmp/pm3probe.txt 2>&1 || true
  grep -E 'Platform name:|PLATFORM:|PLATFORM_SIZE:|Platform extras:|Standalone mode:|Included options:|Invalid or empty PLATFORM|Makefile.platform' /tmp/pm3probe.txt | head -n 30
  echo END_$1
}
summarize DEFAULT
printf '%s\\n' 'PLATFORM=PM3GENERIC' 'LED_ORDER=PM3EASY' 'STANDALONE=HF_AVEFUL' 'PLATFORM_EXTRAS=FLASH' > Makefile.platform
summarize REPO
rm -f Makefile.platform
if test -f Makefile.platform; then echo LEFTOVER_YES; else echo LEFTOVER_NO; fi
echo PROBE_DONE
"""


def main() -> None:
    env = locate()
    shell = ProxSpaceShell(env, Path(__file__).resolve().parents[1] / "var" / "probe-work")
    result = shell.run_script(SCRIPT, timeout=120)
    out = Path(__file__).resolve().parents[1] / "var" / "make-probe.txt"
    out.write_text(result.output, encoding="utf-8")
    print(result.output)
    print("EXIT", result.exit_code)
    if "PROBE_DONE" not in result.output or "LEFTOVER_YES" in result.output:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
