"""Survival, law and money events of current (4.4+) builds.

Kill lines are no longer written since ~4.4, but deaths, incaps, injuries, med beds,
crimes and transfers are. The sample lines below are NOT copied from a real log: they are
built from the patterns that the open-source parsers all-slain, csr and sc-log-tracker use
against real 4.x logs (see README, "Quellen"). Replace them with real lines when available.
"""

import unittest

from scdash.parser import classify_notification, parse_line
from scdash.state import DashboardState

ME = "TestPilot"


def ts(minute, second=0):
    return f"<2026-11-10T18:{minute:02d}:{second:02d}.000Z>"


def notif(text, t=ts(0)):
    return (f'{t} [Notice] <SHUDEvent_OnNotification> Added notification "{text}: " [5] to queue. New queue size: 1, '
            f"MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]")


LOGIN = f"{ts(0)} [Notice] <Legacy login response> [CIG-net] User Login Success - Handle[{ME}] - Time[1] [Team_GameServices][Login]"
JOIN = f"{ts(0)} [Notice] <Join PU> address[10.0.0.1] port[64300] shard[pub_euw1b_1_1] locationId[1] [Team_GameServices][GIM]"


def dead(actor, t, ship=None, destroyed=False, to="OOC_Stanton_2b_Daymar"):
    src = f" ejected from zone '{ship}_123456789'" if ship else ""
    why = " (destroyed vehicle)" if destroyed else ""
    return (f"{t} [Notice] <[ActorState] Dead> [ACTOR STATE][SSCActorStateCVars::LogDead] Actor '{actor}' [100]"
            f"{src}{why} to zone '{to}' [Team_ActorFeatures][Actor]")


def corpse(player, t, who="local"):
    return (f"{t} [Notice] <[ActorState] Corpse> [ACTOR STATE][SSCActorStateCVars::LogCorpse] Player '{player}' "
            f"<{who} client>: Running corpsify for corpse. [Team_ActorFeatures][Actor]")


INCAP = f"{ts(30)} [Notice] <Incap> Logged an incap.! nickname: {ME}, causes: [BulletDamage (45.5 damage), FallDamage (3.0 damage)]"
MEDBED = (f"{ts(40)} [Notice] <MED BED HEAL> Actor: {ME} (Non-Authoritative CLIENT: {ME}) | "
          f"[CEntityComponentMedBed::HandleComponentEvent:123] | -> Perform surgery event Success, med bed name: MedBed_T2, "
          f"vehicle name: RSI_Constellation_Taurus_123456, head: false torso: true leftArm: true rightArm: false "
          f"leftLeg: false rightLeg: false [Team_ActorFeatures][Actor]")


def collision(pilot, t):
    return (f"{t} [Notice] <FatalCollision> Fatal Collision occured for vehicle ANVL_Arrow_123456789 [1] "
            f"[Part: body, Zone: OOC_Stanton_1_Hurston, PlayerPilot: {pilot}] [Team_VehicleFeatures][Vehicle]")


