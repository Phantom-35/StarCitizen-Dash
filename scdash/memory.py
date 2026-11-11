"""Place memory: which named place a mission marker position belongs to.

Mission objectives often name only a room ("Deliver Hydrogen To Lobby"), but the game logs
the marker's coordinates when the contract is accepted (``CLocalMissionPhaseMarker::
CreateMarker ... position [x: .., y: .., z: ..]``, planet-fixed, in metres). When an
objective is completed, the player is standing at that place - and SC-Dash knows its name
from the inventory request. Remembering "these coordinates = this place" lets the next
contract to the same spot show the real place.

Verified with two real 4.10 sessions: the "Security Compound" drop-off of the first and the
"Lobby" drop-off of the second lie 3.6 km apart on microTech, and both were delivered at
Covalex Distribution Centre S4DC05.

Coordinates are planet-local; two different planets would have to have markers within
``MATCH_RADIUS`` of the same local coordinates to be confused, which is very unlikely on
bodies of ~300-7,500 km radius.
"""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import threading
from typing import Dict, List, Optional, Sequence

log = logging.getLogger(__name__)

MATCH_RADIUS = 10_000.0    # metres: markers of one building are well within this
MERGE_RADIUS = 1_000.0     # metres: closer than this to a known point -> same entry
MIN_PLANET_FRAME = 50_000.0  # markers placed later inside a building use small local coordinates
MAX_ENTRIES = 2000

Pos = Sequence[float]


def is_planet_frame(pos: Pos) -> bool:
    return math.dist(pos, (0.0, 0.0, 0.0)) >= MIN_PLANET_FRAME


class PlaceMemory:
    def __init__(self, path: Optional[str]) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._entries: List[Dict] = []
        if path:
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                self._entries = [e for e in data.get("places", []) if len(e.get("pos", [])) == 3 and e.get("place")]
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as exc:
                log.warning("Ortsgedächtnis nicht lesbar (%s) – starte leer", exc)

    def __len__(self) -> int:
        return len(self._entries)

    def lookup(self, pos: Optional[Pos]) -> Optional[Dict[str, Optional[str]]]:
        if not pos or not is_planet_frame(pos):
            return None
        with self._lock:
            best = min(self._entries, key=lambda e: math.dist(e["pos"], pos), default=None)
        if best and math.dist(best["pos"], pos) <= MATCH_RADIUS:
            return {"system": best.get("system"), "planet": best.get("planet"), "place": best["place"]}
        return None

    def learn(self, pos: Optional[Pos], location: Optional[Dict[str, Optional[str]]], when: Optional[str]) -> bool:
        if not pos or not location or not location.get("place") or not is_planet_frame(pos):
            return False
        entry = {"pos": [round(c, 1) for c in pos], "place": location["place"], "planet": location.get("planet"),
                 "system": location.get("system"), "seen": when}
        with self._lock:
            near = [e for e in self._entries if math.dist(e["pos"], pos) <= MERGE_RADIUS]
            if near and near[0]["place"] == entry["place"]:
                near[0]["seen"] = when
            else:
                for e in near:
                    self._entries.remove(e)   # the place there has a new name (or was wrong)
                self._entries.append(entry)
                del self._entries[:-MAX_ENTRIES]
            self._save()
        return True

    def _save(self) -> None:
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "places": self._entries}, fh, ensure_ascii=False, indent=0)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("Ortsgedächtnis nicht speicherbar: %s", exc)
