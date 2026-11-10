import os
import shutil
import tempfile
import unittest
from unittest import mock

from scdash import paths


class LauncherDetectionTests(unittest.TestCase):
    def setUp(self):
        self.appdata = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.appdata, "rsilauncher", "logs"))

    def tearDown(self):
        shutil.rmtree(self.appdata, ignore_errors=True)

    def test_install_roots_from_launcher_log(self):
        with open(os.path.join(self.appdata, "rsilauncher", "logs", "log.log"), "w", encoding="utf-8") as fh:
            fh.write('[info] Launching Star Citizen LIVE from (E:\\\\Games\\\\RSI\\\\StarCitizen\\\\LIVE)\n')
            fh.write('{"libraryFolder":"D:/SC/StarCitizen","channel":"LIVE"}\n')
            fh.write('[info] Launching Star Citizen LIVE from (E:\\\\Games\\\\RSI\\\\StarCitizen\\\\LIVE)\n')  # duplicate
        with mock.patch.dict(os.environ, {"APPDATA": self.appdata}):
            roots = paths.launcher_install_roots()
        self.assertEqual(len(roots), 2)
        self.assertTrue(roots[0].replace("/", "\\").endswith("Games\\RSI\\StarCitizen"))
        with mock.patch.dict(os.environ, {"APPDATA": self.appdata}):
            cands = list(paths.candidate_logs())
        self.assertTrue(any(c.replace("/", "\\").endswith("RSI\\StarCitizen\\LIVE\\Game.log") for c in cands))

    def test_no_launcher(self):
        with mock.patch.dict(os.environ, {"APPDATA": os.path.join(self.appdata, "missing")}):
            self.assertEqual(paths.launcher_install_roots(), [])

    def test_explicit_folder(self):
        live = os.path.join(self.appdata, "LIVE")
        os.makedirs(live)
        self.assertEqual(paths.resolve_log(live), os.path.join(live, "Game.log"))


if __name__ == "__main__":
    unittest.main()
