"""Session history, update check, window placement, autostart and the new HTTP endpoints."""

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from scdash import __version__, cli, updates, window
from scdash.history import SessionHistory, balance
from scdash.server import make_server
from scdash.state import DashboardState
from scdash.watcher import LogWatcher

HERE = os.path.dirname(__file__)
SESSION_1 = os.path.join(HERE, "fixtures", "session_4.10_courier.log")
SESSION_2 = os.path.join(HERE, "fixtures", "session_4.10_courier_2.log")


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def replay(self, fixture, history):
        path = os.path.join(self.dir, "Game.log")
        shutil.copyfile(fixture, path)
        state = DashboardState(None, history)
        LogWatcher(lambda: path, state).poll()
        return state


class HistoryTests(TempDirCase):
    def test_real_session_is_recorded_once(self):
        path = os.path.join(self.dir, "sessions.json")
        state = self.replay(SESSION_1, SessionHistory(path))
        state.save_history()
        state.save_history()   # same session again: updated, not duplicated
        sessions = SessionHistory(path).sessions()
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        snap = state.snapshot()
        self.assertEqual(s["start"], snap["session"]["start"])
        self.assertEqual(s["missions_completed"], snap["stats"]["missions_completed"])
        self.assertGreaterEqual(s["missions_completed"], 1)
        self.assertGreater(s["seconds"], 60)

    def test_reading_the_log_again_does_not_duplicate(self):
        path = os.path.join(self.dir, "sessions.json")
        self.replay(SESSION_1, SessionHistory(path)).save_history()
        self.replay(SESSION_1, SessionHistory(path)).save_history()   # dashboard restarted
        self.replay(SESSION_2, SessionHistory(path)).save_history()
        self.assertEqual(len(SessionHistory(path).sessions()), 2)

    def test_quit_line_saves_immediately(self):
        path = os.path.join(self.dir, "sessions.json")
        state = self.replay(SESSION_1, SessionHistory(path))
        if state.snapshot()["session"]["ended"]:
            self.assertEqual(len(SessionHistory(path).sessions()), 1)

    def test_new_session_saves_the_old_one(self):
        path = os.path.join(self.dir, "sessions.json")
        state = self.replay(SESSION_1, SessionHistory(path))
        start = state.snapshot()["session"]["start"]
        state.new_session()
        self.assertEqual([s["start"] for s in SessionHistory(path).sessions()], [start])

    def test_pay_belongs_to_its_session(self):
        state = self.replay(SESSION_1, SessionHistory(None))
        start = state.snapshot()["session"]["start"]
        self.assertFalse(state.set_pay("2020-01-01T00:00:00.000Z", 5000))
        self.assertFalse(state.set_pay(start, "viel"))
        self.assertTrue(state.set_pay(start, 25000))
        self.assertEqual(state.snapshot()["stats"]["pay"], 25000)
        self.assertEqual(state.session_summary()["pay"], 25000)

    def test_balance_formula_matches_dashboard(self):
        self.assertEqual(balance({"pay": 25000, "money_in": 1000, "spend": 3000, "money_out": 500, "fines": 500}),
                         22000)

    def test_short_or_empty_sessions_are_not_kept(self):
        h = SessionHistory(None)
        self.assertFalse(h.record(None))
        self.assertFalse(h.record({"start": "2026-11-11T10:00:00Z", "seconds": 20}))
        self.assertTrue(h.record({"start": "2026-11-11T10:00:00Z", "seconds": 600}))

    def test_week_and_all_totals(self):
        h = SessionHistory(None)
        h.record({"start": "2026-11-10T10:00:00Z", "seconds": 3600, "missions_completed": 2, "pay": 10000})
        h.record({"start": "2026-10-01T10:00:00Z", "seconds": 1800, "missions_completed": 1, "deaths": 2})
        v = h.view("2026-11-12T10:00:00Z")
        self.assertEqual(v["week"]["sessions"], 1)
        self.assertEqual(v["week"]["missions_completed"], 2)
        self.assertEqual(v["week"]["balance"], 10000)
        self.assertEqual(v["all"]["sessions"], 2)
        self.assertEqual(v["all"]["deaths"], 2)
        self.assertEqual(v["sessions"][0]["start"], "2026-11-10T10:00:00Z")   # newest first

    def test_broken_file_is_ignored(self):
        path = os.path.join(self.dir, "sessions.json")
        with open(path, "w") as fh:
            fh.write("{kaputt")
        self.assertEqual(len(SessionHistory(path)), 0)


