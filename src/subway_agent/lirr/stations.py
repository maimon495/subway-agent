"""LIRR station names to stop ids.

Names arrive from people, not from the feed: "Penn", "penn station", "GCT",
"Ronkonkoma". The GTFS names are canonical but not what anyone says, so
matching is deliberately forgiving.
"""

from __future__ import annotations

import csv
import functools
import pathlib
import re
from typing import Optional

DATA = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "data"

# What people actually say, mapped to the GTFS name.
ALIASES = {
    "penn": "Penn Station",
    "penn station": "Penn Station",
    "nyp": "Penn Station",
    "new york": "Penn Station",
    "moynihan": "Penn Station",
    "gct": "Grand Central",
    "grand central terminal": "Grand Central",
    "grand central madison": "Grand Central",
    "atlantic": "Atlantic Terminal",
    "brooklyn": "Atlantic Terminal",
    "atlantic ave": "Atlantic Terminal",
}


@functools.lru_cache(maxsize=1)
def _stations() -> dict[str, str]:
    path = DATA / "lirr_stations.csv"
    with path.open() as handle:
        return {row["stop_id"]: row["stop_name"] for row in csv.DictReader(handle)}


def station_name(stop_id: str) -> str:
    return _stations().get(stop_id, f"stop {stop_id}")


def _normalise(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\b(station|terminal|train)\b", "", text)
    return re.sub(r"[^a-z0-9 ]+", "", text).strip()


def find_stop_id(name: str) -> Optional[str]:
    """Resolve a spoken station name to a stop id, or None."""
    if not name:
        return None
    if name in _stations():           # already a stop id
        return name

    target = _normalise(ALIASES.get(_normalise(name), name))
    stations = _stations()

    for stop_id, canonical in stations.items():
        if _normalise(canonical) == target:
            return stop_id

    # Fall back to prefix, then substring, preferring the shortest name so
    # "Hempstead" does not resolve to "West Hempstead".
    for predicate in (
        lambda c: _normalise(c).startswith(target),
        lambda c: target in _normalise(c),
    ):
        matches = [(sid, c) for sid, c in stations.items() if predicate(c)]
        if matches:
            return min(matches, key=lambda kv: len(kv[1]))[0]
    return None
