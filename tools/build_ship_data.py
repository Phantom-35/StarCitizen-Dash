#!/usr/bin/env python3
"""Build ``scdash/data/ships.json`` from several public sources and cross-check them.

SC-Dash shows two numbers per ship that are *not* in the Game.log: cargo capacity and the
size of the quantum fuel tank. Wrong numbers would be worse than none, so every value is
taken from the game files and only kept when independent sources agree.

Sources
  scunpacked   StarCitizenWiki/scunpacked-data ``ships.json`` - extracted game files (primary)
  wiki         api.star-citizen.wiki - game files, carries the game version it was built from
  fleetyards   api.fleetyards.net - separate site, keyed by the game's class name
  uex          api.uexcorp.space - community database (often incomplete: 0 = not filled in)
  rsi          robertsspaceindustries.com ship matrix - official marketing figures (cargo only;
               known to differ from the game, used for the report only)

Rules
  * A value is taken over when at least two sources agree (within 2 %).
  * scunpacked and wiki share a toolchain. A value counts as *independently confirmed* only
    if fleetyards or uex agrees as well; otherwise it is kept but flagged ("confirmed": false)
    and SC-Dash shows it as approximate.
  * Contradictions are not papered over: a value is dropped when fewer than three sources
    back it and another source disagrees, or when the majority says 0 while a source reports
    more (modular ships such as the Retaliator).

Usage:  python tools/build_ship_data.py [--cache DIR]
The result is committed to the repository - SC-Dash itself never goes online for it.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "scdash", "data", "ships.json")
REPORT = os.path.join(ROOT, "docs", "ship-data-report.md")
UA = {"User-Agent": "SC-Dash ship data builder"}

URLS = {
    "scunpacked": "https://raw.githubusercontent.com/StarCitizenWiki/scunpacked-data/master/ships.json",
    "uex": "https://api.uexcorp.space/2.0/vehicles",
    "rsi": "https://robertsspaceindustries.com/ship-matrix/index",
}
WIKI = "https://api.star-citizen.wiki/api/v2/vehicles?locale=en_EN&page%5Bsize%5D=50&page%5Bnumber%5D={page}"
FLEETYARDS = "https://api.fleetyards.net/v1/models?perPage=240&page={page}"


def fetch(url: str, cache: str | None, name: str):
    path = os.path.join(cache, name) if cache else None
    if path and os.path.exists(path):
        with open(path, "rb") as fh:
            return json.load(fh)
    print(f"  fetching {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    if path:
        with open(path, "wb") as fh:
            fh.write(raw)
    return json.loads(raw)


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def agree(a, b, tol=0.02):
    """Equal within 2 % (sources round differently)."""
    if a is None or b is None:
        return False
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-9) or abs(a - b) < 0.0051


def load_sources(cache):
    src = {}

    ships = fetch(URLS["scunpacked"], cache, "scunpacked.json")
    src["scunpacked"] = {
        s["ClassName"].lower(): {
            "class": s["ClassName"],
            "name": s.get("Name"),
            "uuid": s.get("UUID"),
            "cargo": num(s.get("Cargo")),
            # game files count in 1/1000 SCU
            "qt_fuel": (num((s.get("QuantumTravel") or {}).get("FuelCapacity")) or 0) / 1000 or None,
            "qt_range": num((s.get("QuantumTravel") or {}).get("Range")),
            "is_ship": bool(s.get("IsSpaceship")),
        }
        for s in ships
        if s.get("ClassName")
    }

    wiki, page, version = {}, 1, None
    while True:
        d = fetch(WIKI.format(page=page), cache, f"wiki_{page}.json")
        for v in d["data"]:
            if not v.get("class_name"):
                continue
            q = v.get("quantum") or {}
            wiki[v["class_name"].lower()] = {
                "class": v["class_name"],
                "name": v.get("name"),
                "game_name": v.get("game_name"),
                "uuid": v.get("uuid"),
                "cargo": num(v.get("cargo_capacity")),
                "qt_fuel": num(q.get("quantum_fuel_capacity")) or None,
                "qt_range": num(q.get("quantum_range")),
            }
            version = version or v.get("version")
        if page >= d["meta"]["last_page"]:
            break
        page += 1
    src["wiki"] = wiki

    fy, page = {}, 1
    while True:
        d = fetch(FLEETYARDS.format(page=page), cache, f"fleetyards_{page}.json")
        for m in d["items"]:
            if not m.get("scIdentifier"):
                continue
            me = m.get("metrics") or {}
            fy[m["scIdentifier"].lower()] = {
                "name": m.get("name"),
                "cargo": num(me.get("cargo")),
                "qt_fuel": num(me.get("quantumFuelTankSize")) or None,
            }
        if page >= d["meta"]["pagination"]["totalPages"]:
            break
        page += 1
    src["fleetyards"] = fy

    uex_by_uuid = {}
    for v in fetch(URLS["uex"], cache, "uex.json")["data"]:
        if v.get("uuid"):
            uex_by_uuid[v["uuid"]] = {
                "name": v.get("name_full"),
                # UEX uses 0 for "not filled in"
                "cargo": num(v.get("scu")) or None,
                "qt_fuel": num(v.get("fuel_quantum")) or None,
            }
    src["uex_by_uuid"] = uex_by_uuid

    src["rsi_by_name"] = {
        r["name"].lower(): {"cargo": num(r.get("cargocapacity"))}
        for r in fetch(URLS["rsi"], cache, "rsi.json")["data"]
    }
    return src, version


INDEPENDENT = ("fleetyards", "uex")  # not derived from the scunpacked/wiki toolchain


def consensus(values: dict):
    """values: source -> number|None. Returns (value, [agreeing sources])."""
    present = {k: v for k, v in values.items() if v is not None}
    best, backers = None, []
    for k, v in present.items():
        group = [k2 for k2, v2 in present.items() if agree(v, v2)]
        if len(group) > len(backers):
            best, backers = v, group
    return best, backers


def build(src, version):
    ships, report = {}, {"qt_conflicts": [], "cargo_conflicts": [], "rsi_differs": [], "single": []}
    for key, base in sorted(src["scunpacked"].items()):
        w = src["wiki"].get(key, {})
        f = src["fleetyards"].get(key, {})
        u = src["uex_by_uuid"].get(base.get("uuid") or w.get("uuid") or "", {})
        name = w.get("game_name") or base.get("name") or w.get("name") or base["class"]
        rsi = src["rsi_by_name"].get((w.get("name") or base.get("name") or "").lower(), {})

        entry = {"class": base["class"], "name": name}
        aliases = {n for n in (w.get("game_name"), w.get("name"), base.get("name"), f.get("name"), u.get("name")) if n}
        entry["aliases"] = sorted(aliases - {name})

        for field, label in (("cargo", "cargo_conflicts"), ("qt_fuel", "qt_conflicts")):
            vals = {"scunpacked": base.get(field), "wiki": w.get(field), "fleetyards": f.get(field), "uex": u.get(field)}
            value, backers = consensus(vals)
            present = {k: v for k, v in vals.items() if v is not None}
            if field == "cargo" and not present:
                continue
            if value is None:
                continue
            dissent = {k: v for k, v in present.items() if k not in backers}
            if len(backers) < 2:
                report["single"].append((name, field, present))
                continue
            dropped = bool(dissent) and (len(backers) < 3 or (value == 0 and any(v > 0 for v in dissent.values())))
            if dissent:
                report[label].append((name, round(value, 3), backers, dissent, dropped))
            if dropped:
                continue
            entry[field] = round(value, 3)
            entry[field + "_sources"] = backers
            entry[field + "_confirmed"] = any(b in INDEPENDENT for b in backers)
        if "qt_fuel" in entry and agree(base.get("qt_range"), w.get("qt_range")) and base.get("qt_range"):
            entry["qt_range"] = round(base["qt_range"])  # metres, with the stock quantum drive
        if "cargo" in entry and rsi.get("cargo") is not None and not agree(rsi["cargo"], entry["cargo"]):
            report["rsi_differs"].append((name, entry["cargo"], rsi["cargo"]))
        if "cargo" in entry or "qt_fuel" in entry:
            ships[key] = entry
    return ships, report


def write_report(ships, report, version, counts):
    today = datetime.date.today().isoformat()
    lines = [
        "# Schiffsdaten – Abgleich der Quellen",
        "",
        f"Erzeugt am {today} mit `tools/build_ship_data.py`. Spielversion laut Wiki-API: **{version}**.",
        "",
        "SC-Dash zeigt Frachtraum und Quantum-Tank nur für Schiffe, bei denen **mindestens zwei Quellen",
        "übereinstimmen** und kein ungeklärter Widerspruch besteht. Die offizielle RSI-Schiffsliste dient nur zum Vergleich: Sie enthält",
        "Marketing-Angaben, die oft von den Werten im Spiel abweichen.",
        "",
        "| | Anzahl |",
        "|---|---:|",
    ]
    for k, v in counts.items():
        lines.append(f"| {k} | {v} |")
    lines += [
        f"| Quantum-Tank unabhängig bestätigt | {sum(1 for s in ships.values() if s.get('qt_fuel_confirmed'))} |",
        f"| Frachtraum unabhängig bestätigt | {sum(1 for s in ships.values() if s.get('cargo_confirmed'))} |",
        "",
        "„Unabhängig bestätigt“ heißt: FleetYards oder UEX nennt denselben Wert wie die Spieldateien.",
        "Werte, die nur die Spieldateien und die darauf aufbauende Wiki-API nennen, zeigt SC-Dash als",
        "ungefähr („ca.“) an.",
        "",
        "## Widersprüche beim Quantum-Tank",
        "",
        "Mehrheit gewinnt; abweichende Quelle in Klammern." if report["qt_conflicts"] else "Keine.",
        "",
    ]
    for name, value, backers, dissent, dropped in report["qt_conflicts"]:
        lines.append(f"- **{name}**: {value} SCU ({', '.join(backers)}) – abweichend: {dissent}"
                     + (" → **nicht übernommen**" if dropped else ""))
    lines += ["", "## Widersprüche beim Frachtraum", "", "Keine." if not report["cargo_conflicts"] else ""]
    for name, value, backers, dissent, dropped in report["cargo_conflicts"]:
        lines.append(f"- **{name}**: {value} SCU ({', '.join(backers)}) – abweichend: {dissent}"
                     + (" → **nicht übernommen**" if dropped else ""))
    lines += ["", "## Nur eine Quelle (nicht übernommen)", ""]
    for name, field, present in report["single"]:
        lines.append(f"- {name}: {field} = {present}")
    lines += ["", f"## RSI-Schiffsliste weicht ab ({len(report['rsi_differs'])} Schiffe)", "",
              "| Schiff | Im Spiel (SCU) | RSI-Liste (SCU) |", "|---|---:|---:|"]
    for name, ours, theirs in report["rsi_differs"]:
        lines.append(f"| {name} | {ours:g} | {theirs:g} |")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache", help="directory to keep the downloaded files (speeds up re-runs)")
    args = ap.parse_args()
    if args.cache:
        os.makedirs(args.cache, exist_ok=True)

    src, version = load_sources(args.cache)
    ships, report = build(src, version)
    counts = {
        "Fahrzeuge in den Spieldateien": len(src["scunpacked"]),
        "davon in der Wiki-API": sum(1 for k in src["scunpacked"] if k in src["wiki"]),
        "davon bei FleetYards": sum(1 for k in src["scunpacked"] if k in src["fleetyards"]),
        "übernommen (mind. ein bestätigter Wert)": len(ships),
        "mit bestätigtem Quantum-Tank": sum(1 for s in ships.values() if "qt_fuel" in s),
        "mit bestätigtem Frachtraum": sum(1 for s in ships.values() if "cargo" in s),
    }
    data = {
        "meta": {
            "generated": datetime.date.today().isoformat(),
            "game_version": version,
            "units": {"cargo": "SCU", "qt_fuel": "SCU", "qt_range": "m (stock quantum drive)"},
            "rule": "a value is included only if at least two sources agree",
            "sources": ["scunpacked-data (game files)", "api.star-citizen.wiki", "api.fleetyards.net", "api.uexcorp.space"],
        },
        "ships": ships,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    write_report(ships, report, version, counts)
    for k, v in counts.items():
        print(f"{v:5d}  {k}")
    print(f"conflicts: qt {len(report['qt_conflicts'])}, cargo {len(report['cargo_conflicts'])}, "
          f"single-source {len(report['single'])}, rsi differs {len(report['rsi_differs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