class SurvivalTests(unittest.TestCase):
    def run_lines(self, *lines):
        st = DashboardState()
        for line in (LOGIN, JOIN) + lines:
            ev = parse_line(line)
            if ev is not None:
                st.apply(ev)
        return st.snapshot()

    def test_death_counted_once(self):
        s = self.run_lines(dead(ME, ts(10), ship="RSI_Aurora_Mk2", destroyed=True), corpse(ME, ts(10, 40)))
        self.assertEqual(s["stats"]["deaths"], 1)
        self.assertEqual(s["session"]["last_death"]["cause"], "Schiff zerstört")
        self.assertEqual(s["session"]["last_death"]["who"], "RSI Aurora Mk2")
        self.assertEqual(s["session"]["last_death"]["where"], "Daymar")
        self.assertEqual(s["session"]["alive_since"], "2026-11-10T18:10:00.000Z")
        self.assertEqual(s["stats"]["best_alive"], 600.0)
        self.assertTrue(s["feeds"]["combat"][0]["banner"])

    def test_two_deaths(self):
        s = self.run_lines(dead(ME, ts(10)), dead(ME, ts(20)))
        self.assertEqual(s["stats"]["deaths"], 2)

    def test_other_players_do_not_count(self):
        s = self.run_lines(dead("SomeoneElse", ts(10)), corpse("SomeoneElse", ts(11), who="remote"))
        self.assertEqual(s["stats"]["deaths"], 0)
        self.assertEqual(s["feeds"]["combat"][0]["actor"], "SomeoneElse")

    def test_incap_line_and_hud_counted_once(self):
        s = self.run_lines(INCAP, notif("Incapacitated: Bleeding Out", ts(30, 2)))
        self.assertEqual(s["stats"]["incaps"], 1)
        self.assertEqual(s["feeds"]["combat"][0]["actor"], "Bullet, Fall")
        self.assertEqual(s["stats"]["deaths"], 0)  # incapacitated is not dead

    def test_medbed(self):
        s = self.run_lines(MEDBED)
        self.assertEqual(s["stats"]["medbed"], 1)
        ev = s["feeds"]["combat"][0]
        self.assertEqual((ev["actor"], ev["detail"]), ("Torso, linker Arm", "RSI Constellation Taurus"))

    def test_collision_only_when_piloting(self):
        s = self.run_lines(collision(0, ts(5)), collision(1, ts(6)))
        self.assertEqual(s["stats"]["collisions"], 1)
        self.assertEqual(s["feeds"]["combat"][0]["actor"], "Anvil Arrow")

    def test_legacy_kill_lines_still_work(self):
        line = (f"{ts(3)} [Notice] <Actor Death> CActor::Kill: '{ME}' [1] in zone 'OOC_Stanton_2b_Daymar' killed by "
                f"'Bob' [2] using 'gun_1234567' [Class gun] with damage type 'Bullet' from direction x: 0")
        s = self.run_lines(line, corpse(ME, ts(3, 30)))
        self.assertEqual(s["stats"]["deaths"], 1)
        self.assertEqual(s["session"]["last_killer"]["name"], "Bob")


class HudNotificationTests(unittest.TestCase):
    def test_categories(self):
        cases = {
            "Minor Injury Detected - Left Arm - Tier 3 Treatment Required": ("injury", {"sev": "Minor", "part": "Left Arm", "tier": "3"}),
            "CrimeStat Rating Increased": ("crime_up", {}),
            "Crime Committed: Assault": ("crime", {}),
            "Fined 1500 UEC": ("fined", {"amount": 1500}),
            "Bob has sent you: 25,000 aUEC": ("money_received", {"who": "Bob", "amount": 25000}),
            "You sent Bob: 1.000 aUEC": ("money_sent", {"amount": 1000}),
            "A Refinery Work Order has been Completed at ARC-L1 Wide Forest Station": ("refinery", {}),
            "Restricted Area - Vehicles will be impounded": ("restricted_on", {}),
            "Monitored Space Down": ("monitored_down", {}),
            "Journal Entry Added: Jurisdiction: Ungoverned": ("jurisdiction", {}),
            "Standby, Local Emergency Services are en route": ("rescue", {}),
        }
        for text, (cat, extra) in cases.items():
            c = classify_notification(text + ": ")
            self.assertEqual(c["category"], cat, text)
            for k, v in extra.items():
                self.assertEqual(c[k], v, text)

    def test_markup_is_removed(self):
        c = classify_notification("Contract Accepted: <EM4>Help Protect Site [500 Rep] [BP]*</EM4>: ")
        self.assertEqual((c["category"], c["subject"]), ("accepted", "Help Protect Site"))

    def test_ship_channel_with_vehicle_tag(self):
        c = classify_notification("You have joined channel '@vehicle_NameRSI Aurora Mk II : Pilot'.")
        self.assertEqual((c["category"], c["subject"]), ("channel_joined", "RSI Aurora Mk II"))

    def test_state_effects(self):
        st = DashboardState()
        for line in (
            LOGIN,
            notif("CrimeStat Rating Increased", ts(1)),
            notif("Fined 500 UEC", ts(2)),
            notif("Bob has sent you: 10000 aUEC", ts(3)),
            notif("Entered Hurston Jurisdiction", ts(4)),
            notif("Entered Crusader Jurisdiction", ts(4, 10)),
            notif("Entered Hurston Jurisdiction", ts(4, 20)),  # border ping-pong: no new feed entry
            notif("Restricted Area - Vehicles will be impounded", ts(5)),
        ):
            st.apply(parse_line(line))
        s = st.snapshot()
        self.assertEqual((s["stats"]["crimestat"], s["stats"]["fines"], s["stats"]["money_in"]), (1, 500, 10000))
        self.assertEqual(s["nav"]["jurisdiction"], "Hurston")
        juris = [e for e in s["feeds"]["mission"] if e["title"] == "Jurisdiktion"]
        self.assertEqual([e["actor"] for e in juris], ["Crusader", "Hurston"])  # newest first, flap suppressed
        self.assertTrue(s["nav"]["restricted"])


