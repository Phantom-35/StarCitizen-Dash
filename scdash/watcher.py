"""Background threads: Game.log tailer and game-process detector.

Both are polling based on purpose – polling a file once per second costs
practically nothing and avoids any platform-specific file-notification APIs.
The log file is opened only briefly on every poll so we never hold a handle
that could get in the way of the game rotating its log on the next start.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
from typing import Callable, Optional

from scdash.parser import parse_line
from scdash.state import DashboardState

log = logging.getLogger(__name__)

# Do not parse more than this on startup if the log is huge.
INITIAL_READ_LIMIT = 8 * 1024 * 1024


class LogWatcher(threading.Thread):
    def __init__(
        self,
        path_resolver: Callable[[], Optional[str]],
        state: DashboardState,
        interval: float = 1.0,
    ) -> None:
        super().__init__(name="scdash-log", daemon=True)
        self._resolve = path_resolver
        self.state = state
        self.interval = interval
        self._halt = threading.Event()
        self._path: Optional[str] = None
        self._identity = None
        self._offset = 0
        self._remainder = b""

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                self.poll()
            except Exception:  # never let the thread die
                log.exception("Fehler beim Lesen der Game.log")
            self._halt.wait(self.interval)

    # Separate method so tests can drive it synchronously.
    def poll(self) -> None:
        path = self._resolve()
        if not path or not os.path.isfile(path):
            self.state.set_log(path, False)
            return
        self.state.set_log(path, True)

        st = os.stat(path)
        identity = (path, st.st_dev, st.st_ino)
        if identity != self._identity or st.st_size < self._offset:
            # New file (game restarted) or log was truncated -> new session.
            if self._identity is not None:
                log.info("Neue Game.log erkannt – Session wird zurückgesetzt")
            self.state.new_session()
            self._identity = identity
            self._remainder = b""
            self._offset = max(0, st.st_size - INITIAL_READ_LIMIT)
            if self._offset:
                self._remainder = None  # type: ignore[assignment]  # drop first partial line

        if st.st_size == self._offset:
            return

        with open(path, "rb") as fh:
            fh.seek(self._offset)
            chunk = fh.read(st.st_size - self._offset)
        self._offset += len(chunk)

        if self._remainder is None:
            nl = chunk.find(b"\n")
            chunk = chunk[nl + 1 :] if nl >= 0 else b""
            self._remainder = b""

        data = self._remainder + chunk
        lines = data.split(b"\n")
        self._remainder = lines.pop()  # possibly incomplete last line
        for raw in lines:
            ev = parse_line(raw.decode("utf-8", errors="replace").rstrip("\r"))
            if ev is not None:
                self.state.apply(ev)


def _is_game_running() -> Optional[bool]:
    """Return True/False if detectable, None if we cannot tell."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq StarCitizen.exe", "/NH", "/FO", "CSV"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            return "starcitizen.exe" in out.lower()
        if shutil.which("pgrep"):
            res = subprocess.run(["pgrep", "-f", "StarCitizen.exe"], capture_output=True, timeout=10)
            return res.returncode == 0
    except (OSError, subprocess.SubprocessError):
        log.debug("Prozessprüfung fehlgeschlagen", exc_info=True)
    return None


class ProcessWatcher(threading.Thread):
    def __init__(self, state: DashboardState, interval: float = 15.0) -> None:
        super().__init__(name="scdash-proc", daemon=True)
        self.state = state
        self.interval = interval
        self._halt = threading.Event()

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        while not self._halt.is_set():
            self.state.set_game_running(_is_game_running())
            self._halt.wait(self.interval)
