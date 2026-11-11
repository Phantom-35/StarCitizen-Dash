"""Command line entry point: ``python -m scdash``."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
import webbrowser

from scdash import __version__
from scdash.paths import browser_profile_dir, find_chromium_browser, resolve_log
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
    p.add_argument("--no-status", action="store_true", help="RSI-Serverstatus nicht abrufen (keine Internetzugriffe)")
    p.add_argument("--analyze", metavar="LOG",
                   help="Log-Check: Bericht über eine Game.log ausgeben (was erkannt wird, unbekannte Meldungen) "
                        "und beenden")
    p.add_argument("--compare", metavar="ALTE_LOG",
                   help="mit --analyze: zweite Log zum Vergleich, z. B. vor/nach einer Änderung der user.cfg")
    p.add_argument("--demo", action="store_true", help="Demo-Modus mit simulierten Ereignissen (ohne Spiel)")
    p.add_argument("-v", "--verbose", action="store_true", help="Ausführliche Ausgabe")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def open_dashboard(url: str, gpu: bool = False) -> None:
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
        "--window-size=1600,900",
    ]
    if not gpu:
        # Software rendering: the dashboard window uses no VRAM on the graphics card.
        args += ["--disable-gpu", "--disable-gpu-compositing", "--disable-software-rasterizer"]
    log.info("Öffne Dashboard-Fenster: %s", os.path.basename(exe))
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        webbrowser.open(url)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

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

    state = DashboardState()
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
    for t in threads:
        if not t.is_alive():
            t.start()

    try:
        httpd = make_server(args.host, args.port, state)
    except OSError as exc:
        log.error("Port %s ist belegt oder nicht verfügbar (%s). Anderen Port mit --port wählen.", args.port, exc)
        return 1

    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{args.port}/"
    log.info("SC-Dash %s läuft auf %s  (Beenden mit Strg+C)", __version__, url)
    if args.open:
        threading.Timer(0.5, open_dashboard, args=(url, args.gpu)).start()

    try:
        httpd.serve_forever(poll_interval=1.0)
    except KeyboardInterrupt:
        log.info("Beende …")
    finally:
        httpd.server_close()
        for t in threads:
            t.stop()
    return 0
