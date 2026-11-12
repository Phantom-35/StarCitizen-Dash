"""Checks GitHub for a newer SC-Dash release (a few times a day, nothing is sent but the request).

Releases are created automatically when a new version reaches the main branch
(``.github/workflows/release.yml``). ``update.bat`` installs the newest one.
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import threading
import urllib.request
from typing import Any, Dict, Optional, Tuple

from scdash import __version__

log = logging.getLogger(__name__)

REPO = "Phantom-35/StarCitizen-Dash"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
CHECK_INTERVAL = 6 * 3600.0
RETRY_INTERVAL = 30 * 60.0


def parse_version(text: Optional[str]) -> Optional[Tuple[int, ...]]:
    """'v0.10.0' / '0.10.0' -> (0, 10, 0); anything else -> None."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?", (text or "").strip())
    if not m:
        return None
    return tuple(int(g or 0) for g in m.groups())


def newer_release(payload: Dict[str, Any], current: str = __version__) -> Optional[Dict[str, Any]]:
    """The release from the GitHub API if it is newer than ``current``, else None."""
    if payload.get("draft") or payload.get("prerelease"):
        return None
    latest, mine = parse_version(payload.get("tag_name")), parse_version(current)
    if not latest or not mine or latest <= mine:
        return None
    url = payload.get("html_url") or RELEASES_PAGE
    if not str(url).startswith(f"https://github.com/{REPO}/"):
        url = RELEASES_PAGE
    return {"version": ".".join(map(str, latest)), "current": current, "url": url}


def fetch_latest(timeout: float = 10.0) -> Dict[str, Any]:
    req = urllib.request.Request(LATEST_URL, headers={"User-Agent": f"SC-Dash/{__version__}",
                                                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


class UpdateChecker(threading.Thread):
    def __init__(self, state, interval: float = CHECK_INTERVAL) -> None:
        super().__init__(name="scdash-update", daemon=True)
        self.state = state
        self.interval = interval
        self._halt = threading.Event()

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        # a little later than the start, the dashboard window and the log come first
        if self._halt.wait(20):
            return
        while not self._halt.is_set():
            wait = self.interval
            try:
                update = newer_release(fetch_latest())
                self.state.set_update(update)
                if update:
                    log.info("Neue Version verfügbar: %s (installiert: %s) – update.bat ausführen",
                             update["version"], __version__)
            except Exception as exc:  # no internet, GitHub limit, no release yet (404)
                log.debug("Update-Prüfung nicht möglich: %s", exc)
                wait = RETRY_INTERVAL
            self._halt.wait(wait)
