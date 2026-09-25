"""LIRR GTFS-realtime feed: fetch and parse, including track assignments.

Track is NOT a standard GTFS-realtime field. The MTA carries it in a railroad
extension on StopTimeUpdate, field number 1005, whose payload is a nested
message:

    MtaRailroadStopTimeUpdate { 1: track (string), 2: trainStatus (string) }

Stock GTFS-realtime bindings silently drop unknown fields, so a normal decode
returns no track at all — every value comes back empty and nothing complains.
That is why this module reads the extension out of the protobuf unknown-field
set by hand rather than relying on the generated classes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Optional
import re

import requests
from google.transit import gtfs_realtime_pb2
from google.protobuf.unknown_fields import UnknownFieldSet

LIRR_FEED_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/lirr%2Fgtfs-lirr"

MTA_RAILROAD_STU_FIELD = 1005

PENN_STATION_STOP_ID = "237"
GRAND_CENTRAL_STOP_ID = "349"
JAMAICA_STOP_ID = "102"
ATLANTIC_TERMINAL_STOP_ID = "241"

# Real trip ids look like "GO202_26_809": general-order id, schedule number,
# then the LIRR train number. Mets specials add a suffix — "GO202_26_1125_2_METS"
# is train 1125. So the train number is the third segment, NOT the last one:
# the last is 26 for every trip in the feed, which is the schedule, not a train.
# (The old TypeScript expected "1923_2026-05-19" and never matched at all.)
_GO_TRAIN_NUMBER_RE = re.compile(r"^GO[^_]*_\d+_(\d+)")
# Fallback for the documented real-time form, e.g. "1923_2026-05-19".
_DATED_TRAIN_NUMBER_RE = re.compile(r"^(\d+)_\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class TrackObservation:
    trip_id: str
    train_number: Optional[str]
    route_id: str
    direction_id: Optional[int]
    service_date: Optional[str]          # YYYYMMDD, from the trip descriptor
    stop_id: str
    stop_sequence: Optional[int]
    origin_stop_id: Optional[str]
    destination_stop_id: Optional[str]
    track: str
    train_status: Optional[str]
    event_type: str                      # "arrival" or "departure"
    event_time: Optional[datetime]

    @property
    def is_terminal(self) -> bool:
        """Terminals are where a track guess is actually worth something."""
        return self.stop_id in (
            PENN_STATION_STOP_ID,
            GRAND_CENTRAL_STOP_ID,
            JAMAICA_STOP_ID,
            ATLANTIC_TERMINAL_STOP_ID,
        )


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    val = shift = 0
    while i < len(buf):
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7
    raise ValueError("truncated varint")


def parse_railroad_extension(raw: bytes) -> tuple[Optional[str], Optional[str]]:
    """Decode the MTA railroad StopTimeUpdate extension -> (track, trainStatus).

    Hand-rolled because we have no .proto for it. Unknown field numbers are
    skipped rather than treated as errors, so the MTA adding fields later
    cannot break collection.
    """
    track = status = None
    i = 0
    while i < len(raw):
        key, i = _read_varint(raw, i)
        field_number, wire_type = key >> 3, key & 7
        if wire_type == 2:
            length, i = _read_varint(raw, i)
            value = raw[i : i + length].decode("utf-8", "replace")
            i += length
            if field_number == 1:
                track = value or None
            elif field_number == 2:
                status = value or None
        elif wire_type == 0:
            _, i = _read_varint(raw, i)
        elif wire_type == 5:
            i += 4
        elif wire_type == 1:
            i += 8
        else:
            raise ValueError(f"unhandled wire type {wire_type}")
    return track, status


def train_number_from_trip_id(trip_id: str) -> Optional[str]:
    for pattern in (_GO_TRAIN_NUMBER_RE, _DATED_TRAIN_NUMBER_RE):
        match = pattern.match(trip_id)
        if match:
            return match.group(1)
    return None


def fetch_feed(timeout: int = 30) -> bytes:
    response = requests.get(LIRR_FEED_URL, timeout=timeout)
    response.raise_for_status()
    return response.content


def parse_track_observations(payload: bytes) -> Iterator[TrackObservation]:
    """Yield one observation per stop update that carries a track value."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip = entity.trip_update.trip
        stop_updates = list(entity.trip_update.stop_time_update)
        # The feed carries no headsign, but it lists the whole trip, so the
        # last stop IS the destination. Recorded per observation because a
        # question like "the 5:00 to Ronkonkoma" is unanswerable without it,
        # and history cannot be backfilled later.
        origin_stop_id = stop_updates[0].stop_id if stop_updates else None
        destination_stop_id = stop_updates[-1].stop_id if stop_updates else None
        for stu in stop_updates:
            for field in UnknownFieldSet(stu):
                if field.field_number != MTA_RAILROAD_STU_FIELD:
                    continue
                track, status = parse_railroad_extension(field.data)
                if not track:
                    continue
                # At a terminal such as Penn or Grand Central an arriving train
                # carries only an arrival time and no departure. Since "what
                # track does it come in on" is the whole point, prefer whichever
                # event this stop update actually describes, and record which.
                event_type, event_time = "departure", None
                if stu.HasField("departure") and stu.departure.time:
                    event_time = datetime.fromtimestamp(
                        stu.departure.time, tz=timezone.utc
                    )
                elif stu.HasField("arrival") and stu.arrival.time:
                    event_type = "arrival"
                    event_time = datetime.fromtimestamp(
                        stu.arrival.time, tz=timezone.utc
                    )
                yield TrackObservation(
                    trip_id=trip.trip_id,
                    train_number=train_number_from_trip_id(trip.trip_id),
                    route_id=trip.route_id,
                    direction_id=trip.direction_id if trip.HasField("direction_id") else None,
                    service_date=trip.start_date or None,
                    stop_id=stu.stop_id,
                    stop_sequence=stu.stop_sequence if stu.HasField("stop_sequence") else None,
                    origin_stop_id=origin_stop_id,
                    destination_stop_id=destination_stop_id,
                    # Deliberately NOT normalised or range-checked. Real values
                    # include "A" and "1B", so the numeric-only filtering the
                    # old TypeScript code did would have discarded them.
                    track=track,
                    train_status=status,
                    event_type=event_type,
                    event_time=event_time,
                )