class BannerContentTests(unittest.TestCase):
    """The banner shows actor (big) and title (small); without an actor the title is the headline.
    So events must not put a place into the actor slot where the title is the actual news."""

    def run_lines(self, *lines):
        st = DashboardState()
        for line in (LOGIN, JOIN) + lines:
            ev = parse_line(line)
            if ev is not None:
                st.apply(ev)
        return st.snapshot()

    def test_plain_death_has_place_as_detail(self):
        ev = self.run_lines(dead(ME, ts(10)))["feeds"]["combat"][0]
        self.assertEqual((ev["title"], ev["actor"], ev["detail"]), ("Gestorben", "", "Daymar"))

    def test_ship_death_names_the_ship(self):
        ev = self.run_lines(dead(ME, ts(10), ship="RSI_Aurora_Mk2", destroyed=True))["feeds"]["combat"][0]
        self.assertEqual((ev["title"], ev["actor"], ev["detail"]), ("Schiff zerstört", "RSI Aurora Mk2", "Daymar"))

    def test_crimestat_has_no_actor(self):
        ev = self.run_lines(notif("CrimeStat Rating Increased", ts(1)))["feeds"]["combat"][0]
        self.assertEqual((ev["title"], ev["actor"], ev["banner"]), ("CrimeStat erhöht", "", True))


