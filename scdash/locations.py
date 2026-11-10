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


def _split_words(s: str) -> str:
    return _CAMEL.sub(" ", s.replace("_", " ")).strip()


def _place(rest: Optional[str]) -> Optional[str]:
    if not rest:
        return None
    key = rest.split("_")[0]
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
