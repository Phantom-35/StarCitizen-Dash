"""End-to-end test of the live setup: watcher thread + HTTP server, log written while running.

This is what happens on a gaming PC: SC-Dash is already running, the game appends to
Game.log in arbitrary chunks (half lines, notifications split over two lines) and on the
next launch moves the old file into ``logbackups`` and starts a new one. The test talks
to the server over HTTP exactly like the dashboard does. Runs on Linux and Windows CI.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock

from scdash import watcher as watcher_mod
from scdash.server import make_server
from scdash.state import DashboardState
from scdash.watcher import LogWatcher

TIMEOUT = 5.0


def line(ts, text):
    return f"<2026-11-10T{ts}Z> {text}\r\n".encode()


HEADER = line("18:00:00.000", "Log started on Tue Nov 10 18:00:00 2026")
LOGIN = line("18:00:01.000", "[Notice] <Legacy login response> [CIG-net] User Login Success - Handle[LivePilot] - Time[1] [Team_GameServices][Login]")
JOIN = line("18:00:02.000", "[Notice] <Join PU> address[10.0.0.1] port[64300] shard[pub_euw1b_1_1] locationId[1] [Team_GameServices][GIM][Matchmaking]")
ACCEPT = line("18:01:00.000", '[Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Live Delivery: " [8] to queue. New queue size: 1, MissionId: [m-live], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]')
# split over two lines, exactly like the real log does it
OBJ_DONE = (
    line("18:02:00.000", '[Notice] <SHUDEvent_OnNotification> Added notification "Objective Complete: Collect the box')
    + line("18:02:00.000", ': " [9] to queue. New queue size: 1, MissionId: [m-live], ObjectiveId: [pickup_1] [Team_CoreGameplayFeatures][Missions][Comms]')
)
OBJ_NEW = line("18:01:00.001", '[Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Collect the box: " [9] to queue. New queue size: 1, MissionId: [m-live], ObjectiveId: [pickup_1] [Team_CoreGameplayFeatures][Missions][Comms]')
LOCATION = line("18:03:00.000", "[Notice] <RequestLocationInventory> Player[LivePilot] requested inventory for Location[Stanton2_Orison] [Team_CoreGameplayFeatures][Inventory]")


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "Game.log")
        self.state = DashboardState()
        self.watcher = LogWatcher(lambda: self.path, self.state, interval=0.05)
        self.httpd = make_server("127.0.0.1", 0, self.state)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.watcher.start()

    def tearDown(self):
        self.watcher.stop()
        self.watcher.join(2)
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)

    # -- helpers ----------------------------------------------------------------------
    def append(self, data: bytes, pause: float = 0.0):
        with open(self.path, "ab") as fh:
            fh.write(data)
            fh.flush()
        if pause:
            time.sleep(pause)

    def api(self, since=""):
        with urllib.request.urlopen(f"{self.base}/api/state?since={since}", timeout=5) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else None)

    def wait_for(self, check, what):
        deadline = time.monotonic() + TIMEOUT
        last = None
        while time.monotonic() < deadline:
            _, last = self.api()
            if check(last):
                return last
            time.sleep(0.05)
        self.fail(f"timed out waiting for: {what}\nlast state: {json.dumps(last)[:800]}")

    # -- tests ------------------------------------------------------------------------
    def test_dashboard_starts_before_game(self):
        # nothing there yet
        s = self.wait_for(lambda s: s["log"]["found"] is False, "missing log reported")
        self.assertIsNone(s["session"]["handle"])

        # game starts writing - first half of a line only
        self.append(HEADER + LOGIN[:40], pause=0.3)
        _, s = self.api()
        self.assertIsNone(s["session"]["handle"], "a half line must not be parsed")
        self.append(LOGIN[40:] + JOIN)
        s = self.wait_for(lambda s: s["session"]["shard"] == "pub_euw1b_1_1", "login + join")
        self.assertEqual(s["session"]["handle"], "LivePilot")

        # contract, objective, then a notification that arrives split over two writes
        self.append(ACCEPT + OBJ_NEW)
        self.wait_for(lambda s: s["missions"]["active"] and s["missions"]["active"][0]["objectives"], "objective")
        self.append(OBJ_DONE[:70], pause=0.3)
        self.append(OBJ_DONE[70:] + LOCATION)
        s = self.wait_for(lambda s: s["session"]["location"] and s["session"]["location"]["place"] == "Orison", "location")
        self.assertEqual(s["missions"]["active"][0]["objectives"][0]["state"], "done")

        # unchanged state -> 204 without body
        token = s["token"]
        status, body = self.api(token)
        self.assertEqual((status, body), (204, None))

    def test_game_restart_rotates_log(self):
        self.append(HEADER + LOGIN + JOIN + ACCEPT)
        self.wait_for(lambda s: len(s["missions"]["active"]) == 1, "first session")

        # next launch: the game moves the old log away and starts a fresh one
        backups = os.path.join(self.dir, "logbackups")
        os.makedirs(backups)
        os.replace(self.path, os.path.join(backups, "Game Build(1) 10 Nov 26 (18 05 00).log"))
        new_header = line("19:00:00.000", "Log started on Tue Nov 10 19:00:00 2026")
        self.append(new_header + line("19:00:01.000", LOGIN.decode().split("> ", 1)[1].strip()))
        s = self.wait_for(lambda s: s["session"]["start"] and s["session"]["start"].startswith("2026-11-10T19"),
                          "new session after restart")
        self.assertEqual(s["missions"]["active"], [])
        self.assertEqual(s["session"]["handle"], "LivePilot")

    def test_log_rewritten_in_place(self):
        """Some setups truncate and rewrite instead of moving: same file identity, new content."""
        self.append(HEADER + LOGIN + ACCEPT)
        self.wait_for(lambda s: len(s["missions"]["active"]) == 1, "first session")
        with open(self.path, "wb") as fh:  # truncate
            fh.write(line("20:00:00.000", "Log started on Tue Nov 10 20:00:00 2026"))
        s = self.wait_for(lambda s: s["session"]["start"] and s["session"]["start"].startswith("2026-11-10T20"),
                          "reset after truncation")
        self.assertEqual(s["missions"]["active"], [])


class ProcessCheckTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "uses tasklist")
    def test_tasklist_on_real_windows(self):
        # CI has no Star Citizen running: must say False (not crash, not None)
        self.assertIs(watcher_mod._is_game_running(), False)

    def test_localized_tasklist_output_does_not_crash(self):
        # German Windows, game not running: OEM code page bytes ("ausgeführt" -> 0x81)
        german = "INFORMATION: Es werden keine Aufgaben mit den angegebenen Kriterien ausgeführt.\r\n".encode("cp850")
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout=german, stderr=b"")
        with mock.patch.object(watcher_mod.sys, "platform", "win32"), \
                mock.patch.object(watcher_mod.subprocess, "run", return_value=fake):
            self.assertIs(watcher_mod._is_game_running(), False)
        running = b'"StarCitizen.exe","14200","Console","1","8.512.004 K"\r\n'
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout=running, stderr=b"")
        with mock.patch.object(watcher_mod.sys, "platform", "win32"), \
                mock.patch.object(watcher_mod.subprocess, "run", return_value=fake):
            self.assertIs(watcher_mod._is_game_running(), True)


if __name__ == "__main__":
    unittest.main()
