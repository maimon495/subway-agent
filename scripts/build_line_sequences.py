#!/usr/bin/env python3
"""Rebuild the subway line sequences from GTFS.

The adjacency graph was built from a hand-maintained {line: [station, ...]}
dict, and it had drifted: the 1 was recorded as running South Ferry -> Wall St
-> Fulton St, neither of which the 1 serves. Routing therefore offered a
transfer to the 2/3 at Wall St, which is not a transfer a person can make.

GTFS already holds the true stop order for every route in stop_times.txt. This
derives the sequences from it, the same way the station ids were repaired,
so the graph stops being something anyone has to remember to update.

    python scripts/build_line_sequences.py
"""

from __future__ import annotations

import csv
import io
import json
import pathlib
import re
import zipfile
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
GTFS_ZIP = ROOT / "data" / "gtfs_subway.zip"
COMPLEX_IDS = ROOT / "data" / "station_gtfs_ids.json"
OUT = ROOT / "data" / "line_sequences.json"

# GTFS names the shuttles GS and FS; the station table calls both S.
ROUTE_ALIASES = {"GS": "S", "FS": "S"}


def main() -> None:
    archive = zipfile.ZipFile(GTFS_ZIP)

    def read(name: str) -> list[dict]:
        with archive.open(name) as handle:
            return list(csv.DictReader(io.TextIOWrapper(handle, "utf-8-sig")))

    # GTFS stop id -> our station key. A complex maps several ids to one key,
    # which is what lets a route through Times Sq land on the station a rider
    # would name.
    gtfs_to_key: dict[str, str] = {}
    for key, ids in json.loads(COMPLEX_IDS.read_text()).items():
        for stop_id in ids:
            gtfs_to_key.setdefault(stop_id, key)

    trips = {r["trip_id"]: r for r in read("trips.txt")}

    by_trip: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for row in read("stop_times.txt"):
        stop_id = re.sub(r"[NS]$", "", row["stop_id"])
        by_trip[row["trip_id"]].append((int(row["stop_sequence"]), stop_id))

    # The longest trip on a route covers its trunk; shorter ones are branches
    # and short turns. Express variants (route ids ending X) fold into the
    # parent line, since a rider says "the 6" either way.
    longest: dict[str, list[str]] = {}
    for trip_id, stops in by_trip.items():
        trip = trips.get(trip_id)
        if not trip:
            continue
        route = trip["route_id"]
        route = ROUTE_ALIASES.get(route, route.rstrip("X") if route.endswith("X") else route)
        ordered = [s for _, s in sorted(stops)]
        if len(ordered) > len(longest.get(route, [])):
            longest[route] = ordered

    sequences: dict[str, list[str]] = {}
    for line, stops in sorted(longest.items()):
        keys: list[str] = []
        for stop_id in stops:
            key = gtfs_to_key.get(stop_id)
            # Stations we do not model are skipped; consecutive modelled stops
            # stay in order, so adjacency remains correct if coarser.
            if key and (not keys or keys[-1] != key):
                keys.append(key)
        if len(keys) >= 2:
            sequences[line] = keys

    OUT.write_text(json.dumps(sequences, indent=1, sort_keys=True))
    print(f"wrote {OUT}")
    print(f"lines: {len(sequences)}")
    for line in sorted(sequences):
        print(f"  {line:<3} {len(sequences[line]):>3} modelled stops")


if __name__ == "__main__":
    main()
