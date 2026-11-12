"""Remembers where the dashboard window was, so it opens on the second monitor again.

The page reports its position and size (``window.screenX`` etc., in the same screen coordinates
Chromium's ``--window-position`` uses) to the local server, which stores them in
``<data_dir>/window.json``. On the next start the window is opened there - unless that spot is no
longer on any screen (monitor unplugged), then the browser decides.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

DEFAULT_SIZE = (1600, 900)
MIN_W, MIN_H = 400, 300
MAX_DIM = 20000


def clean(data: Any) -> Optional[Dict[str, int]]:
    """Validated placement {x, y, w, h} or None."""
    if not isinstance(data, dict):
        return None
    try:
        x, y, w, h = (int(round(float(data[k]))) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not (MIN_W <= w <= MAX_DIM and MIN_H <= h <= MAX_DIM and abs(x) <= MAX_DIM and abs(y) <= MAX_DIM):
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def load(path: str) -> Optional[Dict[str, int]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return clean(json.load(fh))
    except (OSError, ValueError):
        return None


def save(path: str, placement: Dict[str, int]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(placement, fh)
        os.replace(tmp, path)
    except OSError as exc:
        log.debug("Fensterposition nicht speicherbar: %s", exc)


def _virtual_screen() -> Optional[List[int]]:
    """Bounding box of all monitors on Windows (left, top, right, bottom), else None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        u = ctypes.windll.user32
        # 76/77 = SM_X/YVIRTUALSCREEN, 78/79 = SM_CX/CYVIRTUALSCREEN
        left, top, w, h = (u.GetSystemMetrics(i) for i in (76, 77, 78, 79))
        if w <= 0 or h <= 0:
            return None
        return [left, top, left + w, top + h]
    except Exception:
        return None


def window_args(placement: Optional[Dict[str, int]], screen: Optional[List[int]] = None) -> List[str]:
    """Browser arguments for the saved placement; falls back to the default size."""
    if screen is None:
        screen = _virtual_screen()
    if placement:
        cx = placement["x"] + placement["w"] // 2
        cy = placement["y"] + 40  # the title bar must be reachable
        visible = screen is None or (screen[0] <= cx < screen[2] and screen[1] <= cy < screen[3])
        if visible:
            return [f"--window-position={placement['x']},{placement['y']}",
                    f"--window-size={placement['w']},{placement['h']}"]
        log.info("Gespeicherte Fensterposition liegt außerhalb der Bildschirme – Standardposition")
    return [f"--window-size={DEFAULT_SIZE[0]},{DEFAULT_SIZE[1]}"]
