"""Thread-safe dashboard state shared between the watchers and the HTTP server."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from scdash.locations import shard_region
from scdash.parser import LogEvent

MAX_EVENTS = 40
MAX_HISTORY = 12

COMBAT, MISSION = "combat", "mission"
BOTH = (COMBAT, MISSION)

_RESULT_TEXT = {"completed": "Auftrag erledigt", "failed": "Auftrag gescheitert", "abandoned": "Auftrag abgebrochen"}
_RESULT_CAT = {"completed": "success", "failed": "fail", "abandoned": "other"}


def _secs_between(a: Optional[str], b: Optional[str]) -> Optional[float]:
    try:
        fa = datetime.fromisoformat(a.replace("Z", "+00:00"))  # type: ignore[union-attr]
        fb = datetime.fromisoformat(b.replace("Z", "+00:00"))  # type: ignore[union-attr]
        return max(0.0, (fb - fa).total_seconds())
    except (AttributeError, ValueError):
        return None


class DashboardState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
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
        self.suicides = 0
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

    def _touch(self) -> None:
        self._version += 1

    # ------------------------------------------------------------------ mutators
    def new_session(self) -> None:
        """Called when Game.log was recreated (game restarted)."""
        with self._lock:
            self._reset_session()
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
        self.alive_since = ts

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
            self._push(ev, "info", "Shard beigetreten", shard_region(self.shard) or "", self.shard, feeds=BOTH)
        elif ev.kind == "location":
            loc = d["location"]
            if loc != self.location:
                self.location = loc
                self.location_since = ev.ts
                if loc["place"]:
                    self.places.add(loc["place"])
                self._push(ev, "nav", "Ort", loc["place"] or "", self._detail(loc["system"], loc["planet"]), feeds=BOTH)
        elif ev.kind == "death":
            victim, killer = d["victim"], d["killer"]
            detail = self._detail(d["weapon"], d["zone"])
            if me and victim == me:
                self._died(ev.ts)
                if killer == me or killer.lower() == "unknown":
                    self.suicides += 1
                    self._push(ev, "death", "Gestorben", d["damage"] or "Unfall", d["zone"] or "", feeds=BOTH, banner=True)
                else:
                    self.deaths += 1
                    who = "NPC" if d["killer_npc"] else killer
                    self.last_killer = {"name": who, "weapon": d["weapon"], "ts": ev.ts}
                    self._push(ev, "death", "Getötet von", who, detail, feeds=BOTH, banner=True)
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
            if d["entering"]:
                if d["vehicle"] != self.ship:
                    self.ship = d["vehicle"]
                    self._push(ev, "nav", "Pilotensitz", self.ship, feeds=BOTH)
            elif d["vehicle"] == self.ship:
                self.ship = None
        elif ev.kind == "notify":
            self._notify(ev)
        elif ev.kind == "mission_end":
            mission = self.missions.get(d["mission_id"] or "")
            if mission:
                self._end_mission(ev, mission, d["result"])

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

    def _new_mission(self, key: str, title: str, ts: Optional[str]) -> Dict[str, Any]:
        mission = {"id": key, "title": title, "accepted": ts, "objectives": OrderedDict(), "seq": self._event_id}
        self.missions[key] = mission
        return mission

    def _end_mission(self, ev: LogEvent, mission: Dict[str, Any], result: str) -> None:
        self.missions.pop(mission["id"], None)
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
            else:
                obj["state"] = state
                if cat == "objective_new":
                    obj["text"] = subject
            title = {"open": "Neues Ziel", "done": "Ziel erledigt", "failed": "Ziel gescheitert"}[state]
            self._push(ev, "success" if state == "done" else "fail" if state == "failed" else "mission",
                       title, subject, mission["title"], feeds=(MISSION,))
        elif cat in ("armistice_on", "armistice_off"):
            self.armistice = cat == "armistice_on"
            self._push(ev, "zone", "Armistice-Zone", "betreten" if self.armistice else "verlassen",
                       "" if self.armistice else "Waffen frei", feeds=BOTH)
        elif cat in ("monitored_on", "monitored_off"):
            self.monitored = cat == "monitored_on"
            self._push(ev, "zone", "Überwachter Raum" if self.monitored else "Unüberwachter Raum",
                       "betreten", "Comm-Array aktiv" if self.monitored else "keine CrimeStat-Meldung",
                       feeds=BOTH)
        elif cat == "jurisdiction":
            self.jurisdiction = subject
            self._push(ev, "zone", "Jurisdiktion", subject, feeds=(MISSION,))
        else:
            self._push(ev, "comms", "Meldung", d["text"], feeds=(MISSION,))

    # ------------------------------------------------------------------ reading
    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": self._version,
                "server_time": time.time(),
                "log": {"path": self.log_path, "found": self.log_found},
                "game_running": self.game_running,
                "session": {
                    "handle": self.handle,
                    "shard": self.shard,
                    "region": shard_region(self.shard),
                    "location": self.location,
                    "location_since": self.location_since,
                    "start": self.session_start,
                    "last_log": self.last_log_ts,
                    "alive_since": self.alive_since,
                    "last_killer": self.last_killer,
                    "ended": self.ended,
                },
                "stats": {
                    "kills": self.kills,
                    "npc_kills": self.npc_kills,
                    "deaths": self.deaths,
                    "suicides": self.suicides,
                    "vehicles_lost": self.vehicles_lost,
                    "vehicles_destroyed": self.vehicles_destroyed,
                    "streak": self.streak,
                    "best_streak": self.best_streak,
                    "missions_completed": self.missions_completed,
                    "missions_failed": self.missions_failed,
                    "missions_abandoned": self.missions_abandoned,
                    "places": len(self.places),
                },
                "nav": {
                    "ship": self.ship,
                    "armistice": self.armistice,
                    "monitored": self.monitored,
                    "jurisdiction": self.jurisdiction,
                },
                "missions": {
                    "active": [
                        {
                            "id": m["id"], "title": m["title"], "accepted": m["accepted"],
                            "objectives": list(m["objectives"].values()),
                        }
                        for m in sorted(self.missions.values(), key=lambda m: m["seq"], reverse=True)
                    ],
                    "history": list(self.mission_history),
                },
                "feeds": {k: list(v) for k, v in self.feeds.items()},
                "rsi_status": self.rsi_status,
            }