class UsefulnessTests(unittest.TestCase):
    """Things that are shown because they help while playing."""

    def feed(self, *lines):
        st = DashboardState()
        for line in (LOGIN, JOIN) + lines:
            ev = parse_line(line)
            if ev is not None:
                st.apply(ev)
        return st.snapshot()

    def test_open_injuries_until_med_bed(self):
        s = self.feed(notif("Minor Injury Detected - Left Arm - Tier 3 Treatment Required", ts(1)),
                      notif("Severe Injury Detected - Head - Tier 1 Treatment Required", ts(2)))
        self.assertEqual([(i["part"], i["tier"], i["severe"]) for i in s["health"]["injuries"]],
                         [("linker Arm", 3, False), ("Kopf", 1, True)])
        s = self.feed(notif("Minor Injury Detected - Left Arm - Tier 3 Treatment Required", ts(1)),
                      notif("Severe Injury Detected - Head - Tier 1 Treatment Required", ts(2)), MEDBED)
        # the med bed line lists torso + left arm: the head stays injured
        self.assertEqual([i["part"] for i in s["health"]["injuries"]], ["Kopf"])
        s = self.feed(notif("Minor Injury Detected - Left Arm - Tier 3 Treatment Required", ts(1)), dead(ME, ts(5)))
        self.assertEqual(s["health"]["injuries"], [])

    def test_crew_aboard(self):
        s = self.feed(notif("You have joined channel 'Drake Cutlass Black : TestPilot'.", ts(1)),
                      notif("New Member Joined Bob has joined channel 'Drake Cutlass Black : TestPilot'", ts(2)),
                      notif("New Member Joined Alice has joined channel 'Drake Cutlass Black : TestPilot'", ts(3)),
                      notif("Member Left Bob has left the channel 'Drake Cutlass Black : TestPilot'", ts(4)))
        self.assertEqual(s["nav"]["crew"], ["Alice"])
        self.assertEqual(s["nav"]["ship"], "Drake Cutlass Black")

    def test_purchases_count_as_spending(self):
        # reconstructed from the field names sc-log-tracker / csr parse (4.8+ SendShopBuyRequest)
        item = (f"{ts(1)} [Notice] <CEntityComponentShopUIProvider::SendShopBuyRequest> Sending SShopBuyRequest - "
                f"playerId[1] shopId[2] shopName[SCShop_CasabaOutlet_NewBabbage_123] kioskId[3] client_price[4500.000000] "
                f"itemClassGUID[x] itemName[Flight_Suit_Blue_123456789] quantity[2] [Team_NAPU][Shops][UI]")
        cargo = (f"{ts(2)} [Notice] <CEntityComponentCommodityUIProvider::SendCommodityBuyRequest> Sending "
                 f"SShopCommodityBuyRequest - playerId[1] shopName[SCShop_TDD] price[12000.500000] resourceGUID[y] "
                 f"quantity[800] [Team_NAPU][Shops][UI]")
        s = self.feed(item, cargo)
        self.assertEqual((s["stats"]["purchases"], s["stats"]["spend"]), (2, 16500))
        self.assertEqual(s["feeds"]["mission"][1]["actor"], "2× Flight Suit Blue")

    def test_connection_error(self):
        line = (f'{ts(9)} [Notice] <Channel Disconnected> cause=30000 reason="Connection timed out" frame=1 '
                f'map="megamap" gamerules="SC_Default" hostType="GameClient"')
        s = self.feed(line, line.replace("18:09:00", "18:09:05"))  # reported twice within seconds
        self.assertEqual(s["stats"]["disconnects"], 1)
        ev = s["feeds"]["combat"][0]
        self.assertEqual((ev["title"], ev["actor"], ev["banner"]), ("Verbindungsfehler 30000", "Zeitüberschreitung der Verbindung", True))

    def test_next_target_of_contract(self):
        s = self.feed(
            f'{ts(1)} [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Haul: " [1] to queue. MissionId: [h1], ObjectiveId: []',
            f'{ts(1)} [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Deliver 0/24 SCU of Agricium to Seraphim Station: " [2] to queue. MissionId: [h1], ObjectiveId: [dropoff_1]',
            f'{ts(1)} [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Collect Agricium From HDMS-Edmond on Hurston: " [3] to queue. MissionId: [h1], ObjectiveId: [pickup_1]',
        )
        m = s["missions"]["active"][0]
        self.assertEqual(m["next"], {"place": "HDMS-Edmond", "detail": None, "learned": False})  # pick-up first


class QuantumTargetTests(unittest.TestCase):
    def test_mission_marker_uses_objective(self):
        st = DashboardState()
        for line in (
            f'{ts(0)} [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Courier: " [1] to queue. '
            f"MissionId: [m1], ObjectiveId: []",
            f'{ts(0)} [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Collect Medical Supplies From '
            f'Clear View Emergency Shelter on microTech: " [2] to queue. MissionId: [m1], ObjectiveId: [pickup_1]',
            f"{ts(1)} [Notice] <Player Selected Quantum Target - Local> [ItemNavigation][CL][1] | NOT AUTH | "
            f"RSI_Aurora_Mk2_920601993986[920601993986]|CSCItemNavigation::OnPlayerSelectedQuantumTarget|Player has selected "
            f"point em_shelter_001_frost_{{511D51FF-50C7-457A-A1A6-A96AC7832658}}.socpak as their destination, routing locally",
        ):
            st.apply(parse_line(line))
        self.assertEqual(st.snapshot()["nav"]["quantum_target"], "Auftragsziel · Clear View Emergency Shelter")


if __name__ == "__main__":
    unittest.main()
