import os
import shutil
import tempfile
import unittest

from scdash.analyze import report, run, summarize

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "session_4.10_courier.log")
# wording taken from a real 4.10 log (there for a graphics cvar)
REJECTED = ("<2026-11-12T18:00:01.000Z> [CVARS]: [CHANGED] CXConsole::LoadConfigVar(): variable [log_verbosity] is marked "
            "[Not Whitelisted] with a value of [1]; config file attempting to change to [4] - IGNORING\r\n")


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_real_log_report(self):
        text = run(FIXTURE)
        self.assertIn("Spielversion: 4.10.197", text)
        self.assertIn("missions_completed=1", text)
        self.assertIn("log_verbosity: keine Spur in der Log", text)
        # the two ATC hints are the only HUD messages without a rule of their own
        self.assertIn("Air Traffic Control (ATC)", text)
        self.assertNotIn("TestPilot", text)  # player name is masked

    def test_rejected_verbosity_setting_is_reported(self):
        path = os.path.join(self.dir, "Game.log")
        with open(FIXTURE, "rb") as fh:
            raw = fh.read()
        with open(path, "wb") as fh:
            fh.write(raw + REJECTED.encode())
        text = run(path, FIXTURE)
        self.assertIn("log_verbosity: in der user.cfg gefunden, gewünscht 4, Wert im Spiel 1 – ABGELEHNT", text)
        self.assertIn("Vergleich mit", text)
        self.assertIn("Zeilenarten, die es nur in der neuen Log gibt: 0", text)

    def test_masks_private_data(self):
        path = os.path.join(self.dir, "Game.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("<2026-11-12T18:00:00.000Z> [Notice] <Legacy login response> [CIG-net] User Login Success - Handle[SecretName] - Time[1]\n")
            fh.write('<2026-11-12T18:00:05.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "SecretName met 123456789012 at 34.86.146.137: " [1] to queue.\n')
        text = report(summarize(path))
        self.assertNotIn("SecretName", text)
        self.assertNotIn("34.86.146.137", text)
        self.assertNotIn("123456789012", text)
        self.assertIn("<Pilot> met # at #.#.#.#", text)  # numbers are collapsed, the name is masked


if __name__ == "__main__":
    unittest.main()
