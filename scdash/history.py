"""Session history: one summary per game session, kept between dashboard starts.

A session is identified by its start time (first line of the Game.log), so reading the same log
again - dashboard restarted mid-session, or started after the game was closed - updates the
existing entry instead of adding a second one. The summary is saved periodically while playing,
so a crash of the game or the PC loses at most a few seconds.

Stored in ``<data_dir>/sessions.json``; nothing leaves the PC.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

MAX_SESSIONS = 500
MIN_SECONDS = 60          # shorter "sessions" (e.g. the launcher's crash restarts) are not kept
SAVE_INTERVAL = 30.0      # seconds between saves while playing

#: numbers summed up for "last 7 days" / "all time"
TOTAL_KEYS = ("seconds", "missions_completed", "missions_failed", "missions_abandoned", "deaths", "incaps",
              "quantum_jumps", "places", "balance", "pay", "spend", "fines", "money_in", "money_out")


def balance(s: Dict[str, Any]) -> int:
    """Same formula as the dashboard: entered contract pay + transfers - purchases - fines."""
    return int(round(s.get("pay", 0) + s.get("money_in", 0) - s.get("spend", 0) - s.get("money_out", 0)
                     - s.get("fines", 0)))


class SessionHistory:
    def __init__(self, path: Optional[str]) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._sessions: List[Dict[str, Any]] = []
        if path:
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                self._sessions = [s for s in data.get("sessions", []) if isinstance(s, dict) and s.get("start")]
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as exc:
                log.warning("Session-Verlauf nicht lesbar (%s) – starte leer", exc)

    def __len__(self) -> int:
        return len(self._sessions)

    def record(self, summary: Optional[Dict[str, Any]]) -> bool:
        """Insert or update the session with the same start time. Returns True if something changed."""
        if not summary or not summary.get("start") or summary.get("seconds", 0) < MIN_SECONDS:
            return False
        summary = dict(summary, balance=balance(summary))
        with self._lock:
            for i, s in enumerate(self._sessions):
                if s["start"] == summary["start"]:
                    if s == summary:
                        return False
                    self._sessions[i] = summary
                    break
            else:
                self._sessions.append(summary)
                self._sessions.sort(key=lambda s: s["start"])
                del self._sessions[:-MAX_SESSIONS]
            self._save()
        return True

    def sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            # balance is always recalculated, so an older file or a changed formula cannot mislead
            return [dict(s, balance=balance(s)) for s in self._sessions]

    def view(self, now_iso: str, limit: int = 30) -> Dict[str, Any]:
        """Newest sessions first plus totals for the last 7 days and all time."""
        from scdash.state import _secs_between

        items = self.sessions()
        week = [s for s in items if (_secs_between(s["start"], now_iso) or 0) <= 7 * 86400]
        return {
            "sessions": list(reversed(items))[:limit],
            "count": len(items),
            "week": _totals(week),
            "all": _totals(items),
        }

    def _save(self) -> None:
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "sessions": self._sessions}, fh, ensure_ascii=False, indent=0)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("Session-Verlauf nicht speicherbar: %s", exc)


def _totals(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {k: 0 for k in TOTAL_KEYS}
    for s in items:
        for k in TOTAL_KEYS:
            out[k] += s.get(k, 0) or 0
    out["sessions"] = len(items)
    out["seconds"] = round(out["seconds"])
    return out


class HistorySaver(threading.Thread):
    """Saves the running session every ``interval`` seconds (only when something changed)."""

    def __init__(self, state, interval: float = SAVE_INTERVAL) -> None:
        super().__init__(name="scdash-history", daemon=True)
        self.state = state
        self.interval = interval
        self._halt = threading.Event()

    def stop(self) -> None:
        self._halt.set()
        try:
            self.state.save_history()
        except Exception:
            log.debug("Session-Verlauf beim Beenden nicht gespeichert", exc_info=True)

    def run(self) -> None:
        while not self._halt.wait(self.interval):
            try:
                self.state.save_history()
            except Exception:
                log.exception("Session-Verlauf nicht gespeichert")
