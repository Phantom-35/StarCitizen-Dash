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

# --- missions / HUD notifications -------------------------------------------
# Every HUD notification (contracts, objectives, zones, ...) ends up in the log as
#   <SHUDEvent_OnNotification> Added notification "Contract Accepted: Foo: " [12] to queue. ...
#   MissionId: [uuid], ObjectiveId: [id] ...
_NOTIFICATION = re.compile(r"<SHUDEvent_OnNotification>.*?Added notification \"(?P<text>[^\"]*)\"")
_MISSION_ID = re.compile(r"MissionId:?\s*\[(?P<mid>[^\]]*)\]")
_OBJECTIVE_ID = re.compile(r"ObjectiveId:?\s*\[(?P<oid>[^\]]*)\]")
_END_MISSION = re.compile(r"<EndMission>.*?MissionId\[(?P<mid>[^\]]+)\].*?CompletionType\[(?P<ct>[^\]]+)\]")
_MISSION_ENDED = re.compile(r"<MissionEnded>.*?mission_id (?P<mid>[\w-]+).*?mission_state (?P<st>\w+)")
_VEHICLE_CONTROL = re.compile(
    r"<Vehicle Control Flow>.*?(?P<act>requesting|granted|releasing|released)\b.*?control token for '(?P<vehicle>[^']+)'"
)
_JURISDICTION = re.compile(r"(?:Entering|Entered)\s+(?P<name>.+?)\s+Jurisdiction", re.I)

# (prefix, category) – first match wins, compared case-insensitively
NOTIFICATION_KINDS = (
    ("contract accepted", "accepted"),
    ("contract complete", "completed"),
    ("contract failed", "failed"),
    ("contract abandoned", "abandoned"),
    ("contract withdrawn", "abandoned"),
    ("contract cancel", "abandoned"),
    ("contract expired", "abandoned"),
    ("new objective", "objective_new"),
    ("objective updated", "objective_new"),
    ("objective complete", "objective_done"),
    ("objective failed", "objective_failed"),
    ("objective withdrawn", "objective_failed"),
    ("entered armistice", "armistice_on"),
    ("entering armistice", "armistice_on"),
    ("leaving armistice", "armistice_off"),
    ("left armistice", "armistice_off"),
    ("exited armistice", "armistice_off"),
    ("entered monitored", "monitored_on"),
    ("entering monitored", "monitored_on"),
    ("leaving monitored", "monitored_off"),
    ("left monitored", "monitored_off"),
    ("entered unmonitored", "monitored_off"),
    ("entering unmonitored", "monitored_off"),
)

_END_RESULTS = {
    "complete": "completed", "completed": "completed", "succeeded": "completed", "success": "completed",
    "fail": "failed", "failed": "failed",
    "abandon": "abandoned", "abandoned": "abandoned", "withdrawn": "abandoned", "cancelled": "abandoned",
}
_NULL_ID = re.compile(r"^[0-]*$")


def _id(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return None if _NULL_ID.match(value) else value


def classify_notification(text: str) -> dict:
    """Split a HUD notification into category + subject."""
    text = text.strip().rstrip(":").strip()
    low = text.lower()
    category = "comms"
    for prefix, cat in NOTIFICATION_KINDS:
        if low.startswith(prefix):
            category = cat
            break
    subject = text.split(":", 1)[1].strip().rstrip(":").strip() if ":" in text else text
    if category == "comms":
        m = _JURISDICTION.search(text)
        if m:
            category, subject = "jurisdiction", m.group("name").strip()
    return {"text": text, "category": category, "subject": subject}


def _end_result(raw: str) -> str:
    raw = raw.lower().replace("mission_state_", "")
    return _END_RESULTS.get(raw, raw)

# Trailing numeric entity ids, e.g. "behr_rifle_ballistic_01_8471923" -> "behr_rifle_ballistic_01"
_ENTITY_ID = re.compile(r"_\d{5,}$")

_NPC_HINTS = ("PU_", "NPC", "AIModule", "Kopion", "Marok", "Quasigrazer", "Vlk_")


@dataclass
class LogEvent:
    """A single interesting thing that happened in the log."""

    kind: str  # login | join | death | vehicle | location | notify | mission_end | ship | quit
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

    m = _NOTIFICATION.search(line)
    if m:
        data = classify_notification(m.group("text"))
        mid, oid = _MISSION_ID.search(line), _OBJECTIVE_ID.search(line)
        data["mission_id"] = _id(mid.group("mid")) if mid else None
        data["objective_id"] = _id(oid.group("oid")) if oid else None
        return LogEvent("notify", ts, data)

    m = _END_MISSION.search(line)
    if m:
        return LogEvent("mission_end", ts, {"mission_id": _id(m.group("mid")), "result": _end_result(m.group("ct"))})
    m = _MISSION_ENDED.search(line)
    if m:
        return LogEvent("mission_end", ts, {"mission_id": _id(m.group("mid")), "result": _end_result(m.group("st"))})

    m = _VEHICLE_CONTROL.search(line)
    if m:
        entering = m.group("act") in ("requesting", "granted")
        return LogEvent("ship", ts, {"vehicle": ship_name(m.group("vehicle")), "entering": entering})

    if _QUIT.search(line):
        return LogEvent("quit", ts, {})

    return None
