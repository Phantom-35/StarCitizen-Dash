"""Locating the Star Citizen log file and a browser to show the dashboard in."""

from __future__ import annotations

import os
import string
import sys
from typing import Iterable, List, Optional

CHANNELS = ("LIVE", "PTU", "EPTU", "TECH-PREVIEW", "HOTFIX")

# Install roots relative to a drive letter (Windows) – the RSI launcher default
# plus a few layouts people commonly choose.
_ROOTS = (
    r"Program Files\Roberts Space Industries\StarCitizen",
    r"Roberts Space Industries\StarCitizen",
    r"Games\Roberts Space Industries\StarCitizen",
    r"StarCitizen",
    r"Games\StarCitizen",
)


def _drives() -> List[str]:
    if sys.platform != "win32":
        return []
    return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]


def candidate_logs() -> Iterable[str]:
    for drive in _drives():
        for root in _ROOTS:
            for channel in CHANNELS:
                yield os.path.join(drive, root, channel, "Game.log")


def resolve_log(user_path: Optional[str]) -> Optional[str]:
    """Return the Game.log to watch.

    * explicit file -> used as is
    * explicit directory -> ``<dir>/Game.log``
    * nothing -> most recently modified Game.log among the known install paths
    """
    if user_path:
        p = os.path.expandvars(os.path.expanduser(user_path))
        if os.path.isdir(p):
            p = os.path.join(p, "Game.log")
        return p

    best, best_mtime = None, -1.0
    for cand in candidate_logs():
        try:
            mtime = os.path.getmtime(cand)
        except OSError:
            continue
        if mtime > best_mtime:
            best, best_mtime = cand, mtime
    return best


def find_chromium_browser() -> Optional[str]:
    """Find Edge or Chrome – both support app mode and ``--disable-gpu``."""
    if sys.platform == "win32":
        bases = [os.environ.get(v) for v in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        rel = (
            r"Microsoft\Edge\Application\msedge.exe",
            r"Google\Chrome\Application\chrome.exe",
            r"BraveSoftware\Brave-Browser\Application\brave.exe",
        )
        for r in rel:
            for b in bases:
                if b and os.path.isfile(os.path.join(b, r)):
                    return os.path.join(b, r)
        return None
    from shutil import which

    for name in ("chromium", "chromium-browser", "google-chrome", "microsoft-edge", "brave-browser"):
        exe = which(name)
        if exe:
            return exe
    return None


def browser_profile_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "scdash", "browser-profile")
