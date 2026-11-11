"""Ship database and quantum fuel maths.

The unit of the log's "fuel estimate" is the crucial assumption here, so it is pinned down
with real numbers: marker coordinates and estimates from a real 4.10 log, tank size and
range from the game files.
"""

import math
import os
import shutil
import tempfile
import unittest

from scdash import ships
from scdash.state import DashboardState
from scdash.watcher import LogWatcher

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "session_4.10_courier.log")

# Mission markers from the real log (planet-fixed coordinates on microTech, metres)
PICKUP_1 = (-609564.929403, -688361.107677, 393202.542414)
DROPOFF_1 = (-331479.719964, 896896.374603, -293884.459329)
PICKUP_2 = (843967.867663, -179636.458134, 505728.709821)
MICROTECH_RADIUS = 1_000_000.0


class DatabaseTests(unittest.TestCase):
    def test_database_is_bundled_and_plausible(self):
        m = ships.meta()
        self.assertTrue(m.get("game_version"))
        db = ships._load()["ships"]
        self.assertGreater(len(db), 250)
        for key, s in db.items():
            self.assertEqual(key, s["class"].lower())
            if "qt_fuel" in s:
                self.assertTrue(0 < s["qt_fuel"] < 1000, s["name"])
                self.assertGreaterEqual(len(s["qt_fuel_sources"]), 2, s["name"])
            if "cargo" in s:
                self.assertTrue(0 <= s["cargo"] < 100000, s["name"])
                self.assertGreaterEqual(len(s["cargo_sources"]), 2, s["name"])

    def test_lookup_by_class_and_by_name(self):
        by_class = ships.lookup("RSI_Aurora_Mk2_920601993986")
        by_name = ships.lookup(name="RSI Aurora Mk II")       # as in the ship channel notification
        self.assertEqual(by_class["name"], "RSI Aurora Mk II")
        self.assertIs(by_class, by_name)
        self.assertEqual((by_class["cargo"], by_class["qt_fuel"]), (2.0, 0.9))
        self.assertTrue(by_class["qt_fuel_confirmed"])          # fleetyards agrees with the game files
        self.assertIsNone(ships.lookup("NOPE_Unknown_Ship"))
        self.assertIsNone(ships.lookup(None, None))

    def test_contradicted_values_are_not_shipped(self):
        # modular ship: three sources say 0 SCU, one says 74 -> no cargo figure at all
        self.assertNotIn("cargo", ships.lookup("AEGS_Retaliator"))


class FuelUnitTests(unittest.TestCase):
    """fuel estimate [log] x 1e-6 SCU - checked against geometry."""

    def setUp(self):
        self.aurora = ships.lookup("RSI_Aurora_Mk2")
        # SCU per metre with the stock drive: tank / range
        self.rate = self.aurora["qt_fuel"] / self.aurora["qt_range"]

    def distance(self, estimate):
        return estimate * ships.ESTIMATE_UNIT_SCU / self.rate

    def test_estimates_match_distances_on_microtech(self):
        for estimate, a, b in ((18.180450, PICKUP_1, DROPOFF_1), (17.700329, DROPOFF_1, PICKUP_2)):
            chord = math.dist(a, b)
            arc = 2 * math.asin(chord / (2 * MICROTECH_RADIUS)) * MICROTECH_RADIUS
            d = self.distance(estimate)
            self.assertTrue(chord < d < arc, f"{d / 1000:.0f} km not between {chord / 1000:.0f} and {arc / 1000:.0f}")
            # the other conceivable unit (1e-3 SCU) would be a thousand times too far
            self.assertGreater(d * 1000, 100 * arc)

    def test_wiki_reference_trip_gives_same_rate(self):
        # api.star-citizen.wiki: Port Olisar -> ArcCorp costs the Aurora Mk II 382 tank units (1/1000 SCU)
        distance = 0.382 / self.rate
        self.assertAlmostEqual(distance / 1e9, 41.9, delta=0.5)  # ~42 Gm, the known distance

    def test_tank_share(self):
        self.assertAlmostEqual(ships.tank_share(18.180450, self.aurora), 0.00202, places=5)
        self.assertAlmostEqual(ships.tank_share(382_000, self.aurora), 42.4, places=1)
        self.assertIsNone(ships.tank_share(18.0, None))
        self.assertIsNone(ships.tank_share(None, self.aurora))
        self.assertIsNone(ships.tank_share(18.0, {"name": "x"}))  # ship without tank data


class FuelTextTests(unittest.TestCase):
    def test_share_of_tank_or_scu(self):
        st = DashboardState()
        st.ship, st.ship_class = "Drake Cutlass Black", "DRAK_Cutlass_Black"   # 4.6 SCU tank
        self.assertEqual(st._fuel_text(451872.25), "9,8 % Tank")
        self.assertEqual(st._fuel_text(2_300_000), "50 % Tank")
        self.assertEqual(st._fuel_text(18.18), "< 0,1 % Tank")
        st.ship, st.ship_class = "Mystery Ship", None                           # not in the database
        self.assertEqual(st._fuel_text(451872.25), "0,452 SCU Quantum-Treibstoff")
        self.assertIsNone(st._fuel_text(0))


class RealSessionTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "Game.log")
        with open(FIXTURE, "rb") as fh:
            self.raw = fh.read()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def snapshot_until(self, marker: bytes):
        with open(self.path, "wb") as fh:
            fh.write(self.raw[: self.raw.index(marker)])
        state = DashboardState()
        LogWatcher(lambda: self.path, state).poll()
        return state.snapshot()

    def test_planned_jump_shows_share_of_tank(self):
        # just before arriving at the first target: route plotted, 16.858223 estimated
        nav = self.snapshot_until(b"<2026-11-10T16:32:01")["nav"]
        self.assertEqual(nav["ship"], "RSI Aurora Mk II")
        self.assertEqual(nav["ship_info"]["cargo"], 2.0)
        self.assertAlmostEqual(nav["quantum_need_pct"], 100 * 16.858223e-6 / 0.9, places=6)
        self.assertIsNone(nav["quantum_used_pct"])  # nothing flown yet

    def test_session_consumption(self):
        # in the ship again after three jumps (before leaving it at 17:06)
        nav = self.snapshot_until(b"<2026-11-10T17:06:56")["nav"]
        flown = 16.858223 + 18.180450 + 17.700327 + 11.982203
        self.assertAlmostEqual(nav["quantum_used_pct"], 100 * flown * 1e-6 / 0.9, places=6)
        self.assertLess(nav["quantum_used_pct"], 0.01)  # four hops on one planet: practically nothing


if __name__ == "__main__":
    unittest.main()
