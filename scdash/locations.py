"""Turn internal Star Citizen ids (locations, shards, ships) into readable names."""

from __future__ import annotations

import re
from typing import Dict, Optional

BODIES: Dict[str, Dict[str, str]] = {
    "Stanton": {
        "1": "Hurston", "1a": "Arial", "1b": "Aberdeen", "1c": "Magda", "1d": "Ita",
        "2": "Crusader", "2a": "Cellin", "2b": "Daymar", "2c": "Yela",
        "3": "ArcCorp", "3a": "Lyria", "3b": "Wala",
        "4": "microTech", "4a": "Calliope", "4b": "Clio", "4c": "Euterpe",
    },
    "Pyro": {
        "1": "Pyro I", "2": "Monox", "3": "Bloom", "4": "Pyro IV",
        "5": "Pyro V", "5a": "Ignis", "5b": "Vatra", "5c": "Adir", "5d": "Fairo", "5e": "Fuego", "5f": "Vuur",
        "6": "Terminus",
    },
}

# Station / rest-stop abbreviations ("RR_HUR_LEO")
_ABBR = {"HUR": "Hurston", "CRU": "Crusader", "ARC": "ArcCorp", "MIC": "microTech"}

_PLACE_NAMES = {
    "Lorville": "Lorville", "Orison": "Orison", "Area18": "Area 18", "NewBabbage": "New Babbage",
    "GrimHex": "Grim HEX", "PortTressler": "Port Tressler", "Everus": "Everus Harbor",
    "Baijini": "Baijini Point", "Seraphim": "Seraphim Station",
}

_LOC = re.compile(r"^(?P<system>Stanton|Pyro|Nyx)_?(?P<body>\d+[a-z]?)?(?:_(?P<rest>.+))?$", re.I)
_OOC = re.compile(r"^OOC_(?P<system>Stanton|Pyro|Nyx)_(?P<body>\d+[a-z]?)(?:_(?P<rest>.+))?$", re.I)
_RR = re.compile(r"^RR_(?P<body>[A-Z]{3})_(?P<orbit>\w+)$")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")


# camelCase brand names that must not be split into two words
_KEEP = {"micro Tech": "microTech", "Arc Corp": "ArcCorp", "Grim HEX": "Grim HEX"}


def _split_words(s: str) -> str:
    out = _CAMEL.sub(" ", s.replace("_", " ")).strip()
    for wrong, right in _KEEP.items():
        out = out.replace(wrong, right)
    return out


def _place(rest: Optional[str]) -> Optional[str]:
    if not rest:
        return None
    parts = rest.split("_")
    key = parts[0]
    # "EMShelter_ClearView" -> "Clear View Emergency Shelter"
    if key == "EMShelter" and len(parts) > 1:
        return f"{_split_words('_'.join(parts[1:]))} Emergency Shelter"
    # "DistributionCentre_Covalex_S4DC05" -> "Covalex Distribution Centre S4DC05"
    if key in ("DistributionCentre", "DistributionCenter") and len(parts) > 1:
        code = parts[2] if len(parts) > 2 else ""
        kind = "Logistics Depot" if "LD" in code else "Distribution Centre"
        return f"{_split_words(parts[1])} {kind} {code}".strip()
    if rest in _PLACE_NAMES:
        return _PLACE_NAMES[rest]
    if key in _PLACE_NAMES:
        return _PLACE_NAMES[key]
    return _split_words(rest)


def describe_location(raw: str) -> Dict[str, Optional[str]]:
    """``Stanton2_Orison`` -> {system: Stanton, planet: Crusader, place: Orison}."""
    raw = re.sub(r"_\d{5,}$", "", raw.strip())
    m = _LOC.match(raw) or _OOC.match(raw)
    if m:
        system = m.group("system").capitalize()
        body_id = (m.group("body") or "").lower()
        bodies = BODIES.get(system, {})
        body = bodies.get(body_id)
        planet = bodies.get(body_id.rstrip("abcdefgh")) if body_id else None
        place = _place(m.group("rest")) or body or system
        return {"system": system, "planet": planet, "place": place}
    m = _RR.match(raw)
    if m:
        body = _ABBR.get(m.group("body"))
        return {"system": "Stanton", "planet": body, "place": f"R&R {m.group('body')}-{m.group('orbit')}"}
    if raw.split("_")[0].upper() in MANUFACTURERS:
        return {"system": None, "planet": None, "place": ship_name(raw)}
    return {"system": None, "planet": None, "place": _split_words(raw)}


_REGIONS = {
    "euw": "EU West", "eue": "EU East", "euc": "EU Central", "eun": "EU North",
    "use": "US East", "usw": "US West", "usc": "US Central",
    "apse": "Asien-Pazifik (SO)", "apne": "Asien-Pazifik (NO)", "aps": "Asien-Pazifik",
    "sa": "Südamerika", "au": "Australien",
}


def shard_region(shard: Optional[str]) -> Optional[str]:
    if not shard:
        return None
    m = re.match(r"^(?:pub|ptu|tech|eptu)?_?([a-z]+?)\d", shard)
    if not m:
        return None
    return _REGIONS.get(m.group(1))


