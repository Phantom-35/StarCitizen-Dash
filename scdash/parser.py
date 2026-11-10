"""Parsing of Star Citizen ``Game.log`` lines.

Everything in here is pure (no I/O) so it can be unit-tested easily.
The log format is not officially documented and changes between patches,
so every pattern is deliberately tolerant and unknown lines are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from scdash.locations import describe_location, ship_name, weapon_name

_TS = re.compile(r"^<(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)>")

_LOGIN = re.compile(r"User Login Success - Handle\[(?P<handle>[^\]]+)\]")
_CHARACTER = re.compile(r"<AccountLoginCharacterStatus_Character>.*?\bname (?P<handle>\S+)")

_JOIN_PU = re.compile(r"<Join PU>.*?shard\[(?P<shard>[^\]]+)\]")

_ACTOR_DEATH = re.compile(
    r"<Actor Death> CActor::Kill: '(?P<victim>[^']+)' \[\d+\] in zone '(?P<zone>[^']*)' "
    r"killed by '(?P<killer>[^']+)' \[\d+\] using '(?P<weapon>[^']*)' \[[^\]]*\] "
    r"with damage type '(?P<dtype>[^']*)'"
)

_VEHICLE_DESTRUCTION = re.compile(
    r"<Vehicle Destruction>.*?Vehicle '(?P<vehicle>[^']+)' \[\d+\] in zone '(?P<zone>[^']*)'.*?"
    r"driven by '(?P<driver>[^']+)' \[\d+\] advanced from destroy level (?P<from>\d+) "
    r"to (?P<to>\d+) caused by '(?P<cause>[^']+)' \[\d+\] with '(?P<dtype>[^']*)'"
)

_LOCATION = re.compile(r"<RequestLocationInventory>.*?Location\[(?P<location>[^\]]+)\]")

_QUIT = re.compile(r"<SystemQuit>|CSystem::Quit")

# Trailing numeric entity ids, e.g. "behr_rifle_ballistic_01_8471923" -> "behr_rifle_ballistic_01"
_ENTITY_ID = re.compile(r"_\d{5,}$")

_NPC_HINTS = ("PU_", "NPC", "AIModule", "Kopion", "Marok", "Quasigrazer", "Vlk_")


@dataclass
class LogEvent:
    """A single interesting thing that happened in the log."""

    kind: str  # login | join | death | vehicle | location | quit
    ts: Optional[str] = None
    data: dict = field(default_factory=dict)


def clean_name(raw: str) -> str:
    """Strip entity ids and make internal names a bit more readable."""
    name = _ENTITY_ID.sub("", raw.strip())
    return name


def is_npc(raw: str) -> bool:
    return any(hint in raw for hint in _NPC_HINTS)


def pretty_label(raw: str) -> str:
    """Turn ``Stanton1_Lorville`` style ids into ``Stanton1 Lorville``."""
    return clean_name(raw).replace("_", " ").strip()


def parse_line(line: str) -> Optional[LogEvent]:
    """Parse one log line. Returns ``None`` for lines we do not care about."""
    if "<" not in line:
        return None

    m = _TS.match(line)
    ts = m.group("ts") if m else None

    m = _ACTOR_DEATH.search(line)
    if m:
        d = m.groupdict()
        return LogEvent(
            "death",
            ts,
            {
                "victim": clean_name(d["victim"]),
                "killer": clean_name(d["killer"]),
                "weapon": weapon_name(d["weapon"]),
                "zone": describe_location(d["zone"])["place"] if d["zone"] else None,
                "damage": d["dtype"],
                "victim_npc": is_npc(d["victim"]),
                "killer_npc": is_npc(d["killer"]),
            },
        )

    m = _VEHICLE_DESTRUCTION.search(line)
    if m:
        d = m.groupdict()
        return LogEvent(
            "vehicle",
            ts,
            {
                "vehicle": ship_name(d["vehicle"]),
                "zone": describe_location(d["zone"])["place"] if d["zone"] else None,
                "driver": clean_name(d["driver"]),
                "driver_npc": is_npc(d["driver"]),
                "cause": clean_name(d["cause"]),
                "from": int(d["from"]),
                "to": int(d["to"]),
                "damage": d["dtype"],
            },
        )

    m = _LOCATION.search(line)
    if m:
        return LogEvent("location", ts, {"location": describe_location(m.group("location"))})

    m = _JOIN_PU.search(line)
    if m:
        return LogEvent("join", ts, {"shard": m.group("shard")})

    m = _LOGIN.search(line) or _CHARACTER.search(line)
    if m:
        return LogEvent("login", ts, {"handle": m.group("handle").strip()})

    if _QUIT.search(line):
        return LogEvent("quit", ts, {})

    return None
