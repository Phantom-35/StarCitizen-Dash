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

_RANDOM = [
    "<{ts}> [Notice] <Actor Death> CActor::Kill: 'PU_Human_Enemy_GroundCombat_NPC_Pirate_Soldier_{n}' [{n}] in zone 'OOC_Stanton_2b_Daymar' killed by '{me}' [1] using 'behr_rifle_ballistic_01_{n}' [Class behr_rifle_ballistic_01] with damage type 'Bullet' from direction x: 0, y: 0, z: 0 [Team_ActorTech][Actor]",
    "<{ts}> [Notice] <Actor Death> CActor::Kill: 'Some_Rival' [{n}] in zone 'ANVL_Arrow_{n}' killed by '{me}' [1] using 'KLWE_LaserRepeater_S3_{n}' [Class KLWE_LaserRepeater_S3] with damage type 'Energy' from direction x: 0, y: 0, z: 0 [Team_ActorTech][Actor]",
    "<{ts}> [Notice] <Actor Death> CActor::Kill: '{me}' [1] in zone 'OOC_Stanton_2b_Daymar' killed by 'Outlaw_Joe' [{n}] using 'ksar_sniper_ballistic_01_{n}' [Class ksar_sniper_ballistic_01] with damage type 'Bullet' from direction x: 0, y: 0, z: 0 [Team_ActorTech][Actor]",
    "<{ts}> [Notice] <Vehicle Destruction> CVehicle::OnAdvanceDestroyLevel: Vehicle 'DRAK_Cutlass_Black_{n}' [{n}] in zone 'OOC_Stanton_2b_Daymar' [pos x: 0, y: 0, z: 0 vel x: 0, y: 0, z: 0] driven by 'Some_Rival' [{n}] advanced from destroy level 0 to 2 caused by '{me}' [1] with 'Combat' [Team_VehicleFeatures][Vehicle]",
    "<{ts}> [Notice] <RequestLocationInventory> Player[{me}] requested inventory for Location[Stanton2_Orison] [Team_CoreGameplayFeatures][Inventory]",
]


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class DemoLogWriter(threading.Thread):
    def __init__(self, interval: float = 6.0) -> None:
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
