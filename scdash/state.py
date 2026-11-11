"""Thread-safe dashboard state shared between the watchers and the HTTP server."""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict, deque
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from scdash.locations import locate_place, objective_place, shard_region
from scdash.memory import PlaceMemory, is_planet_frame
from scdash import ships
from scdash.parser import LogEvent

MAX_EVENTS = 60
MAX_HISTORY = 12

COMBAT, MISSION = "combat", "mission"
BOTH = (COMBAT, MISSION)

_RESULT_TEXT = {"completed": "Auftrag erledigt", "failed": "Auftrag gescheitert", "abandoned": "Auftrag abgebrochen"}
_RESULT_CAT = {"completed": "success", "failed": "fail", "abandoned": "other"}

# Connection error codes (meanings per sc-log-tracker). 30010/30016/30028 are normal goodbyes.
NET_ERRORS = {
    "30000": "Zeitüberschreitung der Verbindung",
    "30013": "Server-Signal (Serverabsturz?)",
    "30015": "Woanders angemeldet",
    "30024": "Backend-Dienste antworten nicht",
    "41045": "Zeitüberschreitung beim Laden der Spielregeln",
    "41058": "Spielerabfrage fehlgeschlagen",
    "41070": "Zeitüberschreitung beim Laden des Charakters",
    "64004": "Server konnte deinen Standort nicht auflösen",
    "64008": "Server konnte deinen Standort nicht auflösen",
}
BENIGN_NET = {"30010", "30016", "30028"}

DEATH_DEDUP_SECONDS = 90
MEDBED_DEDUP_SECONDS = 300   # the HUD repeats "bed has restored your health" while you lie in it
PLACE_FRESH_SECONDS = 1200   # the known location must be this recent to label a marker with it   # Dead / Corpse / Actor Death lines of the same death
INCAP_DEDUP_SECONDS = 60
JURISDICTION_FLAP_SECONDS = 30
_BODY_DE = {"head": "Kopf", "torso": "Torso", "leftArm": "linker Arm", "rightArm": "rechter Arm",
            "leftLeg": "linkes Bein", "rightLeg": "rechtes Bein"}
_PART_DE = {"head": "Kopf", "torso": "Torso", "left arm": "linker Arm", "right arm": "rechter Arm",
            "left leg": "linkes Bein", "right leg": "rechtes Bein"}
_INJURY_DE = {"minor": "Leichte", "moderate": "Mittlere", "major": "Schwere", "severe": "Schwere", "critical": "Kritische"}


def _secs_between(a: Optional[str], b: Optional[str]) -> Optional[float]:
    try:
        fa = datetime.fromisoformat(a.replace("Z", "+00:00"))  # type: ignore[union-attr]
        fb = datetime.fromisoformat(b.replace("Z", "+00:00"))  # type: ignore[union-attr]
        return max(0.0, (fb - fa).total_seconds())
    except (AttributeError, ValueError):
        return None


