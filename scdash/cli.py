"""Command line entry point: ``python -m scdash``."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from typing import List, Optional

from scdash import __version__
from scdash import window
from scdash.paths import browser_profile_dir, data_dir, find_chromium_browser, resolve_log
from scdash.server import make_server
from scdash.state import DashboardState
from scdash.status import StatusPoller
from scdash.watcher import LogWatcher, ProcessWatcher

log = logging.getLogger("scdash")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scdash",
        description="Leichtgewichtiges Star-Citizen-Dashboard für den zweiten Monitor.",
    )
    p.add_argument("--log", help="Pfad zur Game.log oder zum Kanal-Ordner (z. B. ...\\StarCitizen\\LIVE). "
                   "Standard: automatische Suche.")
    p.add_argument("--host", default="127.0.0.1", help="Adresse für den Webserver (Standard: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8777, help="Port für den Webserver (Standard: 8777)")
    p.add_argument("--open", action="store_true",
                   help="Dashboard als eigenes Fenster öffnen (Edge/Chrome im App-Modus, GPU deaktiviert)")
    p.add_argument("--gpu", action="store_true",
                   help="Dashboard-Fenster mit Hardwarebeschleunigung (flüssiger, belegt aber etwas VRAM)")
    p.add_argument("--fullscreen", action="store_true", help="Dashboard-Fenster im Vollbild öffnen")
    p.add_argument("--with-game", action="store_true",
                   help="Fenster automatisch öffnen, sobald Star Citizen startet (für den Autostart)")
    p.add_argument("--autostart", choices=("on", "off"),
                   help="SC-Dash mit Windows unsichtbar starten (on) bzw. das wieder entfernen (off); "
                        "das Fenster öffnet sich dann von selbst, sobald das Spiel läuft")
    p.add_argument("--no-status", action="store_true",
                   help="Keine Internetzugriffe (kein RSI-Serverstatus, keine Update-Prüfung)")
    p.add_argument("--no-update-check", action="store_true", help="Nicht auf GitHub nach neuen Versionen sehen")
    p.add_argument("--analyze", metavar="LOG",
                   help="Log-Check: Bericht über eine Game.log ausgeben (was erkannt wird, unbekannte Meldungen) "
                        "und beenden")
    p.add_argument("--compare", metavar="ALTE_LOG",
                   help="mit --analyze: zweite Log zum Vergleich, z. B. vor/nach einer Änderung der user.cfg")
    p.add_argument("--demo", action="store_true", help="Demo-Modus mit simulierten Ereignissen (ohne Spiel)")
    p.add_argument("-v", "--verbose", action="store_true", help="Ausführliche Ausgabe")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def window_file() -> str:
    return os.path.join(data_dir(), "window.json")


def open_dashboard(url: str, gpu: bool = False, fullscreen: bool = False) -> None:
    exe = find_chromium_browser()
    if not exe:
        log.info("Kein Edge/Chrome gefunden – öffne Standardbrowser.")
        webbrowser.open(url)
        return
    profile = browser_profile_dir()
    os.makedirs(profile, exist_ok=True)
    args = [
        exe,
        f"--app={url}",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        # let the dashboard play its short signal tones without a click first
        "--autoplay-policy=no-user-gesture-required",
        # Separate profile, otherwise the flags are ignored if the browser is already open.
        f"--user-data-dir={profile}",
    ]
    # where the window was last time (second monitor), else the default size
    args += window.window_args(window.load(window_file()))
    if fullscreen:
        args.append("--start-fullscreen")
    if not gpu:
        # Software rendering: the dashboard window uses no VRAM on the graphics card.
        args += ["--disable-gpu", "--disable-gpu-compositing", "--disable-software-rasterizer"]
    log.info("Öffne Dashboard-Fenster: %s", os.path.basename(exe))
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        webbrowser.open(url)


def running_instance(port: int, timeout: float = 2.0) -> bool:
    """Is an SC-Dash already answering on this port (e.g. started by the Windows autostart)?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=timeout) as resp:
            return '"token"' in resp.read(4096).decode("utf-8", "replace")
    except Exception:
        return False


STARTUP_NAME = "SC-Dash.vbs"


def startup_dir() -> Optional[str]:
    appdata = os.environ.get("APPDATA")
    if sys.platform != "win32" or not appdata:
        return None
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def autostart_script(python: str, workdir: str, extra: List[str]) -> str:
    """VBScript for the Startup folder: runs SC-Dash without a console window."""
    def q(text: str) -> str:  # VBScript string literal
        return '"' + text.replace('"', '""') + '"'

    cmd = " ".join(['"' + python + '"', "-m", "scdash", "--with-game"] +
                   [a if " " not in a else '"' + a + '"' for a in extra])
    return ("' SC-Dash: startet unsichtbar mit Windows. Das Dashboard-Fenster oeffnet sich,\r\n"
            "' sobald Star Citizen laeuft. Entfernen: start.bat --autostart off (oder diese Datei loeschen).\r\n"
            "Set sh = CreateObject(\"WScript.Shell\")\r\n"
            f"sh.CurrentDirectory = {q(workdir)}\r\n"
            f"sh.Run {q(cmd)}, 0, False\r\n")


