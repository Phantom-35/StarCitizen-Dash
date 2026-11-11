"""Demo mode: writes a fake Game.log so the dashboard can be tried without the game."""

from __future__ import annotations

import os
import random
import tempfile
import threading
from datetime import datetime, timezone

HANDLE = "Demo_Pilot"

_STATIC = [
    "<{ts}> ProductVersion: 4.10.197.2878",
    "<{ts}> [Notice] <Legacy login response> [CIG-net] User Login Success - Handle[{me}] - Time[123456] [Team_GameServices][Login]",
    "<{ts}> [Notice] <Join PU> address[10.0.0.1] port[64300] shard[pub_euw1b_9876543_100] locationId[-281470681743359] [Team_GameServices][GIM]",
    "<{ts}> [Notice] <RequestLocationInventory> Player[{me}] requested inventory for Location[Stanton1_Lorville] [Team_CoreGameplayFeatures][Inventory]",
]

_LOC = "<{ts}> [Notice] <RequestLocationInventory> Player[{me}] requested inventory for Location[%s] [Team_CoreGameplayFeatures][Inventory]"
_HUD = '<{ts}> [Notice] <SHUDEvent_OnNotification> Added notification "%s: " [7] to queue. New queue size: 1, MissionId: [00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]'

# Since ~4.4 the game no longer logs kills - only what happens to you. These lines follow
# the formats used by the open-source parsers all-slain, csr and sc-log-tracker.
_RANDOM = [
    "<{ts}> [Notice] <[ActorState] Dead> [ACTOR STATE][SSCActorStateCVars::LogDead] Actor '{me}' [1] ejected from zone 'DRAK_Cutlass_Black_{n}' (destroyed vehicle) to zone 'OOC_Stanton_2b_Daymar' [Team_ActorFeatures][Actor]",
    "<{ts}> [Notice] <[ActorState] Dead> [ACTOR STATE][SSCActorStateCVars::LogDead] Actor '{me}' [1] to zone 'OOC_Stanton_1b_Aberdeen' [Team_ActorFeatures][Actor]",
    "<{ts}> [Notice] <Incap> Logged an incap.! nickname: {me}, causes: [BulletDamage (61.2 damage)]",
    _HUD % "Moderate Injury Detected - Right Leg - Tier 2 Treatment Required",
    _HUD % "Minor Injury Detected - Left Arm - Tier 3 Treatment Required",
    "<{ts}> [Notice] <MED BED HEAL> Actor: {me} (Non-Authoritative CLIENT: {me}) | [CEntityComponentMedBed::HandleComponentEvent:1] | -> Perform surgery event Success, med bed name: MedBed_T3, vehicle name: DRAK_Cutlass_Black_{n}, head: false torso: true leftArm: true rightArm: false leftLeg: false rightLeg: true [Team_ActorFeatures][Actor]",
    _HUD % "CrimeStat Rating Increased",
    _HUD % "Standby, Local Emergency Services are en route",
    "<{ts}> [Notice] <FatalCollision> Fatal Collision occured for vehicle ANVL_Arrow_{n} [{n}] [Part: body, Zone: OOC_Stanton_2b_Daymar, PlayerPilot: 1] [Team_VehicleFeatures][Vehicle]",
    _HUD % "Bob_the_Hauler has sent you: 15000 aUEC",
    _LOC % "Stanton2_Orison",
    _LOC % "Stanton4_NewBabbage",
    _LOC % "RR_HUR_LEO",
]
_N = '<{ts}> [Notice] <SHUDEvent_OnNotification> Added notification "%s: " [11] to queue. New queue size: 1, MissionId: [%s], ObjectiveId: [%s] [Team_CoreGameplayFeatures][Missions][Comms]'
_PILOT = "<{ts}> [Notice] <Vehicle Control Flow> CVehicleMovementBase::SetDriver: Local client node [1] requesting control token for '%s_{n}' [{n}] [Team_VehicleFeatures][Vehicle]"
# Some notifications contain a line break in the real log - keep that quirk in the demo.
_N2 = ('<{ts}> [Notice] <SHUDEvent_OnNotification> Added notification "%s\r\n<{ts}> : " [11] to queue. '
       'New queue size: 1, MissionId: [%s], ObjectiveId: [%s] [Team_CoreGameplayFeatures][Missions][Comms]')
_UPSERT = ("<{ts}> [Notice] <ObjectiveUpserted> Received ObjectiveUpserted push message for: mission_id %s - "
           "objective_id %s - state MISSION_OBJECTIVE_STATE_COMPLETED - created 0 - flags=ShowInLog| [Team_GameServices][Missions]")
_QT_SET = ("<{ts}> [Notice] <Player Selected Quantum Target - Local> [ItemNavigation][CL][1] | NOT AUTH | DRAK_Cutlass_Black_{n}[{n}]|"
           "CSCItemNavigation::OnPlayerSelectedQuantumTarget|Player has selected point %s as their destination, routing locally [Team_CGP4][QuantumTravel]")
_QT_DONE = ("<{ts}> [Notice] <Quantum Drive Arrived - Arrived at Final Destination> [ItemNavigation][CL][1] | NOT AUTH | DRAK_Cutlass_Black_{n}[{n}]|"
            "CSCItemNavigation::OnQuantumDriveArrived|Quantum Drive has arrived at final destination [Team_CGP4][QuantumTravel]")
