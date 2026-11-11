"""Parsing of Star Citizen ``Game.log`` lines.

Everything in here is pure (no I/O) so it can be unit-tested easily.
The log format is not officially documented and changes between patches,
so every pattern is deliberately tolerant and unknown lines are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from scdash.locations import describe_location, quantum_destination, ship_name, weapon_name

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
_NOTIFICATION = re.compile(r"<SHUDEvent_OnNotification>.*?Added notification \"(?P<text>[^\"]*)\"?")
_CHANNEL = re.compile(r"^You have (?P<act>joined|left)(?: the)? channel '(?P<name>[^']*)'", re.I)
_OBJECTIVE_UPSERT = re.compile(
    r"<ObjectiveUpserted>.*?mission_id (?P<mid>[\w-]+) - objective_id (?P<oid>\S+) - state (?P<st>\w+)"
)
_QT_TARGET = re.compile(r"<Player Selected Quantum Target[^>]*>.*?selected point (?P<target>\S+) as their destination")
_QT_FUEL = re.compile(r"<Player Requested Fuel to Quantum Target[^>]*>.*?destination (?P<target>\S+)")
# Real 4.10 line: ...|CSCItemNavigation::CalculateRoute|Successfully calculated route to <target> fuel estimate 16.858223
_QT_ROUTE = re.compile(r"Successfully calculated route to (?P<target>\S+) fuel estimate (?P<fuel>[\d.]+)")
# All quantum lines name the ship they come from: "| NOT AUTH | RSI_Aurora_Mk2_920601993986[920601993986]|"
_QT_SHIP = re.compile(r"\| (?:NOT )?AUTH \| (?P<ship>[A-Za-z][A-Za-z0-9_]+?)_\d{6,}\[")
_QT_ROUTE_START = re.compile(r"Projected Start Location is (?P<start>.+?) for route to destination")
_QT_ARRIVED = re.compile(r"<Quantum Drive Arrived|Quantum Drive has arrived at final destination")

# --- cargo, shopping, connection ---------------------------------------------------
# Real 4.10 line: ... [CSCActorControlAdditiveStatePlace::DoPlace] 'Pilot' [id] placed
#   'Carryable_2H_FL_05x05x05_Commodity_medical_supplies_a_<id>' [id] in lootable container '<container>' [id]
_PLACE = re.compile(
    r"StatePlace::DoPlace\] '(?P<actor>[^']+)' \[\d+\] placed '(?P<item>[^']+?)(?:_\d{6,})?' \[\d+\] "
    r"in (?:lootable container|itemport \d+ on) '(?P<container>[^']+)'"
)
_COMMODITY = re.compile(r"Commodity_(?P<name>[A-Za-z_]+?)(?:_[a-z])?$")
# Purchases (formats per sc-log-tracker / csr: SendStandardItemBuyRequest until 4.7,
# SendShopBuyRequest / SendCommodityBuyRequest since 4.8)
_BUY_ITEM = re.compile(r"client_price\[(?P<price>[\d.]+)\].*?itemName\[(?P<item>[^\]]+)\] quantity\[(?P<qty>\d+)\]")
_BUY_COMMODITY = re.compile(r"\bprice\[(?P<price>[\d.]+)\]")
_SHOP = re.compile(r"shopName\[(?P<shop>[^\]]+)\]")
_DISCONNECT = re.compile(r'cause=(?P<code>\d+) reason="(?P<reason>[^"]*)"')
_CREW = re.compile(r"^(?:New Member Joined|Member Left) (?P<who>\S+) has (?P<act>joined|left) (?:the )?channel '(?P<name>[^']*)'", re.I)

# --- survival (4.x) ------------------------------------------------------------
# Kill lines (<Actor Death>) are limited to the local player since 4.0.2 and gone since
# about 4.4. The own death is still logged by the actor state machine:
_DEAD = re.compile(r"\[ActorState\] Dead")
_DEAD_ACTOR = re.compile(r"Actor '(?P<actor>[^']+)'")
_DEAD_FROM = re.compile(r"ejected from zone '(?P<zone>[^']+)'")
_DEAD_TO = re.compile(r"to zone '(?P<zone>[^']+)'")
_CORPSE = re.compile(r"\[ActorState\] Corpse>.*?Player '(?P<player>[^']+)' <(?P<who>local|remote) client>")
_OLD_CORPSE = re.compile(r"<Corpse> Player '(?P<player>[^']+)' <(?P<who>local|remote) client>")
_INCAP = re.compile(r"Logged an incap\.?!? nickname: (?P<player>[\w-]+), causes: \[(?P<causes>[^\]]*)\]")
_INCAP_CAUSE = re.compile(r"(?P<kind>\w+) \((?P<dmg>[\d.]+) damage\)")
_MEDBED = re.compile(
    r"<MED BED HEAL> Actor: (?P<actor>\S+) .*?Perform surgery event (?P<result>\w+), med bed name: (?P<bed>[^,]+), "
    r"vehicle name: (?P<vehicle>[^,]+), (?P<parts>.*?)(?: \[Team_|$)"
)
_COLLISION = re.compile(r"Fatal ?Collision occured for vehicle (?P<vehicle>\S+)(?:.*?Zone:\s*(?P<zone>[^,\]]+))?")
_VERSION = re.compile(r"ProductVersion: (?P<v>\d+\.\d+(?:\.\d+)?)")

# Cheap pre-filter: >95 % of all log lines are irrelevant, skip them with one search.
_INTERESTING = re.compile(
    r"Actor Death|Vehicle Destruction|RequestLocationInventory|<Join PU>|Login Success|"
    r"AccountLoginCharacterStatus_Character|SHUDEvent_OnNotification|<EndMission>|<MissionEnded>|"
    r"<ObjectiveUpserted>|Vehicle Control Flow|Quantum Target|Quantum Drive|Projected Start Location|Successfully calculated route|"
    r"ActorState\] (?:Dead|Corpse)|<Corpse>|Logged an incap|MED BED HEAL|Fatal ?Collision|"
    r"StatePlace::DoPlace|BuyRequest|cause=\d+ reason=\"|"
    r"SystemQuit|CSystem::Quit|ProductVersion"
)
_MISSION_ID = re.compile(r"MissionId:?\s*\[(?P<mid>[^\]]*)\]")
_OBJECTIVE_ID = re.compile(r"ObjectiveId:?\s*\[(?P<oid>[^\]]*)\]")
_END_MISSION = re.compile(r"<EndMission>.*?MissionId\[(?P<mid>[^\]]+)\].*?CompletionType\[(?P<ct>[^\]]+)\]")
_MISSION_ENDED = re.compile(r"<MissionEnded>.*?mission_id (?P<mid>[\w-]+).*?mission_state (?P<st>\w+)")
_VEHICLE_CONTROL = re.compile(
    r"<Vehicle Control Flow>.*?(?P<act>requesting|granted|releasing|released)\b.*?control token for '(?P<vehicle>[^']+)'"
)
_JURISDICTION = re.compile(r"^Entered\s+(?P<name>.+?)\s+Jurisdiction", re.I)

# (prefix, category) – first match wins, compared case-insensitively.
# Every entry is either seen in a real 4.10 Game.log or used by sc-log-tracker / csr
# (open-source parsers tested with real 4.x logs). No guesses - see README "Quellen".
NOTIFICATION_KINDS = (
    ("contract available", "available"),
    ("contract accepted", "accepted"),
    ("contract complete", "completed"),
    ("contract failed", "failed"),
    ("contract withdrawn", "abandoned"),
    ("contract shared", "shared"),
    ("new objective", "objective_new"),
    ("objective complete", "objective_done"),
    ("objective failed", "objective_failed"),
    ("objective withdrawn", "objective_failed"),
    ("entering armistice", "armistice_on"),
    ("leaving armistice", "armistice_off"),
    ("exiting armistice", "armistice_off"),
    ("entered monitored", "monitored_on"),
    ("exited monitored", "monitored_off"),
    ("monitored space down", "monitored_down"),
    ("monitored space restored", "monitored_on"),
    ("entering private property", "private_on"),
    ("leaving private property", "private_off"),
    ("leaving restricted area", "restricted_off"),
    ("restricted area", "restricted_on"),
    ("incapacitated", "incapacitated"),
    ("standby, local emergency services", "rescue"),
    ("crimestat rating increased", "crime_up"),
    ("crime committed", "crime"),
    ("vehicle impounded", "impounded"),
    ("low fuel", "low_fuel"),
    ("transaction complete", "transaction"),
    ("hangar request completed", "hangar"),
    ("quantum travel: your destination is obstructed", "qt_blocked"),
    ("received blueprint", "blueprint"),
)

# notifications that need a regex (checked when no prefix above matched)
_NOTIFICATION_PATTERNS = (
    (re.compile(r"^(?P<sev>minor|moderate|major|severe|critical) injury detected - (?P<part>.+?) - tier (?P<tier>\d)", re.I), "injury"),
    (re.compile(r"^fined (?P<amount>[\d.,]+) a?uec", re.I), "fined"),
    (re.compile(r"^(?P<who>\S+) committed (?P<what>.+?) against you", re.I), "crime_against"),
    (re.compile(r"^you sent (?P<who>.+?):\s*(?P<amount>[\d.,]+)\s*a?uec", re.I), "money_sent"),
    (re.compile(r"^(?P<who>\S+) has sent you:\s*(?P<amount>[\d.,]+)\s*a?uec", re.I), "money_received"),
    (re.compile(r"^a refinery work order has been completed at (?P<where>[^:]+)", re.I), "refinery"),
    (re.compile(r"^you've earned:\s*(?P<amount>\d+)\s+rewards", re.I), "rewards"),
    (re.compile(r"^journal entry added: jurisdiction: (?P<name>.+)$", re.I), "jurisdiction"),
)


def _amount(raw: str) -> int:
    return int(re.sub(r"[^\d]", "", raw) or 0)


def clean_notification_text(text: str) -> str:
    """HUD text as the player saw it: no markup, language-pack tags or line breaks."""
    text = re.sub(r"</?EM\d>", "", text).replace("\xa0", " ")
    text = re.sub(r"\[[^\]]*\bRep\]\*?", "", text)
    text = re.sub(r"\[BP\]\*?", "", text)
    return " ".join(text.split()).rstrip(":").strip()

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
    text = clean_notification_text(text)
    m = _CREW.match(text)
    if m:
        name = m.group("name").replace("@vehicle_Name", "").strip()
        return {"text": text.rstrip("."), "category": "crew_" + m.group("act").lower(), "subject": m.group("who"),
                "ship": name.rsplit(" : ", 1)[0].strip() if " : " in name else None}
    m = _CHANNEL.match(text)
    if m:
        # "You have joined channel 'RSI Aurora Mk II : PilotName'." -> the ship you just boarded
        name = m.group("name").replace("@vehicle_Name", "").strip()
        ship = name.rsplit(" : ", 1)[0].strip() if " : " in name else None
        return {"text": text.rstrip("."), "category": "channel_" + m.group("act").lower(), "subject": ship or name,
                "is_ship": ship is not None}
    low = text.lower()
    category = "comms"
    for prefix, cat in NOTIFICATION_KINDS:
        if low.startswith(prefix):
            category = cat
            break
    subject = text.split(":", 1)[1].strip().rstrip(":").strip() if ":" in text else text
    extra: dict = {}
    if category == "comms":
        m = _JURISDICTION.search(text)
        if m:
            category, subject = "jurisdiction", m.group("name").strip()
    if category == "comms":
        for rx, cat in _NOTIFICATION_PATTERNS:
            m = rx.search(text)
            if m:
                category, extra = cat, m.groupdict()
                if "amount" in extra:
                    extra["amount"] = _amount(extra["amount"])
                if cat == "jurisdiction":
                    subject = extra["name"].strip()
                break
    return {"text": text, "category": category, "subject": subject, **extra}


def _end_result(raw: str) -> str:
    raw = raw.lower().replace("mission_state_", "")
    return _END_RESULTS.get(raw, raw)

# Trailing numeric entity ids, e.g. "behr_rifle_ballistic_01_8471923" -> "behr_rifle_ballistic_01"
_ENTITY_ID = re.compile(r"_\d{5,}$")

_NPC_HINTS = ("PU_", "NPC", "AIModule", "Kopion", "Marok", "Quasigrazer", "Vlk_")


@dataclass
class LogEvent:
    """A single interesting thing that happened in the log."""

    # login | join | death | vehicle | location | notify | mission_end | objective_state | ship | quantum |
    # dead | corpse | incap | medbed | collision | version | quit
    kind: str
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
    if not _INTERESTING.search(line):
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

    if _DEAD.search(line):
        actor = _DEAD_ACTOR.search(line)
        src, dst = _DEAD_FROM.search(line), _DEAD_TO.search(line)
        return LogEvent("dead", ts, {
            "actor": actor.group("actor") if actor else None,
            "ship": ship_name(src.group("zone")) if src else None,
            "ship_destroyed": "destroyed vehicle" in line,
            "where": describe_location(dst.group("zone"))["place"] if dst else None,
        })
    m = _CORPSE.search(line) or _OLD_CORPSE.search(line)
    if m:
        return LogEvent("corpse", ts, {"player": m.group("player"), "local": m.group("who") == "local"})
    m = _INCAP.search(line)
    if m:
        causes = [c.group("kind").replace("Damage", "") for c in _INCAP_CAUSE.finditer(m.group("causes"))]
        return LogEvent("incap", ts, {"player": m.group("player"), "causes": causes})
    m = _MEDBED.search(line)
    if m:
        parts = [k for k, v in re.findall(r"(\w+): (true|false)", m.group("parts")) if v == "true"]
        vehicle = m.group("vehicle").strip()
        return LogEvent("medbed", ts, {
            "actor": m.group("actor"), "ok": m.group("result").lower() == "success",
            "vehicle": None if vehicle.lower() in ("none", "null", "") else ship_name(vehicle.lstrip("@")),
            "parts": parts,
        })
    m = _COLLISION.search(line)
    if m:
        if "PlayerPilot: 1" not in line:
            return None  # someone else's crash
        zone = m.group("zone")
        return LogEvent("collision", ts, {
            "vehicle": ship_name(m.group("vehicle")),
            "where": describe_location(zone.strip())["place"] if zone else None,
        })

    m = _PLACE.search(line)
    if m:
        c = _COMMODITY.search(m.group("item"))
        if not c:
            return None  # only cargo boxes are interesting
        return LogEvent("cargo", ts, {
            "actor": m.group("actor"),
            "item": c.group("name").replace("_", " ").title(),
            "delivered": m.group("container").lower().startswith("mission_"),
        })
    if "BuyRequest" in line:
        if "Sending" not in line:
            return None
        shop = _SHOP.search(line)
        shop_name = re.sub(r"_\d+$", "", shop.group("shop")).replace("_", " ").strip() if shop else None
        if "Commodity" in line:
            m = _BUY_COMMODITY.search(line)
            return LogEvent("purchase", ts, {"price": float(m.group("price")) if m else 0.0, "item": "Fracht",
                                             "qty": 1, "shop": shop_name})
        m = _BUY_ITEM.search(line)
        if m:
            item = re.sub(r"_\d{6,}$", "", m.group("item")).replace("_", " ")
            return LogEvent("purchase", ts, {"price": float(m.group("price")), "item": item,
                                             "qty": int(m.group("qty")), "shop": shop_name})
        return None
    m = _DISCONNECT.search(line)
    if m:
        return LogEvent("disconnect", ts, {"code": m.group("code"), "reason": m.group("reason"),
                                           "in_pu": 'gamerules="SC_Default"' in line})

    m = _OBJECTIVE_UPSERT.search(line)
    if m:
        state = {"completed": "done", "failed": "failed"}.get(m.group("st").lower().replace("mission_objective_state_", ""))
        if state is None:
            return None
        return LogEvent("objective_state", ts, {"mission_id": _id(m.group("mid")), "objective_id": m.group("oid"), "state": state})

    ship = _QT_SHIP.search(line)
    qt_ship = ship_name(ship.group("ship")) if ship else None
    qt_class = ship.group("ship") if ship else None
    m = _QT_ROUTE.search(line)
    if m:
        return LogEvent("quantum", ts, {"phase": "route", "fuel": float(m.group("fuel")), "ship": qt_ship, "ship_class": qt_class,
                                        **quantum_destination(m.group("target"))})
    m = _QT_TARGET.search(line)
    if m:
        return LogEvent("quantum", ts, {"phase": "target", "ship": qt_ship, "ship_class": qt_class, **quantum_destination(m.group("target"))})
    m = _QT_ROUTE_START.search(line)
    if m:
        return LogEvent("route_start", ts, {"start": m.group("start").strip()})
    m = _QT_FUEL.search(line)
    if m:
        return LogEvent("quantum", ts, {"phase": "fuel", "ship": qt_ship, "ship_class": qt_class, **quantum_destination(m.group("target"))})
    if _QT_ARRIVED.search(line):
        return LogEvent("quantum", ts, {"phase": "arrived", "name": None, "kind": None, "ship": qt_ship, "ship_class": qt_class})

    m = _VEHICLE_CONTROL.search(line)
    if m:
        entering = m.group("act") in ("requesting", "granted")
        return LogEvent("ship", ts, {"vehicle": ship_name(m.group("vehicle")), "entering": entering})

    if _QUIT.search(line):
        return LogEvent("quit", ts, {})

    m = _VERSION.search(line)
    if m:
        return LogEvent("version", ts, {"version": m.group("v")})

    return None


_TS_PREFIX = re.compile(r"^<\d{4}-\d{2}-\d{2}T[\d:.]+Z>\s?")
_OPEN_NOTIFICATION = re.compile(r"<SHUDEvent_OnNotification>.*Added notification \"[^\"]*$")
_NEW_ENTRY = re.compile(r"^<[^>]+> \[\w+\] <")


class LineAssembler:
    """Re-joins log entries that the game splits over several lines.

    Notification texts may contain a line break, e.g.::

        <ts> [Notice] <SHUDEvent_OnNotification> Added notification "Objective Complete: Foo
        <ts> : " [16] to queue. ... MissionId: [..], ObjectiveId: [..]

    ``feed`` returns the complete logical lines that are ready to be parsed.
    """

    MAX_PARTS = 4

    def __init__(self) -> None:
        self._pending: Optional[str] = None
        self._parts = 0

    def feed(self, line: str) -> list:
        out = []
        if self._pending is not None:
            if _NEW_ENTRY.match(line) or self._parts >= self.MAX_PARTS:
                out.append(self._pending)  # continuation never came - use what we have
                self._pending = None
            else:
                self._pending += _TS_PREFIX.sub("", line)
                self._parts += 1
                if self._pending.count('"') % 2 == 0:  # closing quote arrived
                    out.append(self._pending)
                    self._pending = None
                return out
        if _OPEN_NOTIFICATION.search(line):
            self._pending, self._parts = line, 1
        else:
            out.append(line)
        return out

    def reset(self) -> None:
        self._pending = None
