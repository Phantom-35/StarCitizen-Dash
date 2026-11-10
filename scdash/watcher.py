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

import re

from scdash.parser import LineAssembler, parse_line
from scdash.state import DashboardState

log = logging.getLogger(__name__)

# Do not parse more than this on startup if the log is huge.
INITIAL_READ_LIMIT = 8 * 1024 * 1024


def open_log(path: str):
    """Open the log for reading without getting in the game's way.

    On Windows a normal ``open()`` forbids other processes to rename or delete the file while
    we hold it. The game moves the old Game.log into ``logbackups`` on every launch, so we open
    it with full sharing (read/write/delete) instead. Falls back to ``open()`` everywhere else.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            import msvcrt
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateFileW.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
            ]
            kernel32.CreateFileW.restype = wintypes.HANDLE
            GENERIC_READ, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL = 0x80000000, 3, 0x80
            SHARE_ALL = 0x1 | 0x2 | 0x4  # read | write | delete
            handle = kernel32.CreateFileW(path, GENERIC_READ, SHARE_ALL, None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None)
            if handle in (None, wintypes.HANDLE(-1).value):
                err = ctypes.get_last_error()
                if err in (2, 3):  # file / path not found
                    raise FileNotFoundError(path)
                raise OSError(err, ctypes.FormatError(err), path)
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | getattr(os, "O_BINARY", 0))
            except Exception:
                kernel32.CloseHandle(wintypes.HANDLE(handle))
                raise
            return os.fdopen(fd, "rb")
        except FileNotFoundError:
            raise
        except (ImportError, AttributeError):
            pass  # unusual Python build - use the plain variant
    return open(path, "rb")


HEAD_BYTES = 96
_FIRST_TS = re.compile(rb"^<(\d{4}-\d{2}-\d{2}T[\d:.]+Z)>")
HEAD_SCAN_BYTES = 2 * 1024 * 1024  # login, shard and version are written in the first minutes
HEAD_KINDS = ("version", "login", "join")  # the first log line contains the start timestamp -> unique per game launch


def _decode(raw: bytes) -> str:
    # The log is mostly ASCII; player names etc. can be UTF-8 or a legacy code page.
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


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
        self._identity = None
        self._head = b""
        self._offset = 0
        self._remainder: Optional[bytes] = b""
        self._assembler = LineAssembler()

    def stop(self) -> None:
        self._halt.set()

    def _scan_head(self, fh, length: int) -> None:
        """Only the end of a very long log is replayed - take who/where from its beginning."""
        fh.seek(0)
        for ev in _scan_lines(fh.read(length), LineAssembler(), HEAD_KINDS):
            self.state.apply(ev)

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
        if not path:
            self.state.set_log(None, False)
            return
        try:
            fh = open_log(path)
        except FileNotFoundError:
            self.state.set_log(path, False)
            return
        except OSError as exc:
            # e.g. the game is just moving the old log away - simply try again next time
            log.debug("Game.log gerade nicht lesbar: %s", exc)
            return
        self.state.set_log(path, True)

        with fh:
            st = os.fstat(fh.fileno())
            # Ask the open handle for the real end of file. Directory metadata (os.stat) can lag
            # behind on Windows while the game still has the file open for writing.
            size = fh.seek(0, os.SEEK_END)
            fh.seek(0)
            head = fh.read(HEAD_BYTES)

            identity = (path, st.st_dev, st.st_ino)
            head_changed = len(self._head) == HEAD_BYTES and head[: len(self._head)] != self._head
            if identity != self._identity or size < self._offset or head_changed:
                # New file (game restarted) or log was truncated -> new session.
                if self._identity is not None:
                    log.info("Neue Game.log erkannt – Session wird zurückgesetzt")
                self.state.new_session()
                self._assembler.reset()
                self._identity = identity
                self._head = b""
                self._remainder = b""
                self._offset = max(0, size - INITIAL_READ_LIMIT)
                if self._offset:
                    self._remainder = None  # drop the first, partial line
                    self._scan_head(fh, min(HEAD_SCAN_BYTES, self._offset))
            if len(self._head) < HEAD_BYTES:
                m = _FIRST_TS.match(head)  # retried until the first line is complete
                if m:
                    self.state.begin_session(m.group(1).decode())
                self._head = head

            if size == self._offset:
                return
            fh.seek(self._offset)
            chunk = fh.read()  # everything up to the real end of file
        self._offset += len(chunk)

        if self._remainder is None:
            nl = chunk.find(b"\n")
            if nl < 0:
                return
            chunk = chunk[nl + 1 :]
            self._remainder = b""

        lines = (self._remainder + chunk).split(b"\n")
        self._remainder = lines.pop()  # possibly incomplete last line
        for raw in lines:
            try:
                for full in self._assembler.feed(_decode(raw).rstrip("\r")):
                    ev = parse_line(full)
                    if ev is not None:
                        self.state.apply(ev)
            except Exception:  # one odd line must never cost us the rest of the log
                log.debug("Zeile übersprungen: %r", raw[:200], exc_info=True)


def _scan_lines(data: bytes, assembler: "LineAssembler", kinds=None):
    for raw in data.split(b"\n"):
        for full in assembler.feed(_decode(raw).rstrip("\r")):
            ev = parse_line(full)
            if ev is not None and (kinds is None or ev.kind in kinds):
                yield ev


def _is_game_running() -> Optional[bool]:
    """Return True/False if detectable, None if we cannot tell."""
    try:
        if sys.platform == "win32":
            # Read bytes: tasklist prints in the OEM code page ("ausgeführt" on German Windows),
            # decoding that as text would raise and silently kill the watcher thread.
            raw = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq StarCitizen.exe", "/NH", "/FO", "CSV"],
                capture_output=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            return b"starcitizen.exe" in raw.lower()
        if shutil.which("pgrep"):
            res = subprocess.run(["pgrep", "-f", "StarCitizen.exe"], capture_output=True, timeout=10)
            return res.returncode == 0
    except (OSError, ValueError, subprocess.SubprocessError):
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
            try:
                self.state.set_game_running(_is_game_running())
            except Exception:  # never let the thread die
                log.exception("Prozessprüfung fehlgeschlagen")
            self._halt.wait(self.interval)
