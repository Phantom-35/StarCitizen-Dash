"""Thread-safe dashboard state shared between the watchers and the HTTP server."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Dict, Optional

from scdash.parser import LogEvent

MAX_EVENTS = 40


class DashboardState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
        self.log_path: Optional[str] = None
        self.log_found = False
        self.game_running: Optional[bool] = None  # None = unknown
        self.rsi_status: Optional[Dict[str, Any]] = None
        self._reset_session()

    # ------------------------------------------------------------------ helpers
    def _reset_session(self) -> None:
        self.handle: Optional[str] = None
        self.shard: Optional[str] = None
        self.location: Optional[str] = None
        self.session_start: Optional[str] = None
        self.last_log_ts: Optional[str] = None
        self.kills = 0
        self.npc_kills = 0
        self.deaths = 0
        self.suicides = 0
        self.vehicles_lost = 0
        self.vehicles_destroyed = 0
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

    def _push(self, ev: LogEvent, category: str, text: str) -> None:
        self.events.appendleft({"ts": ev.ts, "kind": ev.kind, "cat": category, "text": text})

    def _apply(self, ev: LogEvent) -> None:
        if ev.ts:
            if self.session_start is None:
                self.session_start = ev.ts
            self.last_log_ts = ev.ts
        d = ev.data
        me = self.handle

        if ev.kind == "login":
            if d["handle"] != self.handle:
                self.handle = d["handle"]
                self._push(ev, "info", f"Eingeloggt als {self.handle}")
        elif ev.kind == "join":
            self.shard = d["shard"]
            self._push(ev, "info", f"Shard beigetreten: {self.shard}")
        elif ev.kind == "location":
            if d["location"] != self.location:
                self.location = d["location"]
                self._push(ev, "info", f"Ort: {self.location}")
        elif ev.kind == "death":
            victim, killer = d["victim"], d["killer"]
            where = f" in {d['zone']}" if d["zone"] else ""
            weapon = f" ({d['weapon']})" if d["weapon"] and d["weapon"].lower() != "unknown" else ""
            if me and victim == me:
                if killer == me or killer.lower() == "unknown":
                    self.suicides += 1
                    self._push(ev, "death", f"Gestorben ({d['damage']}){where}")
                else:
                    self.deaths += 1
                    who = "NPC" if d["killer_npc"] else killer
                    self._push(ev, "death", f"Getötet von {who}{weapon}{where}")
            elif me and killer == me:
                if d["victim_npc"]:
                    self.npc_kills += 1
                    self._push(ev, "kill", f"NPC eliminiert{weapon}{where}")
                else:
                    self.kills += 1
                    self._push(ev, "kill", f"{victim} eliminiert{weapon}{where}")
            else:
                self._push(ev, "other", f"{victim} getötet von {killer}{weapon}")
        elif ev.kind == "vehicle":
            # destroy level 1 = soft death / disabled, 2 = fully destroyed
            if d["to"] < 1:
                return
            state = "zerstört" if d["to"] >= 2 else "außer Gefecht"
            if me and d["driver"] == me:
                if d["to"] >= 2:
                    self.vehicles_lost += 1
                self._push(ev, "death", f"Dein Schiff {d['vehicle']} {state} (durch {d['cause']})")
            elif me and d["cause"] == me:
                if d["to"] >= 2:
                    self.vehicles_destroyed += 1
                self._push(ev, "kill", f"{d['vehicle']} {state}")
            else:
                self._push(ev, "other", f"{d['vehicle']} {state}")
        elif ev.kind == "quit":
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
                    "location": self.location,
                    "start": self.session_start,
                    "last_log": self.last_log_ts,
                },
                "stats": {
                    "kills": self.kills,
                    "npc_kills": self.npc_kills,
                    "deaths": self.deaths,
                    "suicides": self.suicides,
                    "vehicles_lost": self.vehicles_lost,
                    "vehicles_destroyed": self.vehicles_destroyed,
                },
                "events": list(self.events),
                "rsi_status": self.rsi_status,
            }
