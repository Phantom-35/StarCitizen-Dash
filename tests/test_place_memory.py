"""Place memory, checked with two real 4.10 sessions.

Session 1 delivered "To Security Compound" at Covalex Distribution Centre S4DC05.
Session 2 had the objective "Deliver Hydrogen To Lobby" - the text names only a room. Its marker
lies 3.6 km from the session-1 marker, and the player delivered at the same Covalex centre.
"""

import os
import shutil
import tempfile
import unittest

from scdash.memory import PlaceMemory
from scdash.state import DashboardState
from scdash.watcher import LogWatcher

HERE = os.path.dirname(__file__)
SESSION_1 = os.path.join(HERE, "fixtures", "session_4.10_courier.log")
SESSION_2 = os.path.join(HERE, "fixtures", "session_4.10_courier_2.log")


class PlaceMemoryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.memfile = os.path.join(self.dir, "places.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def replay(self, fixture, memory, until=None):
        with open(fixture, "rb") as fh:
            raw = fh.read()
        if until:
            raw = raw[: raw.index(until)]
        path = os.path.join(self.dir, "Game.log")
        with open(path, "wb") as fh:
            fh.write(raw)
        state = DashboardState(memory)
        LogWatcher(lambda: path, state).poll()
        return state.snapshot()

    def test_learns_places_where_objectives_were_completed(self):
        mem = PlaceMemory(self.memfile)
        self.replay(SESSION_1, mem)
        names = sorted(e["place"] for e in mem._entries)
        # pick-up and drop-off of the completed contract (the abandoned one taught nothing)
        self.assertEqual(names, ["Clear View Emergency Shelter", "Covalex Distribution Centre S4DC05"])
        self.assertEqual(len(PlaceMemory(self.memfile)), 2)  # saved to disk

    def test_second_session_knows_where_the_lobby_is(self):
        mem = PlaceMemory(self.memfile)
        self.replay(SESSION_1, mem)
        # session 2, after picking up the hydrogen (18:07:54), before arriving at the drop-off
        s = self.replay(SESSION_2, PlaceMemory(self.memfile), until=b"<2026-11-11T18:08:39")
        nxt = s["missions"]["active"][0]["next"]
        self.assertEqual(nxt, {"place": "Covalex Distribution Centre S4DC05", "detail": "Lobby", "learned": True})

    def test_without_memory_the_text_is_used(self):
        s = self.replay(SESSION_2, None, until=b"<2026-11-11T18:08:39")
        self.assertEqual(s["missions"]["active"][0]["next"], {"place": "Lobby", "detail": None, "learned": False})

    def test_pick_up_named_in_text_stays(self):
        mem = PlaceMemory(self.memfile)
        self.replay(SESSION_1, mem)
        # right after accepting: the pick-up comes first and is named in the objective itself
        s = self.replay(SESSION_2, PlaceMemory(self.memfile), until=b"<2026-11-11T18:04:02")
        self.assertEqual(s["missions"]["active"][0]["next"]["place"], "Sakura Sun Goldenrod Workcenter")

    def test_far_away_or_local_markers_do_not_match(self):
        mem = PlaceMemory(None)
        loc = {"system": "Stanton", "planet": "microTech", "place": "Somewhere"}
        self.assertTrue(mem.learn((-331480.0, 896896.0, -293884.0), loc, "t"))
        self.assertIsNotNone(mem.lookup((-331480.0 + 9000, 896896.0, -293884.0)))   # 9 km: same place
        self.assertIsNone(mem.lookup((-331480.0 + 25000, 896896.0, -293884.0)))      # 25 km: no
        self.assertFalse(mem.learn((-1.9, 4.0, 3.7), loc, "t"))   # building-local marker: ignored
        self.assertIsNone(mem.lookup((-1.9, 4.0, 3.7)))

    def test_renamed_place_replaces_old_entry(self):
        mem = PlaceMemory(None)
        p = (500000.0, 500000.0, 500000.0)
        mem.learn(p, {"place": "Old Name"}, "t1")
        mem.learn((p[0] + 200, p[1], p[2]), {"place": "New Name"}, "t2")
        self.assertEqual(len(mem), 1)
        self.assertEqual(mem.lookup(p)["place"], "New Name")

    def test_broken_file_is_ignored(self):
        with open(self.memfile, "w") as fh:
            fh.write("{ not json")
        self.assertEqual(len(PlaceMemory(self.memfile)), 0)


class Session2Tests(unittest.TestCase):
    """Things seen for the first time in the second real session."""

    def test_med_bed_and_tips(self):
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "Game.log")
            shutil.copy(SESSION_2, path)
            state = DashboardState()
            LogWatcher(lambda: path, state).poll()
            s = state.snapshot()
        finally:
            shutil.rmtree(d, ignore_errors=True)
        # "Medical Bed: The bed has restored your health ..." twice, two minutes apart = one visit
        self.assertEqual(s["stats"]["medbed"], 1)
        texts = [e["actor"] for e in s["feeds"]["mission"]]
        self.assertFalse(any(t.startswith(("Medical Device", "Air Traffic Control", "Optic")) for t in texts))
        self.assertEqual((s["stats"]["missions_completed"], s["stats"]["cargo_delivered"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
