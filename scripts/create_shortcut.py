"""Cria ou recria o atalho da área de trabalho do usuário atual."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pm3manager.install.shortcut import SHORTCUT_NAME, create_shortcut, desktop_directory
from pm3manager.paths import project_root


def main() -> None:
    root = project_root()
    exe = root / "dist" / "Proxmark3StandaloneManager" / "Proxmark3StandaloneManager.exe"
    link = desktop_directory() / SHORTCUT_NAME
    create_shortcut(exe, link, exe.parent, exe)
    print(link)


if __name__ == "__main__":
    main()
