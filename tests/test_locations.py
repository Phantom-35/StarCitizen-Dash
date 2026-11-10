import unittest

from scdash.locations import describe_location, shard_region, ship_name, weapon_name


class LocationTests(unittest.TestCase):
    def test_cities(self):
        self.assertEqual(describe_location("Stanton2_Orison"), {"system": "Stanton", "planet": "Crusader", "place": "Orison"})
        self.assertEqual(describe_location("Stanton4_NewBabbage")["place"], "New Babbage")

    def test_moon_has_parent_planet(self):
        self.assertEqual(describe_location("OOC_Stanton_2b_Daymar"), {"system": "Stanton", "planet": "Crusader", "place": "Daymar"})

    def test_rest_stop(self):
        loc = describe_location("RR_HUR_LEO")
        self.assertEqual((loc["planet"], loc["place"]), ("Hurston", "R&R HUR-LEO"))

    def test_ship_zone(self):
        self.assertEqual(describe_location("ANVL_Arrow_1234567")["place"], "Anvil Arrow")

    def test_unknown(self):
        self.assertEqual(describe_location("weird_thing")["place"], "weird thing")

    def test_shard_region(self):
        self.assertEqual(shard_region("pub_euw1b_9876543_100"), "EU West")
        self.assertEqual(shard_region("pub_use1a_1_1"), "US East")
        self.assertIsNone(shard_region(None))
        self.assertIsNone(shard_region("garbage"))

    def test_names(self):
        self.assertEqual(ship_name("DRAK_Cutlass_Black_1234567"), "Drake Cutlass Black")
        self.assertEqual(weapon_name("ksar_sniper_ballistic_01_123456"), "Kastak Arms Sniper Ballistic")
        self.assertIsNone(weapon_name("unknown"))


if __name__ == "__main__":
    unittest.main()