class DashboardState:
    def __init__(self, places: Optional[PlaceMemory] = None) -> None:
        #: remembers which place a mission marker belongs to (None = off, e.g. for log checks)
        self.place_memory = places
        # A Condition (it is also a lock): HTTP long-polls sleep on it until the state changes.
        self._lock = threading.Condition()
        self._version = 0
        self._boot = os.urandom(4).hex()  # distinguishes server restarts for the frontend
        self._event_id = 0
        self.log_path: Optional[str] = None
        self.log_found = False
        self.game_running: Optional[bool] = None  # None = unknown
        self.rsi_status: Optional[Dict[str, Any]] = None
        self._reset_session()

    # ------------------------------------------------------------------ helpers
    def _reset_session(self) -> None:
        self.handle: Optional[str] = None
        self.shard: Optional[str] = None
        self.location: Optional[Dict[str, Optional[str]]] = None
        self.location_since: Optional[str] = None
        self.session_start: Optional[str] = None
        self.last_log_ts: Optional[str] = None
        self.alive_since: Optional[str] = None
        self.last_killer: Optional[Dict[str, Any]] = None
        self.kills = 0
        self.npc_kills = 0
        self.deaths = 0
        self.vehicles_lost = 0
        self.vehicles_destroyed = 0
        self.streak = 0
        self.best_streak = 0
        self.ended = False
        self.feeds: Dict[str, deque] = {COMBAT: deque(maxlen=MAX_EVENTS), MISSION: deque(maxlen=MAX_EVENTS)}
        # missions / navigation
        self.missions: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self.mission_history: deque = deque(maxlen=MAX_HISTORY)
        self.missions_completed = 0
        self.missions_failed = 0
        self.missions_abandoned = 0
        self.places: set = set()
        self.ship: Optional[str] = None
        self.armistice: Optional[bool] = None
        self.monitored: Optional[bool] = None
        self.jurisdiction: Optional[str] = None
        self._ship_from_channel = False
        self._ended_missions: set = set()
        self.quantum_jumps = 0
        # survival / law / money
        self.open_injuries: list = []   # untreated injuries since the last med bed / death
        self.crew: list = []            # others aboard our ship
        self.spend = 0.0
        self.purchases = 0
        self.cargo_loaded = 0
        self.cargo_delivered = 0
        self.disconnects = 0
        self._last_disconnect_ts: Optional[str] = None
        self.incaps = 0
        self.injuries = 0
        self.medbed = 0
        self.collisions = 0
        self.crimestat = 0
        self.fines = 0
        self.money_in = 0
        self.money_out = 0
        self.best_alive = 0.0
        self.last_death: Optional[Dict[str, Any]] = None
        self._last_death_ts: Optional[str] = None
        self._last_incap_ts: Optional[str] = None
        self.restricted: Optional[bool] = None
        self._markers: Dict[str, Dict[str, tuple]] = {}   # mission id -> objective id -> position
        self._last_medbed_ts: Optional[str] = None
        self.private: Optional[bool] = None
        self._jur_left: Dict[str, str] = {}
        self.quantum_target: Optional[str] = None
        self._qt_location: Optional[Dict[str, Optional[str]]] = None  # where a real-place jump ends
        self.quantum_fuel: Optional[float] = None   # the game's estimate for the planned route
        self.quantum_fuel_used = 0.0                # sum of the estimates of the jumps actually made
        self.ship_since: Optional[str] = None
        self.ship_class: Optional[str] = None       # game class name, known from quantum lines
        self._fuel_by_ship: Dict[str, float] = {}   # estimates of flown jumps per ship (log units)
        self.game_version: Optional[str] = None

    def _touch(self) -> None:
        self._version += 1
        self._lock.notify_all()

    def wait_for_change(self, token: str, timeout: float) -> bool:
        """Block until the state differs from ``token`` (True) or the timeout expires (False)."""
        with self._lock:
            return self._lock.wait_for(lambda: f"{self._boot}-{self._version}" != token, timeout)

    # ------------------------------------------------------------------ mutators
    def new_session(self) -> None:
        """Called when Game.log was recreated (game restarted)."""
        with self._lock:
            self._reset_session()
            self._touch()

    def begin_session(self, ts: Optional[str]) -> None:
        """The first line of a fresh Game.log carries the game's start time."""
        if not ts:
            return
        with self._lock:
            if self.session_start is None or ts < self.session_start:
                self.session_start = ts
                if self.alive_since is None:
                    self.alive_since = ts
                self._touch()

    def set_log(self, path: Optional[str], found: bool) -> None:
        with self._lock:
            if path != self.log_path or found != self.log_found:
                self.log_path, self.log_found = path, found
                self._touch()

    def set_game_running(self, running: Optional[bool]) -> None:
        with self._lock:
            if running != self.game_running:
                self.game_running = running
                self._touch()

    def set_rsi_status(self, status: Optional[Dict[str, Any]]) -> None:
        with self._lock:
            if status != self.rsi_status:
                self.rsi_status = status
                self._touch()

    def apply(self, ev: LogEvent) -> None:
        with self._lock:
            self._apply(ev)
            self._touch()

    def _push(
        self,
        ev: LogEvent,
        cat: str,
        title: str,
        actor: str = "",
        detail: str = "",
        feeds: Iterable[str] = (COMBAT,),
        banner: bool = False,
    ) -> None:
        self._event_id += 1
        item = {
            "id": self._event_id, "ts": ev.ts, "cat": cat, "title": title,
            "actor": actor, "detail": detail, "banner": banner,
        }
        for f in feeds:
            self.feeds[f].appendleft(item)

    @staticmethod
    def _detail(*parts: Optional[str]) -> str:
        return " · ".join(p for p in parts if p)

    def _died(self, ts: Optional[str]) -> None:
        self.streak = 0
        alive = _secs_between(self.alive_since, ts)
        if alive is not None:
            self.best_alive = max(self.best_alive, alive)
        self.alive_since = ts

    @staticmethod
    def _within(a: Optional[str], b: Optional[str], seconds: float) -> bool:
        gap = _secs_between(a, b)
        return gap is not None and gap <= seconds

    def _register_death(self, ev: LogEvent, cause: str, who: str = "", where: Optional[str] = None) -> bool:
        """Count a death once, no matter how many lines the game writes about it."""
        if self._within(self._last_death_ts, ev.ts, DEATH_DEDUP_SECONDS):
            # same death - but keep the more detailed description
            if self.last_death and who and not self.last_death.get("who"):
                self.last_death.update({"cause": cause, "who": who, "where": where or self.last_death.get("where")})
            return False
        self._last_death_ts = ev.ts
        self.deaths += 1
        self._died(ev.ts)
        self.ship = None
        self._ship_from_channel = False
        self.quantum_target = self._qt_location = self.quantum_fuel = None
        self.open_injuries = []
        self.crew = []
        self.last_death = {"ts": ev.ts, "cause": cause, "who": who, "where": where}
        self._push(ev, "death", cause, who, where or "", feeds=BOTH, banner=True)
        return True

    def _apply(self, ev: LogEvent) -> None:
        if ev.ts:
            if self.session_start is None:
                self.session_start = ev.ts
                self.alive_since = ev.ts
            self.last_log_ts = ev.ts
        d = ev.data
        me = self.handle

        if ev.kind == "login":
            if d["handle"] != self.handle:
                self.handle = d["handle"]
                self.ended = False
                self._push(ev, "info", "Eingeloggt", self.handle, feeds=BOTH)
        elif ev.kind == "join":
            self.shard = d["shard"]
            self.alive_since = ev.ts  # time in the menus should not count as "alive"
            self.armistice = self.monitored = self.jurisdiction = self.ship = None
            self.crew = []
            self.quantum_target = self._qt_location = self.quantum_fuel = None
            self.restricted = self.private = None
            self._push(ev, "info", "Shard beigetreten", shard_region(self.shard) or "", self.shard, feeds=BOTH)
        elif ev.kind == "location":
            self._set_location(ev, d["location"])
        elif ev.kind == "death":
            victim, killer = d["victim"], d["killer"]
            detail = self._detail(d["weapon"], d["zone"])
            if me and victim == me:
                if killer == me or killer.lower() == "unknown":
                    self._register_death(ev, "Gestorben", d["damage"] or "Unfall", d["zone"])
                else:
                    who = "NPC" if d["killer_npc"] else killer
                    self.last_killer = {"name": who, "weapon": d["weapon"], "ts": ev.ts}
                    self._register_death(ev, "Getötet von", who, detail or None)
            elif me and killer == me:
                self.streak += 1
                self.best_streak = max(self.best_streak, self.streak)
                if d["victim_npc"]:
                    self.npc_kills += 1
                    self._push(ev, "kill", "NPC eliminiert", "", detail, banner=True)
                else:
                    self.kills += 1
                    self._push(ev, "kill", "Eliminiert", victim, detail, banner=True)
            else:
                self._push(ev, "other", "Kill", f"{killer} → {victim}", detail)
        elif ev.kind == "vehicle":
            # destroy level 1 = soft death / disabled, 2 = fully destroyed
            if d["to"] < 1:
                return
            state = "zerstört" if d["to"] >= 2 else "außer Gefecht"
            if me and d["driver"] == me:
                if d["to"] >= 2:
                    self.vehicles_lost += 1
                self._push(ev, "death", f"Dein Schiff {state}", d["vehicle"],
                           self._detail(f"durch {d['cause']}", d["zone"]), feeds=BOTH, banner=True)
            elif me and d["cause"] == me:
                if d["to"] >= 2:
                    self.vehicles_destroyed += 1
                self._push(ev, "kill", f"Schiff {state}", d["vehicle"], d["zone"] or "", banner=True)
            else:
                self._push(ev, "other", f"Schiff {state}", d["vehicle"], d["zone"] or "")
        elif ev.kind == "quit":
            self.ended = True
            self._push(ev, "info", "Spiel beendet", feeds=BOTH)
        elif ev.kind == "ship":
            # Control tokens only tell us about the pilot seat. If the ship channel already told
            # us which ship we are in, leaving the seat does not mean leaving the ship.
            if d["entering"]:
                if not self._ship_from_channel and d["vehicle"] != self.ship:
                    self.ship, self.ship_since = d["vehicle"], ev.ts
                    self._push(ev, "nav", "Pilotensitz", self.ship, feeds=BOTH)
            elif not self._ship_from_channel and d["vehicle"] == self.ship:
                self.ship = None
        elif ev.kind == "quantum":
            # Quantum lines name the ship: a fallback when the boarding notification was missed
            # (dashboard started late, flying as crew).
            if d.get("ship_class"):
                self.ship_class = d["ship_class"]
            if d.get("ship") and not self.ship:
                known = ships.lookup(d.get("ship_class"))
                self.ship = known["name"] if known else d["ship"]
                self._ship_from_channel, self.ship_since = False, ev.ts
                self._push(ev, "nav", "Im Schiff", self.ship, feeds=BOTH)
            if d["phase"] == "route":
                self.quantum_fuel = d["fuel"]
                return
            if d["phase"] in ("target", "fuel"):
                if d["phase"] == "fuel" and self.quantum_target:
                    return  # fuel estimate for a target we already know
                target = self._describe_qt(d)
                self._qt_location = locate_place(d["name"]) if d["kind"] == "place" else None
                if target != self.quantum_target:
                    self.quantum_fuel = None  # a new estimate follows with the route calculation
                    self.quantum_target = target
                    if target:
                        self._push(ev, "nav", "Quantum-Ziel", target, feeds=(MISSION,))
            else:
                self.quantum_jumps += 1
                fuel = self.quantum_fuel or 0.0
                self.quantum_fuel_used += fuel
                if fuel and self.ship_class:
                    key = self.ship_class.lower()
                    self._fuel_by_ship[key] = self._fuel_by_ship.get(key, 0.0) + fuel
                self._push(ev, "nav", "Quantum-Sprung", "Ziel erreicht",
                           self._detail(self.quantum_target, self._fuel_text(fuel)), feeds=(MISSION,))
                self.quantum_target = self.quantum_fuel = None
                if self._qt_location:
                    self._set_location(ev, self._qt_location)
                self._qt_location = None
        elif ev.kind == "route_start":
            # "Projected Start Location is microTech": the game's own idea of where we are.
            # Only use it when it contradicts what we know (we moved without an inventory request).
            loc = self.location or {}
            if d["start"] not in (loc.get("place"), loc.get("planet")):
                where = locate_place(d["start"])
                if where:
                    self._set_location(ev, where)
        elif ev.kind == "version":
            self.game_version = d["version"]
        elif ev.kind == "marker":
            # keep the first marker per objective that uses planet coordinates (later ones inside
            # buildings are local); markers come a few ms *before* the contract notification
            if d["mission_id"] and is_planet_frame(d["pos"]):
                self._markers.setdefault(d["mission_id"], {}).setdefault(d["objective_id"], d["pos"])
            return
        elif ev.kind == "objective_state":
            mission = self.missions.get(d["mission_id"] or "")
            obj = mission["objectives"].get(d["objective_id"]) if mission else None
            if obj and obj["state"] != d["state"]:
                obj["state"] = d["state"]
                if d["state"] == "done":
                    self._learn_place(ev, mission["id"], d["objective_id"])
                mission["seq"] = self._event_id + 1
                self._push(ev, "success" if d["state"] == "done" else "fail",
                           "Ziel erledigt" if d["state"] == "done" else "Ziel gescheitert",
                           obj["text"], mission["title"], feeds=(MISSION,))
        elif ev.kind == "dead":
            if d["actor"] is None or me is None or d["actor"] == me:
                if d["ship_destroyed"] and d["ship"]:
                    self._register_death(ev, "Schiff zerstört", d["ship"], d["where"])
                else:
                    self._register_death(ev, "Gestorben", d["ship"] or "", d["where"])
            else:
                self._push(ev, "other", "Spieler gestorben", d["actor"], d["where"] or "")
        elif ev.kind == "corpse":
            if d["local"] and (me is None or d["player"] == me):
                self._register_death(ev, "Gestorben")
        elif ev.kind == "incap":
            if me is None or d["player"] == me:
                self._incapacitated(ev, ", ".join(d["causes"]))
        elif ev.kind == "medbed":
            if (me is None or d["actor"] == me) and d["ok"]:
                if not self._within(self._last_medbed_ts, ev.ts, MEDBED_DEDUP_SECONDS):
                    self.medbed += 1
                self._last_medbed_ts = ev.ts
                healed = {_BODY_DE.get(p, p) for p in d["parts"]}
                # a med bed visit without part list is a full treatment
                self.open_injuries = [i for i in self.open_injuries if healed and i["part"] not in healed]
                parts = ", ".join(_BODY_DE.get(p, p) for p in d["parts"]) or "Behandlung"
                self._push(ev, "success", "Med-Bed", parts, d["vehicle"] or "Krankenhaus", feeds=BOTH)
        elif ev.kind == "collision":
            self.collisions += 1
            self._push(ev, "death", "Tödliche Kollision", d["vehicle"], d["where"] or "", feeds=BOTH, banner=True)
        elif ev.kind == "cargo":
            if me is None or d["actor"] == me:
                if d["delivered"]:
                    self.cargo_delivered += 1
                    self._push(ev, "success", "Fracht abgegeben", d["item"], feeds=(MISSION,))
                else:
                    self.cargo_loaded += 1
                    self._push(ev, "mission", "Fracht verladen", d["item"], self.ship or "", feeds=(MISSION,))
        elif ev.kind == "purchase":
            self.purchases += 1
            self.spend += d["price"]
            what = f"{d['qty']}× {d['item']}" if d["qty"] > 1 else d["item"]
            self._push(ev, "info", "Gekauft", what,
                       self._detail(f"{d['price']:,.0f} aUEC".replace(",", "."), d["shop"]), feeds=(MISSION,))
        elif ev.kind == "disconnect":
            code = d["code"]
            if code == "30010" or (not d["in_pu"] and code in BENIGN_NET):
                return
            if self._within(self._last_disconnect_ts, ev.ts, 30):
                return
            self._last_disconnect_ts = ev.ts
            self.quantum_target = self._qt_location = self.quantum_fuel = None
            if code in BENIGN_NET:
                text = "wegen Inaktivität" if code == "30028" else "Server verlassen oder gewechselt"
                self._push(ev, "info", "Verbindung getrennt", text, feeds=BOTH)
            else:
                self.disconnects += 1
                self._push(ev, "fail", f"Verbindungsfehler {code}", NET_ERRORS.get(code, d["reason"]),
                           feeds=BOTH, banner=True)
        elif ev.kind == "notify":
            self._notify(ev)
        elif ev.kind == "mission_end":
            mission = self.missions.get(d["mission_id"] or "")
            if mission:
                self._end_mission(ev, mission, d["result"])
            elif d["mission_id"]:
                self._ended_missions.add(d["mission_id"])

    def _set_location(self, ev: LogEvent, loc: Dict[str, Optional[str]]) -> None:
        if loc == self.location:
            return
        self.location = loc
        self.location_since = ev.ts
        if loc["place"]:
            self.places.add(loc["place"])
        self._push(ev, "nav", "Ort", loc["place"] or "", self._detail(loc["system"], loc["planet"]), feeds=BOTH)

    def _fuel_text(self, estimate: float) -> Optional[str]:
        """The game's fuel estimate as something readable: share of the tank, or SCU if the ship is unknown."""
        if not estimate:
            return None
        pct = ships.tank_share(estimate, self._ship_data())
        if pct is not None:
            if pct < 0.1:
                return "< 0,1 % Tank"
            return (f"{pct:.1f}" if pct < 10 else f"{pct:.0f}").replace(".", ",") + " % Tank"
        scu = estimate * ships.ESTIMATE_UNIT_SCU
        return (f"{scu:.3f}" if scu < 1 else f"{scu:.1f}").replace(".", ",") + " SCU Quantum-Treibstoff"

    def _describe_qt(self, d: Dict[str, Any]) -> Optional[str]:
        if d["kind"] != "mission":
            return d["name"]
        # mission markers have no readable name - borrow it from the active objective
        for mission in sorted(self.missions.values(), key=lambda m: m["seq"], reverse=True):
            for obj in mission["objectives"].values():
                if obj["state"] == "open":
                    place = objective_place(obj["text"])
                    if place:
                        return f"Auftragsziel · {place}"
        return f"Auftragsziel · {d['name']}" if d["name"] else "Auftragsziel"

    def _incapacitated(self, ev: LogEvent, causes: str) -> None:
        if self._within(self._last_incap_ts, ev.ts, INCAP_DEDUP_SECONDS):
            return
        self._last_incap_ts = ev.ts
        self.incaps += 1
        self._push(ev, "death", "Kampfunfähig", causes or "K.O.", "Notfall-Beacon möglich", feeds=BOTH, banner=True)

    # ------------------------------------------------------------------ missions
    def _find_mission(self, mission_id: Optional[str], title: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if mission_id and mission_id in self.missions:
            return self.missions[mission_id]
        if title:
            low = title.lower()
            for m in self.missions.values():
                if m["title"].lower() == low:
                    return m
        if not mission_id and len(self.missions) == 1:
            return next(iter(self.missions.values()))
        return None

    def _mission_for_objective(self, ev: LogEvent) -> Dict[str, Any]:
        mid = ev.data["mission_id"]
        mission = self._find_mission(mid)
        if mission is None and not mid and self.missions:
            mission = next(reversed(self.missions.values()))  # most recent
        if mission is None:
            # log started in the middle of a mission
            key = mid or f"unknown-{self._event_id}"
            mission = self._new_mission(key, "Laufender Auftrag", ev.ts)
        return mission

    def _learn_place(self, ev: LogEvent, mission_id: str, objective_id: str) -> None:
        """An objective was completed here: remember which place its marker belongs to."""
        pos = self._markers.get(mission_id, {}).get(objective_id)
        if (self.place_memory is None or pos is None or not self.location
                or not self._within(self.location_since, ev.ts, PLACE_FRESH_SECONDS)):
            return
        self.place_memory.learn(pos, self.location, ev.ts)

    def _next_target(self, mission: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Where to go for the first open objective: remembered place of its marker, else its text."""
        markers = self._markers.get(mission["id"], {})
        for key, obj in mission["objectives"].items():
            if obj["state"] != "open":
                continue
            named = objective_place(obj["text"])
            known = self.place_memory.lookup(markers.get(key)) if self.place_memory is not None else None
            if known:
                extra = named if named and named.lower() not in known["place"].lower() else None
                return {"place": known["place"], "detail": extra, "learned": True}
            if named:
                return {"place": named, "detail": None, "learned": False}
        return None

    def _new_mission(self, key: str, title: str, ts: Optional[str]) -> Dict[str, Any]:
        mission = {"id": key, "title": title, "accepted": ts, "objectives": OrderedDict(), "seq": self._event_id}
        self.missions[key] = mission
        return mission

    def _end_mission(self, ev: LogEvent, mission: Dict[str, Any], result: str) -> None:
        self.missions.pop(mission["id"], None)
        if mission["id"]:
            self._ended_missions.add(mission["id"])
        if result == "completed":
            self.missions_completed += 1
        elif result == "failed":
            self.missions_failed += 1
        else:
            self.missions_abandoned += 1
        self.mission_history.appendleft({
            "title": mission["title"], "result": result, "ts": ev.ts,
            "duration": _secs_between(mission["accepted"], ev.ts),
        })
        self._push(ev, _RESULT_CAT.get(result, "other"), _RESULT_TEXT.get(result, "Auftrag beendet"),
                   mission["title"], feeds=(MISSION,), banner=result in ("completed", "failed"))

    def _notify(self, ev: LogEvent) -> None:
        d = ev.data
        cat, subject = d["category"], d["subject"]

        if cat == "accepted":
            mission = self._find_mission(d["mission_id"], subject)
            if mission is None:
                mission = self._new_mission(d["mission_id"] or f"t:{subject}", subject, ev.ts)
            else:
                mission["title"] = subject
            mission["seq"] = self._event_id + 1
            self._push(ev, "mission", "Auftrag angenommen", subject, feeds=(MISSION,), banner=True)
        elif cat in ("completed", "failed", "abandoned"):
            if d["mission_id"] in self._ended_missions:
                return  # the game reports the end up to three times (push message, EndMission, HUD)
            mission = self._find_mission(d["mission_id"], subject)
            if mission is None:
                # not tracked (e.g. accepted before the log started)
                mission = {"id": "", "title": subject, "accepted": None}
            self._end_mission(ev, mission, cat)
        elif cat in ("objective_new", "objective_done", "objective_failed"):
            mission = self._mission_for_objective(ev)
            mission["seq"] = self._event_id + 1  # most recently active mission goes first
            objectives = mission["objectives"]
            key = d["objective_id"] or subject.lower()
            state = {"objective_new": "open", "objective_done": "done", "objective_failed": "failed"}[cat]
            obj = objectives.get(key)
            if obj is None and not d["objective_id"]:
                # match by text if the log gave no objective id
                obj = next((o for o in objectives.values() if o["text"].lower() == subject.lower()), None)
            if obj is None:
                objectives[key] = {"text": subject, "state": state}
                if state == "done":
                    self._learn_place(ev, mission["id"], key)
                if key.startswith("pickup"):
                    # the game announces the drop-off first; show the pick-up on top
                    objectives.move_to_end(key, last=False)
            else:
                if obj["state"] == state and obj["text"] == subject:
                    return  # already known (e.g. via the server push message)
                if cat == "objective_new" or obj["state"] != state:
                    obj["text"] = subject if cat == "objective_new" else obj["text"]
                obj["state"] = state
            if state == "done":
                self._learn_place(ev, mission["id"], key)
            title = {"open": "Neues Ziel", "done": "Ziel erledigt", "failed": "Ziel gescheitert"}[state]
            self._push(ev, "success" if state == "done" else "fail" if state == "failed" else "mission",
                       title, subject, mission["title"], feeds=(MISSION,))
        elif cat in ("armistice_on", "armistice_off"):
            self.armistice = cat == "armistice_on"
            self._push(ev, "zone", "Zone", "Armistice betreten" if self.armistice else "Armistice verlassen",
                       "Waffen gesperrt" if self.armistice else "Waffen frei", feeds=BOTH)
        elif cat in ("monitored_on", "monitored_off"):
            self.monitored = cat == "monitored_on"
            self._push(ev, "zone", "Zone", "Überwachter Raum" if self.monitored else "Unüberwachter Raum",
                       "Comm-Array aktiv" if self.monitored else "kein Comm-Array in Reichweite",
                       feeds=BOTH)
        elif cat in ("crew_joined", "crew_left"):
            who = subject
            if cat == "crew_joined":
                if who not in self.crew:
                    self.crew.append(who)
                self._push(ev, "nav", "An Bord gekommen", who, d.get("ship") or "", feeds=BOTH)
            else:
                self.crew = [c for c in self.crew if c != who]
                self._push(ev, "nav", "Von Bord gegangen", who, d.get("ship") or "", feeds=BOTH)
        elif cat in ("channel_joined", "channel_left"):
            if not d.get("is_ship"):
                self._push(ev, "comms", "Kanal", d["text"], feeds=(MISSION,))
            elif cat == "channel_joined":
                if subject != self.ship:
                    self.ship_class = None  # a different ship - the class follows with the next quantum line
                self.ship, self._ship_from_channel, self.ship_since = subject, True, ev.ts
                self._push(ev, "nav", "Eingestiegen", subject, feeds=BOTH)
            elif self.ship == subject or not self._ship_from_channel:
                self.ship, self._ship_from_channel = None, False
                self.crew = []
                self._push(ev, "nav", "Ausgestiegen", subject, feeds=(MISSION,))
        elif cat == "incapacitated":
            self._incapacitated(ev, subject if subject != d["text"] else "")
        elif cat == "rescue":
            self._push(ev, "warn", "Rettung", "Notfalldienste unterwegs", feeds=(COMBAT,))
        elif cat == "injury":
            self.injuries += 1
            sev = _INJURY_DE.get(d["sev"].lower(), d["sev"].capitalize())
            severe = d["sev"].lower() in ("major", "severe", "critical")
            part = d["part"].strip()
            part_de = _PART_DE.get(part.lower(), part)
            self.open_injuries = [i for i in self.open_injuries if i["part"] != part_de]
            self.open_injuries.append({"part": part_de, "severity": sev, "tier": int(d["tier"]), "severe": severe})
            self._push(ev, "death" if severe else "warn", f"{sev} Verletzung", _PART_DE.get(part.lower(), part),
                       f"Tier-{d['tier']}-Behandlung nötig", feeds=BOTH)
        elif cat in ("crime_up", "crime"):
            self.crimestat += 1 if cat == "crime_up" else 0
            self._push(ev, "fail", "CrimeStat erhöht" if cat == "crime_up" else "Straftat",
                       "" if cat == "crime_up" else subject, feeds=BOTH, banner=cat == "crime_up")
        elif cat == "crime_against":
            self._push(ev, "warn", "Straftat gegen dich", d["who"], f"{d['what']} – vergeben oder melden", feeds=BOTH)
        elif cat == "fined":
            self.fines += d["amount"]
            self._push(ev, "fail", "Strafe", f"{d['amount']:,} UEC".replace(",", "."), feeds=BOTH)
        elif cat == "impounded":
            self._push(ev, "fail", "Schiff beschlagnahmt", subject, feeds=BOTH, banner=True)
        elif cat == "money_received":
            self.money_in += d["amount"]
            self._push(ev, "success", "Geld erhalten", f"{d['amount']:,} aUEC".replace(",", "."), f"von {d['who']}",
                       feeds=(MISSION,))
        elif cat == "money_sent":
            self.money_out += d["amount"]
            self._push(ev, "info", "Geld gesendet", f"{d['amount']:,} aUEC".replace(",", "."), f"an {d['who']}",
                       feeds=(MISSION,))
        elif cat == "refinery":
            self._push(ev, "success", "Raffinerie fertig", d["where"].strip(), feeds=(MISSION,), banner=True)
        elif cat == "rewards":
            self._push(ev, "success", "Belohnungen", f"{d['amount']} erhalten", "im Heimatort abholen", feeds=(MISSION,))
        elif cat == "blueprint":
            self._push(ev, "success", "Blueprint erhalten", subject, feeds=(MISSION,))
        elif cat == "low_fuel":
            self._push(ev, "warn", "Treibstoff knapp", feeds=BOTH)
        elif cat in ("restricted_on", "restricted_off"):
            self.restricted = cat == "restricted_on"
            if self.restricted:
                self._push(ev, "warn", "Sperrgebiet", "Fahrzeuge werden beschlagnahmt", feeds=BOTH, banner=True)
        elif cat in ("private_on", "private_off"):
            self.private = cat == "private_on"
            self._push(ev, "zone", "Zone", "Privatgelände betreten" if self.private else "Privatgelände verlassen",
                       feeds=(MISSION,))
        elif cat == "monitored_down":
            self.monitored = False
            self._push(ev, "zone", "Zone", "Überwachung ausgefallen", "Comm-Array offline", feeds=BOTH)
        elif cat == "shared":
            self._push(ev, "comms", "Auftrag geteilt", subject, feeds=(MISSION,))
        elif cat == "qt_blocked":
            self._push(ev, "warn", "Quantum blockiert", "Ziel verdeckt", "erst woandershin fliegen", feeds=BOTH)
        elif cat == "medbed_restored":
            if not self._within(self._last_medbed_ts, ev.ts, MEDBED_DEDUP_SECONDS):
                self.medbed += 1
                self._push(ev, "success", "Med-Bed", "Gesundheit wiederhergestellt",
                           "Verletzungen im Behandlungs-Tab heilen" if self.open_injuries else "", feeds=BOTH)
            self._last_medbed_ts = ev.ts
        elif cat == "tip":
            return  # tutorial hint - shown in the game anyway, no value on the dashboard
        elif cat == "hangar":
            self._push(ev, "nav", "Hangar bereit", feeds=(MISSION,))
        elif cat == "transaction":
            self._push(ev, "comms", "Transaktion abgeschlossen", feeds=(MISSION,))
        elif cat == "available":
            self._push(ev, "comms", "Auftrag verfügbar", subject, feeds=(MISSION,))
        elif cat == "jurisdiction":
            if subject == self.jurisdiction:
                return
            if self.jurisdiction and ev.ts:
                self._jur_left[self.jurisdiction] = ev.ts
            self.jurisdiction = subject
            if self._within(self._jur_left.get(subject), ev.ts, JURISDICTION_FLAP_SECONDS):
                return  # ping-pong at a border
            lawless = subject.lower() == "ungoverned"
            self._push(ev, "warn" if lawless else "zone", "Jurisdiktion", subject,
                       "gesetzloser Raum" if lawless else "", feeds=(MISSION,))
        else:
            self._push(ev, "comms", "Meldung", d["text"], feeds=(MISSION,))

    # ------------------------------------------------------------------ reading
    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    @property
    def token(self) -> str:
        """Changes whenever the state changes (or the server was restarted)."""
        with self._lock:
            return f"{self._boot}-{self._version}"

    def _ship_data(self) -> Optional[Dict[str, Any]]:
        if not self.ship:
            return None
        return ships.lookup(self.ship_class, self.ship)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            ship = self._ship_data()
            flown = self._fuel_by_ship.get((ship or {}).get("class", "").lower(), 0.0) if ship else 0.0
            return {
                "version": self._version,
                "token": f"{self._boot}-{self._version}",
                "server_time": time.time(),
                "log": {"path": self.log_path, "found": self.log_found},
                "game_running": self.game_running,
                "session": {
                    "handle": self.handle,
                    "shard": self.shard,
                    "region": shard_region(self.shard),
                    "server": self.shard.rsplit("_", 1)[-1] if self.shard and "_" in self.shard else None,
                    "location": self.location,
                    "location_since": self.location_since,
                    "start": self.session_start,
                    "last_log": self.last_log_ts,
                    "alive_since": self.alive_since,
                    "last_killer": self.last_killer,
                    "last_death": self.last_death,
                    "ended": self.ended,
                },
                "stats": {
                    "kills": self.kills,
                    "npc_kills": self.npc_kills,
                    "deaths": self.deaths,
                    "vehicles_lost": self.vehicles_lost,
                    "vehicles_destroyed": self.vehicles_destroyed,
                    "streak": self.streak,
                    "best_streak": self.best_streak,
                    "missions_completed": self.missions_completed,
                    "missions_failed": self.missions_failed,
                    "missions_abandoned": self.missions_abandoned,
                    "places": len(self.places),
                    "quantum_jumps": self.quantum_jumps,
                    "quantum_fuel_used": round(self.quantum_fuel_used, 1),
                    "incaps": self.incaps,
                    "injuries": self.injuries,
                    "medbed": self.medbed,
                    "collisions": self.collisions,
                    "crimestat": self.crimestat,
                    "fines": self.fines,
                    "money_in": self.money_in,
                    "money_out": self.money_out,
                    "best_alive": self.best_alive,
                    "spend": round(self.spend),
                    "purchases": self.purchases,
                    "cargo_loaded": self.cargo_loaded,
                    "cargo_delivered": self.cargo_delivered,
                    "disconnects": self.disconnects,
                },
                "health": {"injuries": list(self.open_injuries)},
                "nav": {
                    "ship": self.ship,
                    "armistice": self.armistice,
                    "monitored": self.monitored,
                    "jurisdiction": self.jurisdiction,
                    "ship_since": self.ship_since if self.ship else None,
                    "ship_info": ships.public_info(ship),
                    # share of the quantum tank: the planned route, and what this ship flew this session
                    "quantum_need_pct": ships.tank_share(self.quantum_fuel, ship) if self.quantum_target else None,
                    "quantum_used_pct": ships.tank_share(flown, ship),
                    "quantum_target": self.quantum_target,
                    "quantum_fuel": self.quantum_fuel if self.quantum_target else None,
                    "crew": list(self.crew),
                    "restricted": self.restricted,
                    "private": self.private,
                },
                "game_version": self.game_version,
                "missions": {
                    "active": [
                        {
                            "id": m["id"], "title": m["title"], "accepted": m["accepted"],
                            "objectives": list(m["objectives"].values()),
                            # where to go next: remembered place of the marker, else the place in the text
                            "next": self._next_target(m),
                        }
                        for m in sorted(self.missions.values(), key=lambda m: m["seq"], reverse=True)
                    ],
                    "history": list(self.mission_history),
                },
                "feeds": {k: list(v) for k, v in self.feeds.items()},
                "rsi_status": self.rsi_status,
            }
