import os
import shutil
import tempfile
import unittest

from scdash.parser import parse_line
from scdash.state import DashboardState
from scdash.watcher import LogWatcher

TS = "<2026-11-10T18:00:00.000Z>"
LOGIN = f"{TS} [Notice] User Login Success - Handle[Me] - Time[1]\n"
KILL_NPC = (f"{TS} [Notice] <Actor Death> CActor::Kill: 'PU_Pirate_1234567' [2] in zone 'Z' killed by 'Me' [1] "
            f"using 'gun_1234567' [Class gun] with damage type 'Bullet' from direction\n")
KILL_PLAYER = (f"{TS} [Notice] <Actor Death> CActor::Kill: 'Bob' [2] in zone 'Z' killed by 'Me' [1] "
               f"using 'gun_1234567' [Class gun] with damage type 'Bullet' from direction\n")
DEATH = (f"{TS} [Notice] <Actor Death> CActor::Kill: 'Me' [1] in zone 'Z' killed by 'Bob' [2] "
         f"using 'gun_1234567' [Class gun] with damage type 'Bullet' from direction\n")
SUICIDE = (f"{TS} [Notice] <Actor Death> CActor::Kill: 'Me' [1] in zone 'Z' killed by 'Me' [1] "
           f"using 'unknown' [Class unknown] with damage type 'Crash' from direction\n")


class StateTests(unittest.TestCase):
    def test_classification(self):
        st = DashboardState()
        for line in (LOGIN, KILL_NPC, KILL_PLAYER, DEATH, SUICIDE):
            st.apply(parse_line(line))
        s = st.snapshot()
        self.assertEqual(s["session"]["handle"], "Me")
        self.assertEqual(s["stats"]["npc_kills"], 1)
        self.assertEqual(s["stats"]["kills"], 1)
        self.assertEqual(s["stats"]["deaths"], 1)
        self.assertEqual(s["stats"]["suicides"], 1)
        self.assertEqual(s["events"][0]["cat"], "death")  # newest first
        self.assertEqual(s["session"]["start"], "2026-11-10T18:00:00.000Z")

    def test_version_changes(self):
        st = DashboardState()
        v = st.version
        st.set_game_running(True)
        self.assertGreater(st.version, v)
        v = st.version
        st.set_game_running(True)  # no change -> no new version
        self.assertEqual(st.version, v)


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "Game.log")
        self.state = DashboardState()
        self.watcher = LogWatcher(lambda: self.path, self.state)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, text, mode="a"):
        with open(self.path, mode, encoding="utf-8", newline="") as fh:
            fh.write(text)

    def test_missing_file(self):
        self.watcher.poll()
        self.assertFalse(self.state.snapshot()["log"]["found"])

    def test_tail_and_partial_lines(self):
        self.write(LOGIN)
        self.watcher.poll()
        self.assertEqual(self.state.snapshot()["session"]["handle"], "Me")

        # write half a line, then the rest
        self.write(KILL_PLAYER[:40])
        self.watcher.poll()
        self.assertEqual(self.state.snapshot()["stats"]["kills"], 0)
        self.write(KILL_PLAYER[40:])
        self.watcher.poll()
        self.assertEqual(self.state.snapshot()["stats"]["kills"], 1)

    def test_crlf_lines(self):
        self.write(LOGIN.replace("\n", "\r\n") + KILL_PLAYER.replace("\n", "\r\n"))
        self.watcher.poll()
        self.assertEqual(self.state.snapshot()["stats"]["kills"], 1)

    def test_new_log_resets_session(self):
        self.write(LOGIN + KILL_PLAYER + KILL_PLAYER)
        self.watcher.poll()
        self.assertEqual(self.state.snapshot()["stats"]["kills"], 2)

        # game restart: log rotated away and recreated smaller
        os.replace(self.path, self.path + ".bak")
        self.write(LOGIN, mode="w")
        self.watcher.poll()
        s = self.state.snapshot()
        self.assertEqual(s["stats"]["kills"], 0)
        self.assertEqual(s["session"]["handle"], "Me")


if __name__ == "__main__":
    unittest.main()
