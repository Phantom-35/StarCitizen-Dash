"""Print the CHANGELOG section of one version (used by the release workflow).

    python tools/release_notes.py 0.10.0
"""

import re
import sys
from pathlib import Path


def notes(version: str, changelog: str) -> str:
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", changelog, re.M | re.S)
    body = m.group(1).strip() if m else ""
    install = ("**Installieren/aktualisieren:** `update.bat` im SC-Dash-Ordner ausführen – oder unten "
               "„Source code (zip)“ laden und entpacken.")
    return (body + "\n\n" if body else "") + install + "\n"


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    sys.stdout.write(notes(sys.argv[1], (root / "CHANGELOG.md").read_text(encoding="utf-8")))
