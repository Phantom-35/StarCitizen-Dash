import unittest

from scdash.parser import clean_name, parse_line, pretty_label

TS = "<2026-11-10T18:04:12.345Z>"


class ParserTests(unittest.TestCase):
    def test_ignores_noise(self):
        self.assertIsNone(parse_line(""))
        self.assertIsNone(parse_line("random text"))
        self.assertIsNone(parse_line(f"{TS} [Notice] <Something Else> blah"))

    def test_login(self):
        ev = parse_line(f"{TS} [Notice] <Legacy login response> [CIG-net] User Login Success - Handle[Space_Ben] - Time[1]")
        self.assertEqual(ev.kind, "login")
        self.assertEqual(ev.data["handle"], "Space_Ben")
        self.assertEqual(ev.ts, "2026-11-10T18:04:12.345Z")

    def test_join(self):
        ev = parse_line(f"{TS} [Notice] <Join PU> address[1.2.3.4] port[64300] shard[pub_euw1b_123_100] locationId[-1]")
        self.assertEqual(ev.kind, "join")
        self.assertEqual(ev.data["shard"], "pub_euw1b_123_100")

    def test_location(self):
        ev = parse_line(f"{TS} [Notice] <RequestLocationInventory> Player[Space_Ben] requested inventory for Location[Stanton1_Lorville]")
        self.assertEqual(ev.kind, "location")
        self.assertEqual(ev.data["location"], "Stanton1 Lorville")

    def test_actor_death(self):
        line = (f"{TS} [Notice] <Actor Death> CActor::Kill: 'PU_Human_Enemy_Pirate_123456789' [200] in zone "
                f"'OOC_Stanton_2b_Daymar' killed by 'Space_Ben' [100] using 'behr_rifle_ballistic_01_7654321' "
                f"[Class behr_rifle_ballistic_01] with damage type 'Bullet' from direction x: 0, y: 0, z: 0 [Team_ActorTech][Actor]")
        ev = parse_line(line)
        self.assertEqual(ev.kind, "death")
        self.assertEqual(ev.data["victim"], "PU_Human_Enemy_Pirate")
        self.assertTrue(ev.data["victim_npc"])
        self.assertEqual(ev.data["killer"], "Space_Ben")
        self.assertFalse(ev.data["killer_npc"])
        self.assertEqual(ev.data["weapon"], "behr rifle ballistic 01")
        self.assertEqual(ev.data["damage"], "Bullet")

    def test_vehicle_destruction(self):
        line = (f"{TS} [Notice] <Vehicle Destruction> CVehicle::OnAdvanceDestroyLevel: Vehicle 'DRAK_Cutlass_Black_1234567' "
                f"[1234567] in zone 'OOC_Stanton_2b_Daymar' [pos x: 1, y: 2, z: 3 vel x: 0, y: 0, z: 0] driven by "
                f"'Some_Rival' [5] advanced from destroy level 0 to 2 caused by 'Space_Ben' [100] with 'Combat' [Team_VehicleFeatures][Vehicle]")
        ev = parse_line(line)
        self.assertEqual(ev.kind, "vehicle")
        self.assertEqual(ev.data["vehicle"], "DRAK Cutlass Black")
        self.assertEqual(ev.data["driver"], "Some_Rival")
        self.assertEqual(ev.data["cause"], "Space_Ben")
        self.assertEqual((ev.data["from"], ev.data["to"]), (0, 2))

    def test_clean_name(self):
        self.assertEqual(clean_name("ANVL_Arrow_12345678"), "ANVL_Arrow")
        self.assertEqual(clean_name("Player_01"), "Player_01")  # short numbers are kept
        self.assertEqual(pretty_label("Stanton2_Orison"), "Stanton2 Orison")


if __name__ == "__main__":
    unittest.main()