def set_autostart(enable: bool, args) -> int:
    folder = startup_dir()
    if not folder:
        log.error("Autostart gibt es nur unter Windows.")
        return 1
    target = os.path.join(folder, STARTUP_NAME)
    if not enable:
        try:
            os.remove(target)
            log.info("Autostart entfernt.")
        except FileNotFoundError:
            log.info("Autostart war nicht eingerichtet.")
        return 0
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.isfile(pythonw):
        exe = pythonw  # no console window at all
    extra: List[str] = []
    if args.log:
        extra += ["--log", os.path.abspath(args.log)]
    if args.port != 8777:
        extra += ["--port", str(args.port)]
    for flag in ("gpu", "fullscreen", "no_status", "no_update_check"):
        if getattr(args, flag):
            extra.append("--" + flag.replace("_", "-"))
    workdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(folder, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="") as fh:
        fh.write(autostart_script(exe, workdir, extra))
    log.info("Autostart eingerichtet: %s", target)
    log.info("Ab dem nächsten Windows-Start läuft SC-Dash im Hintergrund und öffnet sich mit dem Spiel.")
    return 0


class GameFollower(threading.Thread):
    """--with-game: opens the dashboard window when Star Citizen starts and no window is open."""

    QUIET = 15.0  # seconds without a request from a window = no window open

    def __init__(self, state, open_window, interval: float = 2.0) -> None:
        super().__init__(name="scdash-follow", daemon=True)
        self.state = state
        self.open_window = open_window
        self.interval = interval
        self._halt = threading.Event()
        self._was_running = False

    def stop(self) -> None:
        self._halt.set()

    def step(self) -> bool:
        running = self.state.game_running is True
        opened = False
        if running and not self._was_running and time.monotonic() - self.state.last_client > self.QUIET:
            log.info("Star Citizen gestartet – öffne Dashboard")
            self.open_window()
            opened = True
        self._was_running = running
        return opened

    def run(self) -> None:
        while not self._halt.wait(self.interval):
            try:
                self.step()
            except Exception:
                log.exception("Fenster konnte nicht geöffnet werden")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = None
    if sys.stderr is None:  # started with pythonw (autostart): no console, write a log file instead
        try:
            os.makedirs(data_dir(), exist_ok=True)
            handlers = [logging.FileHandler(os.path.join(data_dir(), "scdash.log"), mode="w", encoding="utf-8")]
        except OSError:
            handlers = [logging.NullHandler()]
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )

    if args.autostart:
        return set_autostart(args.autostart == "on", args)

    if args.analyze:
        from scdash.analyze import run

        try:
            text = run(args.analyze, args.compare)
        except OSError as exc:
            log.error("Log nicht lesbar: %s", exc)
            return 1
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page
        except (AttributeError, ValueError):
            pass
        print(text)
        return 0

    places = history = None
    if not args.demo:
        from scdash.history import SessionHistory
        from scdash.memory import PlaceMemory

        places = PlaceMemory(os.path.join(data_dir(), "places.json"))
        history = SessionHistory(os.path.join(data_dir(), "sessions.json"))
        log.info("Ortsgedächtnis: %d bekannte Auftragsorte, Verlauf: %d Sessions", len(places), len(history))
    state = DashboardState(places, history)

    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{args.port}/"
    try:
        httpd = make_server(args.host, args.port, state, None if args.demo else window_file())
    except OSError as exc:
        if running_instance(args.port):
            # e.g. already running in the background via the autostart: just open the window
            log.info("SC-Dash läuft bereits auf %s", url)
            if args.open:
                open_dashboard(url, args.gpu, args.fullscreen)
            return 0
        log.error("Port %s ist belegt oder nicht verfügbar (%s). Anderen Port mit --port wählen.", args.port, exc)
        return 1

    threads = []

    if args.demo:
        from scdash.demo import DemoLogWriter

        demo = DemoLogWriter()
        demo.start()
        threads.append(demo)
        log_arg = demo.path
        log.info("Demo-Modus aktiv (simulierte Game.log: %s)", demo.path)
    else:
        log_arg = args.log

    resolved = resolve_log(log_arg)
    if resolved:
        log.info("Beobachte: %s", resolved)
    else:
        log.warning("Keine Game.log gefunden. Starte mit --log \"<Pfad>\\StarCitizen\\LIVE\". "
                    "Es wird weiter gesucht.")

    # Re-resolve periodically when auto-detecting (e.g. switching LIVE <-> PTU).
    cache = {"path": resolved, "n": 0}

    def resolver():
        if log_arg:
            return resolved
        cache["n"] += 1
        if cache["path"] is None or cache["n"] % 30 == 0:
            cache["path"] = resolve_log(None)
        return cache["path"]

    threads.append(LogWatcher(resolver, state))
    if args.demo:
        state.set_game_running(True)
    else:
        threads.append(ProcessWatcher(state))
    if not args.no_status:
        threads.append(StatusPoller(state))
        if not args.no_update_check and not args.demo:
            from scdash.updates import UpdateChecker

            threads.append(UpdateChecker(state))
    if history is not None:
        from scdash.history import HistorySaver

        threads.append(HistorySaver(state))
    if args.with_game:
        threads.append(GameFollower(state, lambda: open_dashboard(url, args.gpu, args.fullscreen)))
    for t in threads:
        if not t.is_alive():
            t.start()

    log.info("SC-Dash %s läuft auf %s  (Beenden mit Strg+C)", __version__, url)
    if args.open:
        threading.Timer(0.5, open_dashboard, args=(url, args.gpu, args.fullscreen)).start()

    try:
        httpd.serve_forever(poll_interval=1.0)
    except KeyboardInterrupt:
        log.info("Beende …")
    finally:
        httpd.server_close()
        for t in threads:
            t.stop()
    return 0
