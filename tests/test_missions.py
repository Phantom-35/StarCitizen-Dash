import unittest

from scdash.parser import classify_notification, parse_line
from scdash.state import DashboardState

T = "<2026-11-10T18:00:00.000Z> [Notice] "
T2 = "<2026-11-10T18:12:30.000Z> [Notice] "


def notif(text, mid="", oid="", ts=T):
    return (f'{ts}<SHUDEvent_OnNotification> Added notification "{text}: " [11] to queue. '
            f"New queue size: 1, MissionId: [{mid}], ObjectiveId: [{oid}] [Team_CoreGameplayFeatures][Missions][Comms]")


class ClassifyTests(unittest.TestCase):
    def test_categories(self):
        cases = {
            "Contract Accepted: Covalex Delivery": ("accepted", "Covalex Delivery"),
            "Contract Complete: Covalex Delivery": ("completed", "Covalex Delivery"),
            "Contract Failed: Covalex Delivery": ("failed", "Covalex Delivery"),
            "New Objective: Deliver 0/4 SCU": ("objective_new", "Deliver 0/4 SCU"),
            "Objective Complete: Deliver 4/4 SCU": ("objective_done", "Deliver 4/4 SCU"),
            "Entering Armistice Zone - Combat Prohibited": ("armistice_on", "Entering Armistice Zone - Combat Prohibited"),
            "Leaving Armistice Zone": ("armistice_off", "Leaving Armistice Zone"),
            "Entered Hurston Dynamics Jurisdiction": ("jurisdiction", "Hurston Dynamics"),
            "Something new from CIG": ("comms", "Something new from CIG"),
        }
        for text, (cat, subject) in cases.items():
            c = classify_notification(text + ": ")
            self.assertEqual((c["category"], c["subject"]), (cat, subject), text)

    def test_null_mission_id(self):
        ev = parse_line(notif("Leaving Armistice Zone", mid="00000000-0000-0000-0000-000000000000"))
        self.assertIsNone(ev.data["mission_id"])


class MissionFlowTests(unittest.TestCase):
    def feed(self, st, *lines):
        for line in lines:
            ev = parse_line(line)
            self.assertIsNotNone(ev, line)
            st.apply(ev)

    def test_full_contract(self):
        st = DashboardState()
        self.feed(
            st,
            notif("Contract Accepted: Covalex Delivery", mid="m1"),
            notif("New Objective: Pick up 4 SCU at Lorville", mid="m1", oid="o1"),
            notif("New Objective: Deliver 0/4 SCU to Seraphim", mid="m1", oid="o2"),
            notif("Objective Complete: Pick up 4 SCU at Lorville", mid="m1", oid="o1"),
        )
        s = st.snapshot()
        active = s["missions"]["active"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["title"], "Covalex Delivery")
        self.assertEqual([o["state"] for o in active[0]["objectives"]], ["done", "open"])

        # objective text update keeps the same entry
        self.feed(st, notif("New Objective: Deliver 2/4 SCU to Seraphim", mid="m1", oid="o2"))
        objs = st.snapshot()["missions"]["active"][0]["objectives"]
        self.assertEqual(objs[1]["text"], "Deliver 2/4 SCU to Seraphim")

        # completion via notification, then the duplicate EndMission line is ignored
        self.feed(
            st,
            notif("Contract Complete: Covalex Delivery", mid="m1", ts=T2),
            f"{T2}<EndMission> Ending mission for player. MissionId[m1] Player[Me] PlayerId[1] CompletionType[Complete] Reason[]",
        )
        s = st.snapshot()
        self.assertEqual(s["missions"]["active"], [])
        self.assertEqual(s["stats"]["missions_completed"], 1)
        self.assertEqual(s["missions"]["history"][0]["result"], "completed")
        self.assertEqual(s["missions"]["history"][0]["duration"], 750.0)
        self.assertTrue(s["feeds"]["mission"][0]["banner"])
        self.assertEqual(s["feeds"]["combat"], [])  # missions do not spam the combat feed

    def test_most_recently_active_mission_first(self):
        st = DashboardState()
        self.feed(
            st,
            notif("Contract Accepted: A", mid="a"),
            notif("Contract Accepted: B", mid="b"),
        )
        self.assertEqual(st.snapshot()["missions"]["active"][0]["title"], "B")
        self.feed(st, notif("New Objective: do A things", mid="a", oid="1"))
        self.assertEqual(st.snapshot()["missions"]["active"][0]["title"], "A")

    def test_end_mission_line_and_failure(self):
        st = DashboardState()
        self.feed(
            st,
            notif("Contract Accepted: Bounty", mid="b1"),
            f"{T}<EndMission> Ending mission for player. MissionId[b1] Player[Me] PlayerId[1] CompletionType[Fail] Reason[x]",
        )
        s = st.snapshot()
        self.assertEqual(s["stats"]["missions_failed"], 1)
        self.assertEqual(s["missions"]["history"][0]["title"], "Bounty")

    def test_objective_without_contract(self):
        st = DashboardState()
        self.feed(st, notif("New Objective: Go to Yela", mid="x9", oid="o1"))
        active = st.snapshot()["missions"]["active"]
        self.assertEqual(active[0]["title"], "Laufender Auftrag")
        self.assertEqual(active[0]["objectives"][0]["text"], "Go to Yela")

    def test_zones_and_ship(self):
        st = DashboardState()
        self.feed(
            st,
            notif("Entering Armistice Zone - Combat Prohibited"),
            notif("Entered Crusader Industries Jurisdiction"),
            f"{T}<Vehicle Control Flow> CVehicleMovementBase::SetDriver: Local client node [1] requesting control "
            f"token for 'MISC_Prospector_1234567' [1234567] [Team_VehicleFeatures][Vehicle]",
        )
        nav = st.snapshot()["nav"]
        self.assertEqual((nav["armistice"], nav["jurisdiction"], nav["ship"]), (True, "Crusader Industries", "MISC Prospector"))
        self.feed(st, notif("Leaving Armistice Zone"),
                  f"{T}<Vehicle Control Flow> CVehicleMovementBase::ClearDriver: Local client node [1] releasing "
                  f"control token for 'MISC_Prospector_1234567' [1234567]")
        nav = st.snapshot()["nav"]
        self.assertEqual((nav["armistice"], nav["ship"]), (False, None))


if __name__ == "__main__":
    unittest.main()
