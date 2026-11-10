"""Thread-safe dashboard state shared between the watchers and the HTTP server."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Dict, Optional

from scdash.locations import shard_region
from scdash.parser import LogEvent

MAX_EVENTS = 40


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
        self.events: deque = deque(maxlen=MAX_EVENTS)

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

    def _push(self, ev: LogEvent, cat: str, title: str, actor: str = "", detail: str = "") -> None:
        self._event_id += 1
        self.events.appendleft(
            {"id": self._event_id, "ts": ev.ts, "cat": cat, "title": title, "actor": actor, "detail": detail}
        )

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
                self._push(ev, "info", "Eingeloggt", self.handle)
        elif ev.kind == "join":
            self.shard = d["shard"]
            self._push(ev, "info", "Shard beigetreten", shard_region(self.shard) or "", self.shard)
        elif ev.kind == "location":
            loc = d["location"]
            if loc != self.location:
                self.location = loc
                self.location_since = ev.ts
                self._push(ev, "nav", "Ort", loc["place"] or "", self._detail(loc["system"], loc["planet"]))
        elif ev.kind == "death":
            victim, killer = d["victim"], d["killer"]
            detail = self._detail(d["weapon"], d["zone"])
            if me and victim == me:
                self._died(ev.ts)
                if killer == me or killer.lower() == "unknown":
                    self.suicides += 1
                    self._push(ev, "death", "Gestorben", d["damage"] or "Unfall", d["zone"] or "")
                else:
                    self.deaths += 1
                    who = "NPC" if d["killer_npc"] else killer
                    self.last_killer = {"name": who, "weapon": d["weapon"], "ts": ev.ts}
                    self._push(ev, "death", "Getötet von", who, detail)
            elif me and killer == me:
                self.streak += 1
                self.best_streak = max(self.best_streak, self.streak)
                if d["victim_npc"]:
                    self.npc_kills += 1
                    self._push(ev, "kill", "NPC eliminiert", "", detail)
                else:
                    self.kills += 1
                    self._push(ev, "kill", "Eliminiert", victim, detail)
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
                self._push(ev, "death", f"Dein Schiff {state}", d["vehicle"], self._detail(f"durch {d['cause']}", d["zone"]))
            elif me and d["cause"] == me:
                if d["to"] >= 2:
                    self.vehicles_destroyed += 1
                self._push(ev, "kill", f"Schiff {state}", d["vehicle"], d["zone"] or "")
            else:
                self._push(ev, "other", f"Schiff {state}", d["vehicle"], d["zone"] or "")
        elif ev.kind == "quit":
            self.ended = True
            self._push(ev, "info", "Spiel beendet")

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
                },
                "events": list(self.events),
                "rsi_status": self.rsi_status,
            }
