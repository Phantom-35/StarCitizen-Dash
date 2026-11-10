"""Polls the public RSI status page (cState JSON API) every few minutes."""

from __future__ import annotations

import json
import logging
import ssl
import threading
import time
import urllib.request
from typing import Any, Dict, Optional

from scdash import __version__
from scdash.state import DashboardState

log = logging.getLogger(__name__)

STATUS_URL = "https://status.robertsspaceindustries.com/index.json"
STATUS_PAGE = "https://status.robertsspaceindustries.com/"


def parse_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    systems = []
    for s in payload.get("systems", []) or []:
        systems.append(
            {
                "name": s.get("name", "?"),
                "status": s.get("status", "unknown"),
                "issues": len(s.get("unresolvedIssues") or []),
            }
        )
    return {
        "summary": payload.get("summaryStatus", "unknown"),
        "systems": systems,
        "checked": time.time(),
        "url": STATUS_PAGE,
        "error": None,
    }


def fetch_status(timeout: float = 10.0) -> Dict[str, Any]:
    req = urllib.request.Request(STATUS_URL, headers={"User-Agent": f"SC-Dash/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        return parse_status(json.loads(resp.read().decode("utf-8")))


class StatusPoller(threading.Thread):
    def __init__(self, state: DashboardState, interval: float = 300.0) -> None:
        super().__init__(name="scdash-status", daemon=True)
        self.state = state
        self.interval = interval
        self._halt = threading.Event()
        self._last_ok: Optional[Dict[str, Any]] = None

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                self._last_ok = fetch_status()
                self.state.set_rsi_status(self._last_ok)
            except Exception as exc:  # network errors are expected sometimes
                log.info("RSI-Status nicht abrufbar: %s", exc)
                fallback = dict(self._last_ok or {"summary": "unknown", "systems": [], "url": STATUS_PAGE})
                fallback["error"] = "Status derzeit nicht abrufbar"
                self.state.set_rsi_status(fallback)
            self._halt.wait(self.interval)
