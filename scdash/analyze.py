"""Log check: what is in a Game.log, what SC-Dash makes of it, and what it does not know yet.

    python -m scdash --analyze "…\\LIVE\\Game.log"
    python -m scdash --analyze new.log --compare old.log

Used for two things:

* finding data SC-Dash does not use yet (unknown HUD messages, new kinds of lines)
* the "more verbose log" experiment: put ``log_verbosity = 4`` and
  ``log_WriteToFileVerbosity = 4`` into ``user.cfg``, play, and compare the new log with an
  old one. The report says whether the game accepted the settings and what changed.

Player name, ids and addresses are masked, so the report can be shared.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from scdash.parser import LineAssembler, parse_line
from scdash.state import DashboardState
from scdash.watcher import _decode

_TAG = re.compile(r"^<[^>]+> (?:\[(?P<level>\w+)\] )?<(?P<tag>[^>]+)>")
_TS = re.compile(r"^<(\d{4}-\d{2}-\d{2}T[\d:.]+Z)>")
_CVAR = re.compile(r"\[CVARS\].*?variable \[(?P<name>[^\]]+)\] is marked \[(?P<mark>[^\]]+)\].*?"
                   r"with a value of \[(?P<value>[^\]]*)\].*?attempting to change to \[(?P<wanted>[^\]]*)\]")
_CVAR_ANY = re.compile(r"(?i)\b(log_verbosity|log_writetofileverbosity|log_writetofile|log_filter|log_spamdelay)\b")
_HANDLE = re.compile(r"Handle\[([^\]]+)\]")
_MASKS = (
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "<IP>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<ID>"),
    (re.compile(r"\b\d{9,}\b"), "<N>"),
)

#: settings to try for a more verbose log (names from the engine's cvar list)
VERBOSITY_CVARS = ("log_verbosity", "log_WriteToFileVerbosity")


class LogSummary:
    def __init__(self, path: str) -> None:
        self.path = path
        self.lines = 0
        self.size = 0
        self.first_ts: Optional[str] = None
        self.last_ts: Optional[str] = None
        self.tags: Counter = Counter()
        self.levels: Counter = Counter()
        self.kinds: Counter = Counter()          # parser event kinds
        self.categories: Counter = Counter()     # HUD notification categories
        self.unknown_hud: Counter = Counter()    # HUD texts SC-Dash has no rule for
        self.cvars: List[Tuple[str, str, str, str]] = []
        self.verbosity_mentions: List[str] = []
        self.handle: Optional[str] = None
        self.version: Optional[str] = None
        self.state = DashboardState()

    def mask(self, text: str) -> str:
        if self.handle:
            text = text.replace(self.handle, "<Pilot>")
        for rx, repl in _MASKS:
            text = rx.sub(repl, text)
        return text


def summarize(path: str) -> LogSummary:
    s = LogSummary(path)
    with open(path, "rb") as fh:
        raw = fh.read()
    s.size = len(raw)
    asm = LineAssembler()
    for chunk in raw.split(b"\n"):
        line = _decode(chunk).rstrip("\r")
        if not line:
            continue
        s.lines += 1
        m = _TS.match(line)
        if m:
            s.first_ts = s.first_ts or m.group(1)
            s.last_ts = m.group(1)
        m = _TAG.match(line)
        if m:
            s.tags[m.group("tag")] += 1
            s.levels[m.group("level") or "-"] += 1
        if s.handle is None:
            h = _HANDLE.search(line)
            if h:
                s.handle = h.group(1)
        c = _CVAR.search(line)
        if c:
            # the game states its decision itself: "... is marked [Not Whitelisted] ... - IGNORING"
            mark = c.group("mark") + (" - IGNORING" if "IGNORING" in line else "")
            s.cvars.append((c.group("name"), mark, c.group("value"), c.group("wanted")))
        if _CVAR_ANY.search(line):
            s.verbosity_mentions.append(line)
        for full in asm.feed(line):
            ev = parse_line(full)
            if ev is None:
                continue
            s.kinds[ev.kind] += 1
            if ev.kind == "version":
                s.version = ev.data["version"]
            if ev.kind == "notify":
                s.categories[ev.data["category"]] += 1
                if ev.data["category"] == "comms":
                    # collapse numbers so "Fined 500 UEC" and "Fined 900 UEC" count as one kind
                    s.unknown_hud[re.sub(r"\d+", "#", ev.data["text"])[:110]] += 1
            try:
                s.state.apply(ev)
            except Exception:  # the report must never fail because of one odd line
                pass
    return s


def _duration(s: LogSummary) -> str:
    from scdash.state import _secs_between

    secs = _secs_between(s.first_ts, s.last_ts)
    if secs is None:
        return "?"
    return f"{int(secs // 3600)}:{int(secs % 3600 // 60):02d} h"


def _verbosity_verdict(s: LogSummary) -> List[str]:
    out = []
    names = {n.lower(): (mark, value, wanted) for n, mark, value, wanted in s.cvars}
    for cvar in VERBOSITY_CVARS:
        hit = names.get(cvar.lower())
        if hit:
            mark, value, wanted = hit
            rejected = "not whitelisted" in mark.lower() or "ignoring" in mark.lower()
            verdict = ("ABGELEHNT – das Spiel meldet selbst „Not Whitelisted … IGNORING“" if rejected
                       else f"vom Spiel NICHT abgelehnt (Status: {mark})")
            out.append(f"  {cvar}: in der user.cfg gefunden, gewünscht {wanted}, Wert im Spiel {value} – {verdict}")
        elif any(cvar.lower() in line.lower() for line in s.verbosity_mentions):
            out.append(f"  {cvar}: wird in der Log erwähnt (siehe unten)")
        else:
            out.append(f"  {cvar}: keine Spur in der Log – nicht in der user.cfg gesetzt, oder ohne Meldung übernommen "
                       f"(dann müssten unten deutlich mehr Zeilen pro Stunde stehen)")
    for line in s.verbosity_mentions[:6]:
        out.append("    > " + s.mask(line)[:200])
    return out


def report(new: LogSummary, old: Optional[LogSummary] = None) -> str:
    L: List[str] = []
    add = L.append
    add("SC-Dash Log-Check")
    add("=================")
    add(f"Datei:        {new.path}")
    add(f"Spielversion: {new.version or '?'}    Zeilen: {new.lines:,}    Größe: {new.size / 1e6:.1f} MB    Dauer: {_duration(new)}".replace(",", "."))
    hours = None
    from scdash.state import _secs_between

    secs = _secs_between(new.first_ts, new.last_ts)
    if secs:
        hours = secs / 3600
        add(f"Zeilen pro Stunde: {new.lines / hours:,.0f}".replace(",", "."))
    add("")

    add("Ausführlichere Log (user.cfg)")
    add("-----------------------------")
    L.extend(_verbosity_verdict(new))
    rejected = [c for c in new.cvars if "not whitelisted" in c[1].lower()]
    add(f"  Vom Spiel abgelehnte Einstellungen insgesamt: {len(rejected)}"
        + (f" (z. B. {', '.join(sorted({c[0] for c in rejected})[:3])})" if rejected else ""))
    add("")

    add("Was SC-Dash erkannt hat")
    add("-----------------------")
    for kind, n in new.kinds.most_common():
        add(f"  {n:5d}  {kind}")
    if new.categories:
        add("  HUD-Meldungen nach Art: " + ", ".join(f"{k} {v}" for k, v in new.categories.most_common()))
    st = new.state.snapshot()["stats"]
    add("  Ergebnis: " + ", ".join(f"{k}={v}" for k, v in st.items() if v))
    add("")

    add("HUD-Meldungen ohne eigene Regel (landen im Komm-Log)")
    add("----------------------------------------------------")
    if not new.unknown_hud:
        add("  keine")
    for text, n in new.unknown_hud.most_common(25):
        add(f"  {n:4d}×  {new.mask(text)}")
    add("")

    add("Häufigste Zeilenarten")
    add("---------------------")
    for tag, n in new.tags.most_common(15):
        add(f"  {n:6d}  <{tag}>")
    add("")

    if old is not None:
        add(f"Vergleich mit {old.path}")
        add("-" * (15 + len(old.path)))
        o_secs = _secs_between(old.first_ts, old.last_ts)
        if secs and o_secs:
            a, b = new.lines / (secs / 3600), old.lines / (o_secs / 3600)
            add(f"  Zeilen pro Stunde: neu {a:,.0f} – alt {b:,.0f}  ({(a / b - 1) * 100:+.0f} %)".replace(",", "."))
        add(f"  Stufen neu: {dict(new.levels.most_common())}")
        add(f"  Stufen alt: {dict(old.levels.most_common())}")
        only_new = sorted(((n, t) for t, n in new.tags.items() if t not in old.tags), reverse=True)
        add(f"  Zeilenarten, die es nur in der neuen Log gibt: {len(only_new)}")
        for n, tag in only_new[:40]:
            add(f"    {n:5d}  <{tag}>")
        only_old = [t for t in old.tags if t not in new.tags]
        add(f"  Zeilenarten, die nur in der alten Log vorkommen: {len(only_old)}")
        add("")
        add("  Lesehilfe: Mehr Zeilen pro Stunde und viele neue Zeilenarten bedeuten, dass die")
        add("  Einstellung wirkt. Unterschiede allein durch anderes Spielverhalten (z. B. Kampf statt")
        add("  Fracht) sind normal – entscheidend ist der Abschnitt „Ausführlichere Log“ oben.")
    return "\n".join(L) + "\n"


def run(path: str, compare: Optional[str] = None) -> str:
    new = summarize(path)
    old = summarize(compare) if compare else None
    return report(new, old)
