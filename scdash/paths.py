"""Locating the Star Citizen log file and a browser to show the dashboard in."""

from __future__ import annotations

import os
import re
import string
import sys
from typing import Iterable, List, Optional

CHANNELS = ("LIVE", "PTU", "EPTU", "TECH-PREVIEW", "HOTFIX")

# Install roots relative to a drive letter (Windows) – the RSI launcher default
# plus a few layouts people commonly choose.
_ROOTS = (
    r"Program Files\Roberts Space Industries\StarCitizen",
    r"Program Files (x86)\Roberts Space Industries\StarCitizen",
    r"SteamLibrary\StarCitizen",
    r"Roberts Space Industries\StarCitizen",
    r"Games\Roberts Space Industries\StarCitizen",
    r"StarCitizen",
    r"Games\StarCitizen",
)


def _drives() -> List[str]:
    if sys.platform != "win32":
        return []
    return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]


_LAUNCHER_PATH = re.compile(r'([A-Za-z]:(?:\\\\|\\|/)[^"\'<>|\r\n]*?StarCitizen)(?=[\\/"\'\s]|$)')


def launcher_install_roots() -> List[str]:
    """Install folders mentioned in the RSI Launcher's own log (exact even for custom paths)."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    roots: List[str] = []
    for rel in (("rsilauncher", "logs", "log.log"), ("rsilauncher", "log.log")):
        try:
            with open(os.path.join(appdata, *rel), "rb") as fh:
                fh.seek(0, os.SEEK_END)
                fh.seek(max(0, fh.tell() - 3_000_000))
                text = fh.read().decode("utf-8", errors="replace")
        except OSError:
            continue
        for m in _LAUNCHER_PATH.finditer(text):
            root = os.path.normpath(m.group(1).replace("\\\\", "\\"))
            if root.lower() not in (r.lower() for r in roots):
                roots.append(root)
    return roots


def candidate_logs() -> Iterable[str]:
    bases = launcher_install_roots()
    for drive in _drives():
        bases.extend(os.path.join(drive, root) for root in _ROOTS)
    for base in bases:
        yield os.path.join(base, "Game.log")
        for channel in CHANNELS:
            yield os.path.join(base, channel, "Game.log")


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
