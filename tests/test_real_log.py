"""Regression tests against an (anonymised) excerpt of a real Star Citizen 4.10 Game.log.

The excerpt keeps the original quirks: latin-1 bytes, mixed CRLF/LF line endings and
notifications that the game splits over two lines.
"""

import os
import random
import shutil
import tempfile
import unittest

from scdash.parser import LineAssembler, parse_line
from scdash.state import DashboardState
from scdash.watcher import LogWatcher

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "session_4.10_courier.log")


def comparable(snapshot):
    """Everything except the fields that differ between two runs."""
    return {k: v for k, v in snapshot.items() if k not in ("version", "token", "server_time", "log")}


class RealLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, "rb") as fh:
            cls.raw = fh.read()

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "Game.log")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def read_all_at_once(self):
        with open(self.path, "wb") as fh:
            fh.write(self.raw)
        state = DashboardState()
        LogWatcher(lambda: self.path, state).poll()
        return state.snapshot()

    def test_session_summary(self):
        s = self.read_all_at_once()
        self.assertEqual(s["session"]["handle"], "TestPilot")
        self.assertEqual(s["session"]["shard"], "pub_use1b_12881860_450")
        self.assertEqual(s["session"]["region"], "US East")
        self.assertEqual(s["session"]["location"], {"system": "Stanton", "planet": "microTech", "place": "New Babbage"})
        self.assertTrue(s["session"]["ended"])
        self.assertEqual(s["game_version"], "4.10.197")

        st = s["stats"]
        self.assertEqual((st["missions_completed"], st["missions_failed"], st["missions_abandoned"]), (1, 0, 1))
        self.assertEqual(st["quantum_jumps"], 4)
        self.assertEqual(st["places"], 4)
        self.assertEqual((st["kills"], st["deaths"]), (0, 0))

        nav = s["nav"]
        self.assertEqual((nav["armistice"], nav["monitored"], nav["jurisdiction"]), (True, True, "microTech"))
        self.assertIsNone(nav["ship"])  # left the ship before quitting

    def test_missions(self):
        s = self.read_all_at_once()
        self.assertEqual(s["missions"]["active"], [])
        done, = [h for h in s["missions"]["history"] if h["result"] == "completed"]
        self.assertEqual(done["title"], "ENTRY LVL. COURIER NEEDED IN STANTON")
        self.assertAlmostEqual(done["duration"], 595, delta=1)

        feed = s["feeds"]["mission"]
        titles = [e["title"] for e in feed]
        # the game reports a finished contract three times - it must be counted once
        self.assertEqual(titles.count("Auftrag erledigt"), 1)
        self.assertEqual(titles.count("Auftrag abgebrochen"), 1)
        # the multi-line "Objective Complete" notification and the drop-off (push message only)
        self.assertEqual(titles.count("Ziel erledigt"), 2)
        # ship name comes from the multi-line channel notification
        self.assertIn(("Eingestiegen", "RSI Aurora Mk II"), [(e["title"], e["actor"]) for e in feed])
        # a mere offer is not an accepted contract
        self.assertEqual(titles.count("Auftrag angenommen"), 2)

    def test_navigation_from_real_lines(self):
        s = self.read_all_at_once()
        # session time starts with the first log line, not with the login a few seconds later
        self.assertEqual(s["session"]["start"], "2026-11-10T16:18:05.458Z")
        feed = list(reversed(s["feeds"]["mission"]))
        targets = [e["actor"] for e in feed if e["title"] == "Quantum-Ziel"]
        # em_shelter_001_frost_{GUID}.socpak -> place from the active objective; NavPoint_Dynamic_* -> marker
        self.assertEqual(targets, ["Auftragsziel · Clear View Emergency Shelter", "Markierter Navpunkt",
                                   "Markierter Navpunkt", "Markierter Navpunkt", "New Babbage"])
        self.assertIn("Quantum blockiert", [e["title"] for e in feed])
        # arriving at a real place updates the location right away (inventory request came 20 s later)
        arrival = [e for e in feed if e["title"] == "Ort" and e["actor"] == "New Babbage"][-1]
        self.assertEqual(arrival["ts"], "2026-11-10T17:03:42.688Z")
        places = [e["actor"] for e in feed if e["title"] == "Ort"]
        self.assertEqual(places, ["New Babbage", "Clear View Emergency Shelter", "Covalex Distribution Centre S4DC05",
                                  "microTech Logistics Depot S4LD13", "New Babbage"])

    def test_cargo_and_connection_from_real_lines(self):
        s = self.read_all_at_once()
        feed = list(reversed(s["feeds"]["mission"]))
        # the medical supplies box: put into the ship, later handed in at the drop-off
        self.assertEqual((s["stats"]["cargo_loaded"], s["stats"]["cargo_delivered"]), (1, 1))
        self.assertIn(("Fracht verladen", "Medical Supplies"), [(e["title"], e["actor"]) for e in feed])
        self.assertIn(("Fracht abgegeben", "Medical Supplies"), [(e["title"], e["actor"]) for e in feed])
        # the log has four harmless "Nub destroyed" (30010) lines and one 30016 in the universe:
        # no connection error may be reported, only one neutral note
        self.assertEqual(s["stats"]["disconnects"], 0)
        self.assertEqual([e["title"] for e in feed].count("Verbindung getrennt"), 1)
        self.assertFalse(any(e["title"].startswith("Verbindungsfehler") for e in feed))
        self.assertEqual(s["session"]["server"], "450")
        self.assertEqual(s["health"]["injuries"], [])

    def test_ship_and_quantum_fuel_from_real_lines(self):
        s = self.read_all_at_once()
        # four jumps were made; the game's fuel estimates for them: 16.858 + 18.180 + 17.700 + 11.982.
        # A fifth route (0.66) was planned at 16:52 but never flown and must not be counted.
        self.assertAlmostEqual(s["stats"]["quantum_fuel_used"], 64.7, places=1)
        feed = list(reversed(s["feeds"]["mission"]))
        jumps = [e["detail"] for e in feed if e["title"] == "Quantum-Sprung"]
        self.assertEqual(jumps[0], "Auftragsziel · Clear View Emergency Shelter · 16,9 Treibstoff")
        self.assertEqual(jumps[-1], "New Babbage · 12,0 Treibstoff")
        # boarding is known from the channel notification, with its time
        boarded = [e for e in feed if e["title"] == "Eingestiegen"]
        self.assertEqual(boarded[0]["ts"], "2026-11-10T16:28:41.844Z")
        self.assertIsNone(s["nav"]["ship_since"])  # left the ship before quitting

    def test_ship_from_quantum_lines_when_boarding_was_missed(self):
        """Dashboard started mid-flight: the first quantum line still tells us the ship."""
        start = self.raw.index(b"<2026-11-10T16:30:54")
        with open(self.path, "wb") as fh:
            fh.write(self.raw[:200] + b"\r\n" + self.raw[start:self.raw.index(b"<2026-11-10T16:31:30")])
        state = DashboardState()
        LogWatcher(lambda: self.path, state).poll()
        nav = state.snapshot()["nav"]
        self.assertEqual(nav["ship"], "RSI Aurora Mk II")  # proper name from the ship database
        self.assertEqual(nav["ship_since"], "2026-11-10T16:30:54.148Z")
        self.assertAlmostEqual(nav["quantum_fuel"], 16.858, places=2)

    def test_multiline_notifications_are_joined(self):
        asm, texts = LineAssembler(), []
        for raw in self.raw.split(b"\n"):
            for full in asm.feed(raw.decode("latin-1").rstrip("\r")):
                ev = parse_line(full)
                if ev and ev.kind == "notify":
                    texts.append((ev.data["category"], ev.data["mission_id"], ev.data["objective_id"]))
        self.assertEqual(len(texts), 37)
        done = [t for t in texts if t[0] == "objective_done"]
        self.assertEqual(len(done), 1)
        self.assertTrue(done[0][1] and done[0][2], "mission/objective id of the joined line got lost")

    def test_live_tailing_gives_same_result(self):
        """Write the log in random chunks (as the game does) and poll in between."""
        expected = comparable(self.read_all_at_once())
        rng = random.Random(4)
        for _ in range(5):
            os.remove(self.path)
            state = DashboardState()
            watcher = LogWatcher(lambda: self.path, state)
            pos = 0
            with open(self.path, "wb"):
                pass
            while pos < len(self.raw):
                n = rng.choice((1, 7, 60, 300, 2000))
                with open(self.path, "ab") as fh:
                    fh.write(self.raw[pos : pos + n])
                pos += n
                watcher.poll()
            self.assertEqual(comparable(state.snapshot()), expected)

    def test_game_restart_starts_new_session(self):
        state = DashboardState()
        watcher = LogWatcher(lambda: self.path, state)
        with open(self.path, "wb") as fh:
            fh.write(self.raw)
        watcher.poll()
        self.assertEqual(state.snapshot()["stats"]["missions_completed"], 1)

        # The game recreates Game.log on launch. Same path, different first line (start time),
        # and here even *larger* than before so only the head check can notice it.
        new = self.raw.replace(b"2026-11-10T", b"2026-11-11T") + b"<2026-11-11T18:00:00.000Z> filler\r\n" * 50
        with open(self.path, "r+b") as fh:  # rewrite in place: keeps the same file identity
            fh.write(new)
        watcher.poll()
        s = state.snapshot()
        self.assertEqual(s["stats"]["missions_completed"], 1)  # not 2
        self.assertTrue(s["session"]["start"].startswith("2026-11-11"))


if __name__ == "__main__":
    unittest.main()
