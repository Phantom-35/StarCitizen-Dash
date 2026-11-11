"""Static ship data (cargo capacity, quantum fuel tank) and the maths built on it.

The numbers come from ``scdash/data/ships.json``, which ``tools/build_ship_data.py`` builds
from the game files and cross-checks against other sources (see docs/ship-data-report.md).

Quantum fuel units - verified against a real 4.10 log
-----------------------------------------------------
The log line ``... Successfully calculated route to X fuel estimate 18.180450`` gives the
game's fuel estimate for the plotted route. Its unit is **1/1,000,000 SCU**:

* Tank sizes in the game files are in 1/1000 SCU (Aurora Mk II: 900 = 0.9 SCU), range with
  the stock drive 98.75 Gm -> 9.114e-9 SCU per km.
* In the real log two jumps on microTech (radius 1000 km) between known mission markers were
  estimated at 18.18 and 17.70. Read as 1e-6 SCU this is 1,995 km and 1,942 km - right between
  the straight-line distance (1,750 / 1,783 km) and the way over the surface (2,131 / 2,202 km).
  Read as 1e-3 SCU it would be two million km on a planet 2,000 km wide.
* Cross-check: the wiki lists 382 tank units for Port Olisar -> ArcCorp (~42 Gm), which is
  9.1 units per Gm - the same rate.

The share of the tank a route needs does not depend on the installed quantum drive: the game
has already put the drive's consumption into its estimate.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ships.json")

#: one unit of the log's "fuel estimate" in SCU
ESTIMATE_UNIT_SCU = 1e-6

_db: Optional[Dict[str, Any]] = None
_by_name: Dict[str, str] = {}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _load() -> Dict[str, Any]:
    global _db
    if _db is None:
        try:
            with open(DATA_FILE, encoding="utf-8") as fh:
                _db = json.load(fh)
        except (OSError, ValueError):
            _db = {"meta": {}, "ships": {}}
        for key, ship in _db["ships"].items():
            for name in [ship["name"], ship["class"]] + ship.get("aliases", []):
                _by_name.setdefault(_norm(name), key)
    return _db


def meta() -> Dict[str, Any]:
    return _load().get("meta", {})


def lookup(class_name: Optional[str] = None, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find a ship by the game's class name (``RSI_Aurora_Mk2``) or by its display name."""
    ships = _load()["ships"]
    if class_name:
        key = re.sub(r"_\d{6,}$", "", class_name).lower()
        if key in ships:
            return ships[key]
    for candidate in (name, class_name):
        if candidate:
            key = _by_name.get(_norm(candidate))
            if key:
                return ships[key]
    return None


def tank_share(estimate: Optional[float], ship: Optional[Dict[str, Any]]) -> Optional[float]:
    """Share of the quantum tank (in percent) that ``estimate`` log units represent."""
    if not estimate or not ship or not ship.get("qt_fuel"):
        return None
    return 100.0 * estimate * ESTIMATE_UNIT_SCU / ship["qt_fuel"]


def public_info(ship: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """What the dashboard needs to know about the current ship."""
    if not ship:
        return None
    return {
        "name": ship["name"],
        "cargo": ship.get("cargo"),
        "cargo_confirmed": bool(ship.get("cargo_confirmed")),
        "qt_fuel": ship.get("qt_fuel"),
        "qt_fuel_confirmed": bool(ship.get("qt_fuel_confirmed")),
    }
