#!/usr/bin/env python3
"""Repair the GTFS stop ids in stations.py against the official GTFS feed.

The hand-maintained ids had drifted badly — "Chambers St" pointed at stop 130,
which is 23 St — and because a wrong id still returns arrivals, the agent
answered confidently with another station's trains. Silent and wrong is worse
than an error.

The coordinates in the table are accurate, so each station is re-resolved to
the nearest GTFS parent stop that actually serves its lines. Names are matched
only as a tie-break, because the table and the feed spell stations differently
("West 4th St-Washington Sq" vs "W 4 St-Wash Sq").

    python scripts/fix_station_gtfs_ids.py --check    # report, change nothing
    python scripts/fix_station_gtfs_ids.py --write
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import pathlib
import re
import zipfile
from difflib import SequenceMatcher

ROOT = pathlib.Path(__file__).resolve().parent.parent
GTFS_ZIP = ROOT / "data" / "gtfs_subway.zip"
STATIONS_PY = ROOT / "src" / "subway_agent" / "stations.py"

ROW_RE = re.compile(
    r'\(\s*"(?P<key>[^"]+)",\s*"(?P<name>[^"]+)",\s*'
    r'\[(?P<lines>[^\]]*)\],\s*"(?P<gtfs>[^"]+)",\s*'
    r'(?P<lat>-?\d+\.\d+),\s*(?P<lon>-?\d+\.\d+),\s*"(?P<borough>[^"]+)"\s*\)'
)


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def load_gtfs():
    archive = zipfile.ZipFile(GTFS_ZIP)

    def read(name):
        return list(csv.DictReader(io.TextIOWrapper(archive.open(name), "utf-8-sig")))

    stops = read("stops.txt")
    parents = {
        r["stop_id"]: r
        for r in stops
        if r.get("location_type") == "1" or not r.get("parent_station")
    }

    trips = {r["trip_id"]: r["route_id"] for r in read("trips.txt")}
    routes_by_stop: dict[str, set[str]] = {}
    for row in read("stop_times.txt"):
        route = trips.get(row["trip_id"])
        if not route:
            continue
        # Platform ids carry an N/S suffix; roll them up to the parent station.
        stop_id = re.sub(r"[NS]$", "", row["stop_id"])
        routes_by_stop.setdefault(stop_id, set()).add(route)
    return parents, routes_by_stop


def name_key(text: str) -> set[str]:
    text = text.lower()
    text = re.sub(r"\b(street|st)\b", "st", text)
    text = re.sub(r"\b(avenue|ave|av)\b", "av", text)
    text = re.sub(r"\b(square|sq)\b", "sq", text)
    text = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", text)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return {w for w in text.split() if w not in {"st", "av", "the", "of"}}


def best_by_name(name, parents, routes_by_stop, wanted=None):
    """Strongest name match, optionally restricted to stops serving `wanted`."""
    target = name_key(name)
    scored = []
    for stop_id, stop in parents.items():
        served = routes_by_stop.get(stop_id, set())
        if wanted and not (wanted & served):
            continue
        other = name_key(stop["stop_name"])
        overlap = len(target & other) / max(len(target), 1)
        # Token overlap alone misses near-spellings: GTFS writes "Beverly Rd"
        # where the table writes "Beverley Rd", which scored low enough to fall
        # through to a same-named station on a different line. Blend in a
        # character-level ratio so spelling drift does not change the station.
        ratio = SequenceMatcher(None, " ".join(sorted(target)), " ".join(sorted(other))).ratio()
        score = max(overlap, ratio)
        if score:
            scored.append((score, stop_id, stop))
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], -len(t[2]["stop_name"])), reverse=True)
    score, stop_id, stop = scored[0]
    return (stop_id, stop, score) if score >= 0.75 else None


def resolve(name, lines, lat, lon, parents, routes_by_stop):
    """Nearest GTFS parent stop serving these lines. Returns (id, distance)."""
    wanted = {l.strip().strip('"') for l in lines if l.strip()}
    candidates = []
    for stop_id, stop in parents.items():
        try:
            slat, slon = float(stop["stop_lat"]), float(stop["stop_lon"])
        except (KeyError, ValueError):
            continue
        served = routes_by_stop.get(stop_id, set())
        if wanted and not (wanted & served):
            continue
        distance = haversine_m(lat, lon, slat, slon)
        overlap = len(wanted & served)
        candidates.append((distance, -overlap, stop_id, stop["stop_name"], slat, slon))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--complex-map", action="store_true",
                        help="write data/station_gtfs_ids.json for multi-stop complexes")
    args = parser.parse_args()

    if args.complex_map:
        import json
        mapping = build_complex_map()
        out = ROOT / "data" / "station_gtfs_ids.json"
        out.write_text(json.dumps(mapping, indent=1, sort_keys=True))
        multi = {k: v for k, v in mapping.items() if len(v) > 1}
        print(f"wrote {out}  ({len(mapping)} stations, {len(multi)} span several GTFS stops)")
        for k, v in sorted(multi.items())[:10]:
            print(f"   {k:<22} {v}")
        return

    parents, routes_by_stop = load_gtfs()
    source = STATIONS_PY.read_text()

    changed = unchanged = unresolved = far = 0
    report = []

    def replace(match: re.Match) -> str:
        nonlocal changed, unchanged, unresolved, far
        key = match.group("key")
        name = match.group("name")
        lines = match.group("lines").split(",")
        old_id = match.group("gtfs")
        lat, lon = float(match.group("lat")), float(match.group("lon"))

        best = resolve(name, lines, lat, lon, parents, routes_by_stop)
        if best is None:
            unresolved += 1
            report.append(("UNRESOLVED", key, name, old_id, "-", 0))
            return match.group(0)

        distance, _, new_id, gtfs_name, _, _ = best
        if distance > 400:
            # The nearest line-serving stop is implausibly far, which means the
            # row's own coordinates are wrong rather than its id. Fall back to
            # the name, and correct the coordinates too.
            wanted = {l.strip().strip('"') for l in lines if l.strip()}
            found = best_by_name(name, parents, routes_by_stop, wanted)
            note = "RELOCATED"
            if not found:
                # No stop of that name serves the claimed lines, so the LINES
                # are wrong as well (163 St-Amsterdam Av is A/C, not 1).
                found = best_by_name(name, parents, routes_by_stop)
                note = "LINES-ALSO-WRONG"
            if not found:
                far += 1
                report.append(("FAR", key, name, old_id, f"{new_id} ({gtfs_name})", distance))
                return match.group(0)
            stop_id, stop, _ = found
            served = sorted(routes_by_stop.get(stop_id, set()))
            report.append((note, key, name, old_id, f"{stop_id} ({stop['stop_name']}) lines={served}", distance))
            changed += 1
            text = match.group(0).replace(f'"{old_id}"', f'"{stop_id}"', 1)
            text = text.replace(match.group("lat"), f"{float(stop['stop_lat']):.4f}", 1)
            text = text.replace(match.group("lon"), f"{float(stop['stop_lon']):.4f}", 1)
            return text
        if new_id == old_id:
            unchanged += 1
            return match.group(0)

        changed += 1
        report.append(("FIXED", key, name, old_id, f"{new_id} ({gtfs_name})", distance))
        return match.group(0).replace(f'"{old_id}"', f'"{new_id}"', 1)

    updated = ROW_RE.sub(replace, source)

    for kind, key, name, old, new, dist in report:
        if kind == "FIXED":
            print(f"  FIXED      {name:<34} {old:<5} -> {new}  ({dist:.0f} m)")
    for kind, key, name, old, new, dist in report:
        if kind != "FIXED":
            print(f"  {kind:<10} {name:<34} {old:<5} nearest {new} ({dist:.0f} m)")

    print(f"\nfixed {changed}   already correct {unchanged}   too far to trust {far}   unresolved {unresolved}")

    if args.write:
        STATIONS_PY.write_text(updated)
        print(f"\nwrote {STATIONS_PY}")
    else:
        print("\n(dry run — pass --write to apply)")



def build_complex_map() -> dict[str, list[str]]:
    """Map each station to every GTFS stop id in its complex.

    A station like Times Sq is one row here but several parent stations in
    GTFS — one per line group. A single id therefore answers for only part of
    the complex: keyed to the 7's stop, Times Sq reports no N, Q, R or W at
    all. Collect every nearby stop serving any of the station's lines.
    """
    parents, routes_by_stop = load_gtfs()
    source = STATIONS_PY.read_text()
    mapping: dict[str, list[str]] = {}

    for match in ROW_RE.finditer(source):
        key = match.group("key")
        wanted = {l.strip().strip('"') for l in match.group("lines").split(",") if l.strip()}
        # GTFS calls the 42 St Shuttle "GS" and the Franklin Av Shuttle "FS",
        # while the table calls both "S"; without this the shuttle platforms at
        # Times Sq and Grand Central are left out of the complex.
        if "S" in wanted:
            wanted |= {"GS", "FS"}
        lat, lon = float(match.group("lat")), float(match.group("lon"))
        primary = match.group("gtfs")

        ids = {primary}
        for stop_id, stop in parents.items():
            try:
                slat, slon = float(stop["stop_lat"]), float(stop["stop_lon"])
            except (KeyError, ValueError):
                continue
            if haversine_m(lat, lon, slat, slon) > 250:
                continue
            if wanted & routes_by_stop.get(stop_id, set()):
                ids.add(stop_id)
        # Primary first so existing behaviour is unchanged where it was right.
        mapping[key] = [primary] + sorted(ids - {primary})
    return mapping

if __name__ == "__main__":
    main()
