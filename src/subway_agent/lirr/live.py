"""Live LIRR status for a specific train: is it late, and is a track posted yet."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from google.transit import gtfs_realtime_pb2
from google.protobuf.unknown_fields import UnknownFieldSet

from .feed import (
    MTA_RAILROAD_STU_FIELD,
    fetch_feed,
    parse_railroad_extension,
    train_number_from_trip_id,
)


@dataclass(frozen=True)
class LiveStop:
    train_number: str
    stop_id: str
    track: Optional[str]
    delay_seconds: Optional[int]
    event_type: str
    event_time: Optional[datetime]

    @property
    def delay_minutes(self) -> Optional[int]:
        if self.delay_seconds is None:
            return None
        return round(self.delay_seconds / 60)

    @property
    def status(self) -> str:
        minutes = self.delay_minutes
        if minutes is None:
            return "running, no delay reported"
        if minutes <= 1:
            return "on time"
        return f"running about {minutes} min late"


def get_live_stop(train_number: str, stop_id: str) -> Optional[LiveStop]:
    """Find a train's stop in the live feed, or None if it isn't in it yet.

    The feed only looks about four hours ahead, so None is the normal answer
    for anything later in the day — it does not mean the train is cancelled.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(fetch_feed())

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        if train_number_from_trip_id(entity.trip_update.trip.trip_id) != str(train_number):
            continue
        for stu in entity.trip_update.stop_time_update:
            if stu.stop_id != stop_id:
                continue
            track = None
            for field in UnknownFieldSet(stu):
                if field.field_number == MTA_RAILROAD_STU_FIELD:
                    track, _ = parse_railroad_extension(field.data)

            event_type, event_time, delay = "departure", None, None
            if stu.HasField("departure") and stu.departure.time:
                event_time = datetime.fromtimestamp(stu.departure.time, tz=timezone.utc)
                delay = stu.departure.delay if stu.departure.HasField("delay") else None
            elif stu.HasField("arrival") and stu.arrival.time:
                event_type = "arrival"
                event_time = datetime.fromtimestamp(stu.arrival.time, tz=timezone.utc)
                delay = stu.arrival.delay if stu.arrival.HasField("delay") else None

            return LiveStop(
                train_number=str(train_number),
                stop_id=stop_id,
                track=track,
                delay_seconds=delay,
                event_type=event_type,
                event_time=event_time,
            )
    return None
