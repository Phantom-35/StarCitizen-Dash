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

_KILL = "<{ts}> [Notice] <Actor Death> CActor::Kill: '%s_{n}' [{n}] in zone '%s' killed by '{me}' [1] using '%s_{n}' [Class x] with damage type '%s' from direction x: 0, y: 0, z: 0 [Team_ActorTech][Actor]"
_DEATH = "<{ts}> [Notice] <Actor Death> CActor::Kill: '{me}' [1] in zone '%s' killed by '%s' [{n}] using '%s_{n}' [Class x] with damage type '%s' from direction x: 0, y: 0, z: 0 [Team_ActorTech][Actor]"
_SHIP = "<{ts}> [Notice] <Vehicle Destruction> CVehicle::OnAdvanceDestroyLevel: Vehicle '%s_{n}' [{n}] in zone '%s' [pos x: 0, y: 0, z: 0 vel x: 0, y: 0, z: 0] driven by '%s' [{n}] advanced from destroy level 0 to 2 caused by '{me}' [1] with 'Combat' [Team_VehicleFeatures][Vehicle]"
_LOC = "<{ts}> [Notice] <RequestLocationInventory> Player[{me}] requested inventory for Location[%s] [Team_CoreGameplayFeatures][Inventory]"

_RANDOM = [
    _KILL % ("PU_Human_Enemy_GroundCombat_NPC_Pirate", "OOC_Stanton_2b_Daymar", "behr_rifle_ballistic_01", "Bullet"),
    _KILL % ("PU_Human_Enemy_GroundCombat_NPC_Outlaw", "OOC_Stanton_1b_Aberdeen", "ksar_smg_energy_01", "Energy"),
    _KILL % ("PU_Human_Enemy_GroundCombat_NPC_Pirate", "OOC_Stanton_2b_Daymar", "gmni_lmg_ballistic_01", "Bullet"),
    "<{ts}> [Notice] <Actor Death> CActor::Kill: 'xX_Nova_Reaper_Xx' [{n}] in zone 'ANVL_Arrow_{n}' killed by '{me}' [1] using 'KLWE_LaserRepeater_S3_{n}' [Class x] with damage type 'Energy' from direction x: 0, y: 0, z: 0 [Team_ActorTech][Actor]",
    _DEATH % ("OOC_Stanton_2b_Daymar", "Outlaw_Joe", "ksar_sniper_ballistic_01", "Bullet"),
    _SHIP % ("DRAK_Cutlass_Black", "OOC_Stanton_2b_Daymar", "Some_Rival"),
    _SHIP % ("AEGS_Gladius", "Stanton2", "Red_Baron_77"),
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
        _N2 % ("Objective Complete: Collect 3 packages at Lorville Spaceport", a, "o1"),
        _N % ("New Objective: Deliver 0/3 packages to Everus Harbor", a, "o2"),
        _N2 % ("You have joined channel 'Drake Cutlass Black : {me}'.", _ZERO, ""),
        _N % ("Hangar Request Completed", _ZERO, ""),
        _N % ("Leaving Armistice Zone - Caution Advised", _ZERO, ""),
        _QT_SET % "EverusHarbor_LOC",
        _QT_DONE,
        _LOC % "Stanton1_Everus",
        _N % ("Entering Armistice Zone - Combat Prohibited", _ZERO, ""),
        _N % ("New Objective: Deliver 3/3 packages to Everus Harbor", a, "o2"),
        _UPSERT % (a, "o2"),
        "<{ts}> [Notice] <MissionEnded> Received MissionEnded push message for: mission_id %s - mission_state MISSION_STATE_COMPLETED [Team_GameServices][Missions]" % a,
        _END % (a, "Complete"),
        _N % ("Contract Complete: Covalex Local Delivery", a, ""),
        _N % ("Objective Complete: Pick up 24 SCU Agricium at HDMS-Edmond", b, "o1"),
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
            if random.random() < 0.6:
                if not script:
                    loop += 1
                    script = mission_script(loop)
                self._write(script.pop(0))
            else:
                self._write(random.choice(_RANDOM))