MANUFACTURERS = {
    "AEGS": "Aegis", "ANVL": "Anvil", "ARGO": "Argo", "BANU": "Banu", "CNOU": "C.O.", "CRUS": "Crusader",
    "DRAK": "Drake", "ESPR": "Esperia", "GAMA": "Gatac", "GRIN": "Greycat", "KRIG": "Kruger",
    "MISC": "MISC", "MRAI": "Mirai", "ORIG": "Origin", "RSI": "RSI", "TMBL": "Tumbril",
    "VNCL": "Vanduul", "XIAN": "Aopoa", "XNAA": "Aopoa",
}


def ship_name(raw: str) -> str:
    """``DRAK_Cutlass_Black_123456`` -> ``Drake Cutlass Black``."""
    raw = re.sub(r"_\d{5,}$", "", raw.strip())
    parts = raw.split("_")
    if parts and parts[0].upper() in MANUFACTURERS:
        parts[0] = MANUFACTURERS[parts[0].upper()]
    # drop AI / PU prefixes that sometimes appear on NPC ships
    parts = [p for p in parts if p not in ("PU", "AI", "CRIM", "UEE", "CIV")]
    return " ".join(parts) or raw


WEAPON_MAKERS = {
    "behr": "Behring", "ksar": "Kastak Arms", "klwe": "Klaus & Werner", "gats": "Gallenson",
    "apar": "Apocalypse Arms", "hrst": "Hurston", "gmni": "Gemini", "lbco": "Lightning Bolt",
    "volt": "VOLT", "amrs": "Amon & Reese", "kbar": "KnightBridge", "nvy": "NorthStar",
}


def weapon_name(raw: str) -> Optional[str]:
    raw = re.sub(r"_\d{5,}$", "", (raw or "").strip())
    if not raw or raw.lower() == "unknown":
        return None
    parts = raw.split("_")
    maker = WEAPON_MAKERS.get(parts[0].lower())
    rest = [p for p in parts[1:] if not re.fullmatch(r"\d{1,2}", p)] if maker else parts
    words = " ".join(w.capitalize() if w.islower() else w for w in rest)
    return f"{maker} {words}".strip() if maker else words


# --------------------------------------------------------------------------- quantum targets
# Quantum targets in the log are internal object names. Many are technical (mission
# markers, nav points); those are classified instead of shown verbatim. Categories were
# cross-checked with the open-source tools sc-log-tracker (MIT) and all-slain.
_QT_NOISE = re.compile(r"_?\{[0-9A-Fa-f-]+\}|\.socpak$|_\d{6,}$")
_QT_CITY = re.compile(r"(?i)^(levski|grimhex|lorville|area18|orison|newbabbage)(?:_[a-z]+)?(?:-\d+)?$")
_QT_REST_STOP = re.compile(r"(?i)^LOC_RR_S([1-4])_L(\d)$")
_QT_MISSION = re.compile(r"(?i)^MISSION_QT_(.+)$")
_QT_ASTEROIDS = re.compile(r"(?i)^asteroidcluster_([a-z]+)_region([a-z])")
_QT_MISSION_HINT = re.compile(r"(?i)final|^ab_|^orbtl_|^util_|_encounter|_dungeon|^em_shelter|_cluster_|^mission")
_CITY_NAMES = {"grimhex": "Grim HEX", "newbabbage": "New Babbage", "area18": "Area 18"}


def quantum_destination(raw: str) -> Dict[str, Optional[str]]:
    """Classify a quantum target id.

    Returns ``{"name": readable name or None, "kind": place|mission|navpoint|party|asteroids|unknown}``.
    """
    name = _QT_NOISE.sub("", _QT_NOISE.sub("", (raw or "").strip()))
    low = name.lower()
    if not name:
        return {"name": None, "kind": "unknown"}
    if low.startswith("partymembermarker"):
        return {"name": "Partymitglied", "kind": "party"}
    if low.startswith("navpoint"):
        return {"name": "Markierter Navpunkt", "kind": "navpoint"}
    m = _QT_REST_STOP.match(name)
    if m:
        return {"name": f"{['HUR', 'CRU', 'ARC', 'MIC'][int(m.group(1)) - 1]}-L{m.group(2)}", "kind": "place"}
    m = _QT_MISSION.match(name)
    if m:
        return {"name": _split_words(m.group(1)), "kind": "mission"}
    m = _QT_ASTEROIDS.match(name)
    if m:
        return {"name": f"Asteroidenfeld ({m.group(1).capitalize()})", "kind": "asteroids"}
    name = re.sub(r"(?i)_LOC$", "", name)
    m = _QT_CITY.match(name)
    if m:
        key = m.group(1).lower()
        return {"name": _CITY_NAMES.get(key, m.group(1).capitalize()), "kind": "place"}
    if _QT_MISSION_HINT.search(name):
        return {"name": None, "kind": "mission"}
    if name[0].isupper() and not re.search(r"(^|_)\d+(_|$)", name):
        return {"name": describe_location(name)["place"], "kind": "place"}
    return {"name": None, "kind": "unknown"}


_OBJECTIVE_PLACE = re.compile(r"(?i)\b(?:from|to|at|near|in)\s+(?P<place>[A-Z][^:]*?)(?:\s+(?:on|above|in orbit of)\s+[\w ]+)?\s*$")


def objective_place(text: str) -> Optional[str]:
    """``Collect X From Clear View Emergency Shelter on microTech`` -> ``Clear View Emergency Shelter``."""
    m = _OBJECTIVE_PLACE.search(text or "")
    return m.group("place").strip() if m else None
