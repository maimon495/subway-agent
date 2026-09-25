#!/usr/bin/env python3
"""Rebuild the bundled LIRR schedule index from the MTA's static GTFS.

The realtime feed only looks about four hours ahead, so "the 5:00 to
Ronkonkoma" asked in the morning cannot be answered from it. The static
schedule covers the whole day, and it is small enough (roughly 2,000 trips)
to ship with the agent rather than fetched at runtime.

Run after the MTA publishes a new general order:

    python scripts/build_lirr_schedule.py
"""

from __future__ import annotations

import csv
import gzip
import io
import pathlib
import zipfile

import requests

STATIC_URL = "https://rrgtfsfeeds.s3.amazonaws.com/gtfslirr.zip"
DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = requests.get(STATIC_URL, timeout=120)
    payload.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(payload.content))

    def read(name: str) -> list[dict]:
        with archive.open(name) as handle:
            return list(csv.DictReader(io.TextIOWrapper(handle, "utf-8-sig")))

    stops = {r["stop_id"]: r["stop_name"] for r in read("stops.txt")}
    trips = {r["trip_id"]: r for r in read("trips.txt")}
    stop_times = read("stop_times.txt")

    # Final stop of each trip is its destination; the feed has no headsign at
    # runtime, so the schedule is where a destination stop id comes from.
    last_stop: dict[str, tuple[int, str]] = {}
    for row in stop_times:
        seq = int(row["stop_sequence"])
        trip = row["trip_id"]
        if trip not in last_stop or seq > last_stop[trip][0]:
            last_stop[trip] = (seq, row["stop_id"])

    out = DATA_DIR / "lirr_schedule.csv.gz"
    written = 0
    with gzip.open(out, "wt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "service_id", "trip_id", "train_number", "route_id", "headsign",
            "stop_id", "stop_sequence", "arrival_time", "departure_time",
            "destination_stop_id",
        ])
        for row in stop_times:
            trip = trips.get(row["trip_id"])
            if not trip:
                continue
            writer.writerow([
                trip["service_id"], row["trip_id"],
                trip.get("trip_short_name") or "", trip["route_id"],
                trip.get("trip_headsign") or "",
                row["stop_id"], row["stop_sequence"],
                row["arrival_time"], row["departure_time"],
                last_stop.get(row["trip_id"], (0, ""))[1],
            ])
            written += 1

    dates = DATA_DIR / "lirr_service_dates.csv"
    with dates.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["service_id", "date", "exception_type"])
        for row in read("calendar_dates.txt"):
            writer.writerow([row["service_id"], row["date"], row["exception_type"]])

    stations = DATA_DIR / "lirr_stations.csv"
    with stations.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["stop_id", "stop_name"])
        for stop_id, name in sorted(stops.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
            writer.writerow([stop_id, name])

    print(f"schedule rows: {written}")
    print(f"stations: {len(stops)}   trips: {len(trips)}")


if __name__ == "__main__":
    main()