_PLACE = ("<{ts}> [Notice] <[ActorState] Place> [ACTOR STATE][CSCActorControlAdditiveStatePlace::DoPlace] '{me}' [1] placed "
          "'Carryable_2H_FL_05x05x05_Commodity_%s_a_{n}' [{n}] in lootable container '%s' [{n}] [Team_ActorFeatures][Actor]")
_BUY = ("<{ts}> [Notice] <CEntityComponentShopUIProvider::SendShopBuyRequest> Sending SShopBuyRequest - playerId[1] "
        "shopName[SCShop_%s] client_price[%s] itemName[%s] quantity[%s] [Team_NAPU][Shops][UI]")
_ZERO = "00000000-0000-0000-0000-000000000000"
_END = "<{ts}> [Notice] <EndMission> Ending mission for player. MissionId[%s] Player[{me}] PlayerId[1] CompletionType[%s] Reason[]"


def mission_script(c: int) -> list:
    """One loop of a hauling evening; ``c`` makes mission ids unique per loop."""
    a, b, x = f"demo-a-{c}", f"demo-b-{c}", f"demo-x-{c}"
    return [
        _LOC % "Stanton1_Lorville",
        _N % ("Contract Accepted: Covalex Local Delivery", a, ""),
        _N % ("New Objective: Collect 3 packages at Lorville Spaceport", a, "o1"),
        _N % ("Contract Accepted: Hauling - Hurston to Crusader", b, ""),
        _N % ("New Objective: Pick up 24 SCU Agricium at HDMS-Edmond", b, "o1"),
        _N % ("New Objective: Deliver 0/24 SCU to Seraphim Station", b, "o2"),
        _PLACE % ("medical_supplies", "drak_cutlass_black_cargo_slot"),
        _N2 % ("Objective Complete: Collect 3 packages at Lorville Spaceport", a, "o1"),
        _N % ("New Objective: Deliver 0/3 packages to Everus Harbor", a, "o2"),
        _N2 % ("You have joined channel 'Drake Cutlass Black : {me}'.", _ZERO, ""),
        _N % ("New Member Joined Bob_the_Hauler has joined channel 'Drake Cutlass Black : {me}'", _ZERO, ""),
        _N % ("Hangar Request Completed", _ZERO, ""),
        _N % ("Leaving Armistice Zone - Caution Advised", _ZERO, ""),
        _QT_SET % "EverusHarbor_LOC",
        "<{ts}> [Notice] <Calculate Route> [ItemNavigation][CL][1] | NOT AUTH | DRAK_Cutlass_Black_{n}[{n}]|CSCItemNavigation::CalculateRoute|Successfully calculated route to EverusHarbor_LOC fuel estimate 23.417050 [Team_CGP4][QuantumTravel]",
        _N % ("Entered Monitored Space", _ZERO, ""),
        _QT_DONE,
        _LOC % "RR_HUR_LEO",
        _N % ("Entering Armistice Zone - Combat Prohibited", _ZERO, ""),
        _N % ("New Objective: Deliver 3/3 packages to Everus Harbor", a, "o2"),
        _PLACE % ("medical_supplies", "Mission_InvisibleItemPort_2H-010"),
        _UPSERT % (a, "o2"),
        "<{ts}> [Notice] <MissionEnded> Received MissionEnded push message for: mission_id %s - mission_state MISSION_STATE_COMPLETED [Team_GameServices][Missions]" % a,
        _END % (a, "Complete"),
        _N % ("Contract Complete: Covalex Local Delivery", a, ""),
        _BUY % ("Refuel_EverusHarbor", "1850.000000", "Hydrogen_Fuel", "1"),
        _N % ("Objective Complete: Pick up 24 SCU Agricium at HDMS-Edmond", b, "o1"),
        _N % ("New Objective: Deliver 8/24 SCU to Seraphim Station", b, "o2"),
        _N % ("Entered Crusader Jurisdiction", _ZERO, ""),
        _N % ("Contract Accepted: Retrieve Stolen Cargo", x, ""),
        _N % ("New Objective: Recover cargo from wreck near Yela", x, "o1"),
        _N % ("Exited Monitored Space", _ZERO, ""),
        _N % ("Contract Failed: Retrieve Stolen Cargo", x, ""),
        _N % ("Entered Monitored Space", _ZERO, ""),
        _N % ("Contract Available: Covalex Shipping: Rush Delivery", f"demo-o-{c}", ""),
        _LOC % "Stanton2_Seraphim",
    ]


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class DemoLogWriter(threading.Thread):
    def __init__(self, interval: float = 4.0) -> None:
        super().__init__(name="scdash-demo", daemon=True)
        self.interval = interval
        fd, self.path = tempfile.mkstemp(prefix="scdash-demo-", suffix=".log")
        os.close(fd)
        self._halt = threading.Event()

    def _write(self, template: str) -> None:
        line = template.format(ts=_ts(), me=HANDLE, n=random.randint(100000, 9999999))
        with open(self.path, "a", encoding="utf-8", newline="") as fh:
            fh.write(line + "\r\n")

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        for t in _STATIC:
            self._write(t)
        loop, script = 0, mission_script(0)
        while not self._halt.wait(self.interval):
            # alternate between the mission story and random combat noise
            if random.random() < 0.65:
                if not script:
                    loop += 1
                    script = mission_script(loop)
                self._write(script.pop(0))
            else:
                self._write(random.choice(_RANDOM))
