"""Demo mode: writes a fake Game.log so the dashboard can be tried without the game."""

from __future__ import annotations

import os
import random
import tempfile
import threading
from datetime import datetime, timezone

HANDLE = "Demo_Pilot"

_STATIC = [
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


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class DemoLogWriter(threading.Thread):
    def __init__(self, interval: float = 5.0) -> None:
        super().__init__(name="scdash-demo", daemon=True)
        self.interval = interval
        fd, self.path = tempfile.mkstemp(prefix="scdash-demo-", suffix=".log")
        os.close(fd)
        self._halt = threading.Event()

    def _write(self, template: str) -> None:
        line = template.format(ts=_ts(), me=HANDLE, n=random.randint(100000, 9999999))
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        for t in _STATIC:
            self._write(t)
        while not self._halt.wait(self.interval):
            self._write(random.choice(_RANDOM))