class UpdateTests(unittest.TestCase):
    def test_version_parsing(self):
        self.assertEqual(updates.parse_version("v0.10.0"), (0, 10, 0))
        self.assertEqual(updates.parse_version("0.9"), (0, 9, 0))
        self.assertIsNone(updates.parse_version("latest"))

    def test_only_newer_releases(self):
        self.assertIsNone(updates.newer_release({"tag_name": "v0.9.0"}, "0.9.0"))
        self.assertIsNone(updates.newer_release({"tag_name": "v0.8.3"}, "0.9.0"))
        # 0.10 is newer than 0.9 (numbers, not text)
        u = updates.newer_release({"tag_name": "v0.10.0", "html_url":
                                   "https://github.com/Phantom-35/StarCitizen-Dash/releases/tag/v0.10.0"}, "0.9.0")
        self.assertEqual(u["version"], "0.10.0")
        self.assertIn("/releases/tag/v0.10.0", u["url"])

    def test_drafts_and_foreign_links_are_ignored(self):
        self.assertIsNone(updates.newer_release({"tag_name": "v9.0.0", "prerelease": True}, "0.9.0"))
        u = updates.newer_release({"tag_name": "v9.0.0", "html_url": "https://evil.example/x"}, "0.9.0")
        self.assertEqual(u["url"], updates.RELEASES_PAGE)

    def test_release_notes_from_changelog(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("release_notes", os.path.join(HERE, "..", "tools", "release_notes.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with open(os.path.join(HERE, "..", "CHANGELOG.md"), encoding="utf-8") as fh:
            text = mod.notes(__version__, fh.read())
        self.assertIn("update.bat", text)
        self.assertNotIn("## [", text)            # only this version's section
        self.assertGreater(len(text), 200)        # the changelog has an entry for the current version


class WindowTests(TempDirCase):
    SCREEN = [-1920, 0, 2560, 1440]   # second monitor left of the main one

    def test_saved_position_is_used(self):
        p = window.clean({"x": -1900, "y": 10, "w": 1800, "h": 1000})
        args = window.window_args(p, self.SCREEN)
        self.assertEqual(args, ["--window-position=-1900,10", "--window-size=1800,1000"])

    def test_position_off_screen_falls_back(self):
        p = window.clean({"x": 5000, "y": 10, "w": 1600, "h": 900})   # monitor unplugged
        self.assertEqual(window.window_args(p, self.SCREEN), ["--window-size=1600,900"])
        self.assertEqual(window.window_args(None, self.SCREEN), ["--window-size=1600,900"])

    def test_bad_values_are_rejected(self):
        for bad in (None, [], {"x": 1}, {"x": "a", "y": 0, "w": 800, "h": 600},
                    {"x": -32000, "y": -32000, "w": 160, "h": 28},   # what Windows reports when minimised
                    {"x": 0, "y": 0, "w": 10**9, "h": 600}):
            self.assertIsNone(window.clean(bad), bad)

    def test_save_and_load(self):
        path = os.path.join(self.dir, "window.json")
        window.save(path, {"x": 1, "y": 2, "w": 800, "h": 600})
        self.assertEqual(window.load(path), {"x": 1, "y": 2, "w": 800, "h": 600})
        self.assertIsNone(window.load(os.path.join(self.dir, "missing.json")))


class EndpointTests(TempDirCase):
    def setUp(self):
        super().setUp()
        self.state = self.replay(SESSION_1, SessionHistory(os.path.join(self.dir, "sessions.json")))
        self.winfile = os.path.join(self.dir, "window.json")
        self.httpd = make_server("127.0.0.1", 0, self.state, self.winfile)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def post(self, path, data, ctype="application/json"):
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode(), method="POST",
                                     headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def test_history_endpoint(self):
        with urllib.request.urlopen(self.base + "/api/history", timeout=5) as r:
            data = json.loads(r.read())
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["sessions"][0]["start"], self.state.snapshot()["session"]["start"])

    def test_pay_endpoint(self):
        start = self.state.snapshot()["session"]["start"]
        self.assertEqual(self.post("/api/pay", {"session": start, "total": 12000}), 204)
        self.assertEqual(self.state.snapshot()["stats"]["pay"], 12000)
        self.assertEqual(self.post("/api/pay", {"session": "alt", "total": 1}), 409)

    def test_simple_requests_from_web_pages_are_refused(self):
        # a foreign web page can only send text/plain etc. without asking first
        self.assertEqual(self.post("/api/pay", {"session": "x", "total": 1}, ctype="text/plain"), 400)

    def test_window_endpoint(self):
        self.assertEqual(self.post("/api/window", {"x": 10, "y": 20, "w": 1700, "h": 950}), 204)
        self.assertEqual(window.load(self.winfile), {"x": 10, "y": 20, "w": 1700, "h": 950})
        self.post("/api/window", {"x": -32000, "y": -32000, "w": 160, "h": 28})   # minimised: ignored
        self.assertEqual(window.load(self.winfile)["x"], 10)

    def test_running_instance_is_detected(self):
        self.assertTrue(cli.running_instance(self.httpd.server_address[1]))
        self.assertFalse(cli.running_instance(1, timeout=0.5))

    def test_page_requests_mark_a_window_as_open(self):
        before = self.state.last_client
        urllib.request.urlopen(self.base + "/api/state", timeout=5).read()
        self.assertGreater(self.state.last_client, before)


class AutostartTests(unittest.TestCase):
    def test_script_runs_hidden_with_game_mode(self):
        text = cli.autostart_script(r"C:\Python313\pythonw.exe", r"C:\Users\X\Desktop\StarCitizen-Dash",
                                    ["--log", r"D:\Star Citizen\LIVE"])
        self.assertIn('sh.CurrentDirectory = "C:\\Users\\X\\Desktop\\StarCitizen-Dash"', text)
        # one VBScript string: inner quotes doubled
        self.assertIn('sh.Run """C:\\Python313\\pythonw.exe"" -m scdash --with-game --log ""D:\\Star Citizen\\LIVE""", 0, False',
                      text)
        self.assertTrue(text.endswith("\r\n"))

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_install_and_remove_on_windows(self):
        tmp = tempfile.mkdtemp()
        old = os.environ.get("APPDATA")
        os.environ["APPDATA"] = tmp
        try:
            args = cli.build_parser().parse_args(["--autostart", "on", "--gpu"])
            self.assertEqual(cli.set_autostart(True, args), 0)
            target = os.path.join(cli.startup_dir(), cli.STARTUP_NAME)
            with open(target, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("-m scdash --with-game --gpu", text)
            self.assertEqual(cli.set_autostart(False, args), 0)
            self.assertFalse(os.path.exists(target))
        finally:
            if old is None:
                del os.environ["APPDATA"]
            else:
                os.environ["APPDATA"] = old
            shutil.rmtree(tmp, ignore_errors=True)

    def test_not_on_other_systems(self):
        if os.name == "nt":
            self.skipTest("Windows")
        args = cli.build_parser().parse_args(["--autostart", "on"])
        self.assertEqual(cli.set_autostart(True, args), 1)


class GameFollowerTests(unittest.TestCase):
    def test_opens_once_when_the_game_starts(self):
        state = DashboardState()
        opened = []
        f = cli.GameFollower(state, lambda: opened.append(1))
        state.set_game_running(False)
        self.assertFalse(f.step())
        state.set_game_running(True)
        self.assertTrue(f.step())
        self.assertFalse(f.step())          # still running: not again
        self.assertEqual(len(opened), 1)

    def test_not_when_a_window_is_already_open(self):
        state = DashboardState()
        f = cli.GameFollower(state, lambda: None)
        state.last_client = time.monotonic()
        state.set_game_running(True)
        self.assertFalse(f.step())


if __name__ == "__main__":
    unittest.main()
