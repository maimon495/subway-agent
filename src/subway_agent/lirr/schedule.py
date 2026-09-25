"""The published LIRR timetable.

The realtime feed only looks about four hours ahead, so a question asked in
the morning about an evening train cannot be answered from it at all. This
reads the bundled static schedule, which covers the whole service day.
"""

from __future__ import annotations

import csv
import functools
import gzip
import pathlib
from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional

DATA = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "data"


@dataclass(frozen=True)
class ScheduledStop:
    service_id: str
    trip_id: str
    train_number: str
    route_id: str
    headsign: str
    stop_id: str
    stop_sequence: int
    arrival_time: str
    departure_time: str
    destination_stop_id: str

    @property
    def minutes_after_midnight(self) -> int:
        """GTFS times run past 24:00 for trains after midnight; keep that."""
        source = self.departure_time or self.arrival_time
        hours, minutes, _ = (int(part) for part in source.split(":"))
        return hours * 60 + minutes


@functools.lru_cache(maxsize=1)
def _schedule() -> list[ScheduledStop]:
    path = DATA / "lirr_schedule.csv.gz"
    with gzip.open(path, "rt") as handle:
        return [
            ScheduledStop(
                service_id=r["service_id"],
                trip_id=r["trip_id"],
                train_number=r["train_number"],
                route_id=r["route_id"],
                headsign=r["headsign"],
                stop_id=r["stop_id"],
                stop_sequence=int(r["stop_sequence"]),
                arrival_time=r["arrival_time"],
                departure_time=r["departure_time"],
                destination_stop_id=r["destination_stop_id"],
            )
            for r in csv.DictReader(handle)
        ]


@functools.lru_cache(maxsize=1)
def _service_dates() -> dict[str, set[str]]:
    """date (YYYYMMDD) -> service_ids running that day."""
    path = DATA / "lirr_service_dates.csv"
    by_date: dict[str, set[str]] = {}
    with path.open() as handle:
        for row in csv.DictReader(handle):
            # LIRR publishes only additions; type 2 would be a removal.
            if row["exception_type"] != "1":
                continue
            by_date.setdefault(row["date"], set()).add(row["service_id"])
    return by_date


def services_on(day: date_cls) -> set[str]:
    return _service_dates().get(day.strftime("%Y%m%d"), set())


def find_departures(
    origin_stop_id: str,
    destination_stop_id: Optional[str],
    day: date_cls,
    near_minutes: Optional[int] = None,
    window: int = 90,
    limit: int = 6,
) -> list[ScheduledStop]:
    """Scheduled departures from a station, optionally toward a destination.

    `near_minutes` is minutes after midnight; results are ordered by how close
    they sit to it so "the 5:00" picks the 5:02 rather than the first of the day.
    """
    running = services_on(day)
    if not running:
        return []

    by_trip: dict[str, list[ScheduledStop]] = {}
    for stop in _schedule():
        if stop.service_id in running:
            by_trip.setdefault(stop.trip_id, []).append(stop)

    candidates = []
    for stops in by_trip.values():
        stops.sort(key=lambda s: s.stop_sequence)
        origin = next((s for s in stops if s.stop_id == origin_stop_id), None)
        if not origin:
            continue
        # The last stop of a trip is where it terminates, not somewhere you can
        # board. Without this, trains arriving into Penn are listed as Penn
        # departures "to Penn Station".
        if origin.stop_sequence >= max(s.stop_sequence for s in stops):
            continue
        if destination_stop_id:
            # The destination must come later in the trip, otherwise a train
            # that already passed through it would match.
            later = [s.stop_id for s in stops if s.stop_sequence > origin.stop_sequence]
            if destination_stop_id not in later:
                continue
        candidates.append(origin)

    if near_minutes is None:
        return sorted(candidates, key=lambda s: s.minutes_after_midnight)[:limit]

    near = [s for s in candidates if abs(s.minutes_after_midnight - near_minutes) <= window]
    return sorted(near, key=lambda s: abs(s.minutes_after_midnight - near_minutes))[:limit]
