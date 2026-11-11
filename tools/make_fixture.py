#!/usr/bin/env python3
"""Turn a real Game.log into an anonymised test fixture.

Keeps only the lines SC-Dash reads (plus continuations of multi-line notifications and the
first three header lines) and replaces the player name, ids and addresses.

    python tools/make_fixture.py Game.log tests/fixtures/name.log --name PlayerName
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scdash.parser import _INTERESTING, _OPEN_NOTIFICATION  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("target")
    ap.add_argument("--name", required=True, help="player handle to replace")
    args = ap.parse_args()

    with open(args.source, "rb") as fh:
        lines = fh.read().split(b"\n")
    out, take_next = [], False
    for i, raw in enumerate(lines):
        text = raw.decode("latin-1")
        keep = take_next or bool(_INTERESTING.search(text)) or i < 3
        take_next = bool(_OPEN_NOTIFICATION.search(text.rstrip("\r")))
        if keep:
            out.append(text)
    txt = "\n".join(out) + "\n"

    txt = txt.replace(args.name, "TestPilot")
    ids = sorted(set(re.findall(r"(?:geid|playerGEID=|PlayerId\[|Player: |node \[)(\d{9,})", txt)))
    for n, real in enumerate(ids):
        txt = txt.replace(real, str(100000000001 + n))
    txt = re.sub(r"accountId \d+", "accountId 1000001", txt)
    txt = re.sub(r"Time\[\d+\]", "Time[1]", txt)
    txt = re.sub(r"session=[0-9a-f]{32}", "session=" + "0" * 32, txt)
    txt = re.sub(r"node_id=[0-9a-f-]{36}", "node_id=00000000-0000-0000-0000-000000000000", txt)
    txt = re.sub(r"\b(?!10\.0\.0\.1\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b(?!\.\d)", "10.0.0.1", txt)
    txt = re.sub(r"[A-Z]:\\\\Users\\\\[^\\\\\"' ]+", r"C:\\\\Users\\\\user", txt)
    assert args.name.lower() not in txt.lower()

    with open(args.target, "wb") as fh:
        fh.write(txt.encode("latin-1"))
    print(f"{len(out)} lines -> {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
