"""LangGraph tools for the LIRR."""

from __future__ import annotations

import re
from datetime import date as date_cls, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from .live import get_live_stop
from .predict import predict_track
from .schedule import ScheduledStop, find_departures
from .stations import find_stop_id, station_name

EASTERN = ZoneInfo("America/New_York")

_TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\s*$", re.I)


def _now_eastern() -> datetime:
    return datetime.now(timezone.utc).astimezone(EASTERN)


def parse_time_of_day(text: str, now: Optional[datetime] = None) -> Optional[int]:
    """"5:00", "5pm", "17:02" -> minutes after midnight.

    A bare "5:00" from a commuter almost always means the evening, so an
    unqualified hour resolves to whichever reading is still ahead of them.
    """
    match = _TIME_RE.match(text or "")
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower().replace(".", "")

    if meridiem.startswith("p") and hour != 12:
        hour += 12
    elif meridiem.startswith("a") and hour == 12:
        hour = 0
    elif not meridiem and hour < 12:
        now = now or _now_eastern()
        current = now.hour * 60 + now.minute
        if hour * 60 + minute < current:
            hour += 12          # the morning reading has already gone by
    return hour * 60 + minute


def _clock(hhmm: str) -> str:
    """"18:19" -> "6:19 PM". The model was re-deriving times from the rider's
    own words and getting the meridiem wrong, so hand it no arithmetic."""
    try:
        hour, minute = int(hhmm[:2]), int(hhmm[3:5])
    except (ValueError, IndexError):
        return hhmm
    suffix = "AM" if hour % 24 < 12 else "PM"
    display = hour % 12 or 12
    return f"{display}:{minute:02d} {suffix}"


def _track_at(train_number: str, stop_id: str, day: date_cls, event_type: str) -> str:
    """Posted track if the MTA has set one, else the historical guess."""
    try:
        live = get_live_stop(train_number, stop_id)
    except Exception:
        live = None
    if live and live.track:
        return f"Track {live.track} (posted)"
    try:
        prediction = predict_track(train_number, stop_id, day, event_type=event_type)
    except Exception:
        return "not posted yet"
    if prediction:
        return f"{prediction.describe()} (predicted, not posted)"
    return "not posted yet, and not enough history to predict"


def _describe(stop: ScheduledStop, day: date_cls, want_track: bool) -> str:
    depart = _clock(stop.departure_time)
    dest_id = stop.destination_stop_id
    dest = stop.headsign or station_name(dest_id)
    origin = station_name(stop.stop_id)
    lines = [f"Train {stop.train_number} departs {origin} at {depart} for {dest}."]

    live = None
    try:
        live = get_live_stop(stop.train_number, stop.stop_id)
    except Exception:                             # feed down should not kill the answer
        lines.append("(couldn't reach the real-time feed just now.)")

    if live:
        lines.append(f"Status: {live.status}.")
        if live.track:
            # Name the station. "Track A" alone reads as the arrival track to
            # someone waiting at Penn, when it is the platform they are
            # leaving from.
            lines.append(f"Departure track at {origin}: Track {live.track} (posted).")
        else:
            lines.append(f"No departure track posted at {origin} yet.")
    else:
        lines.append(
            "Not in the real-time feed yet — it only looks about 4 hours ahead, "
            "so this is the schedule."
        )

    if not want_track:
        return " ".join(lines)

    # "What track will it arrive on" is asked by someone meeting the train, so
    # the track that matters is at the far end — Penn or Grand Central — not
    # the one it is leaving from.
    if dest_id and dest_id != stop.stop_id:
        arrival = _track_at(stop.train_number, dest_id, day, "arrival")
        lines.append(f"Arrival track at {station_name(dest_id)}: {arrival}.")

    if not (live and live.track):
        departure = _track_at(stop.train_number, stop.stop_id, day, "departure")
        if "not posted" not in departure or "history" in departure:
            lines.append(f"Departure track at {origin}: {departure}.")
    return " ".join(lines)


@tool
def lirr_train_status(
    origin: str,
    destination: str = "",
    time_of_day: str = "",
    train_number: str = "",
) -> str:
    """Check an LIRR train: whether it is on time and what track to expect.

    Use for any Long Island Rail Road question — Penn Station, Grand Central,
    Jamaica, Atlantic Terminal, or any branch station. Answers "is the 5:00 to
    Ronkonkoma on time and what track will it be on".

    Args:
        origin: Station you are leaving from, e.g. "Penn Station", "Grand Central"
        destination: Where the train is going, e.g. "Ronkonkoma" (optional)
        time_of_day: Departure time as spoken, e.g. "5:00", "5pm", "17:02" (optional)
        train_number: Exact LIRR train number if the rider knows it (optional)

    Returns:
        Scheduled time, on-time status, and the posted or expected track.
    """
    origin_id = find_stop_id(origin)
    if not origin_id:
        return f"I don't recognise the LIRR station '{origin}'."
    dest_id = find_stop_id(destination) if destination else None
    if destination and not dest_id:
        return f"I don't recognise the LIRR station '{destination}'."

    now = _now_eastern()
    day = now.date()
    near = parse_time_of_day(time_of_day, now) if time_of_day else None

    matches = find_departures(origin_id, dest_id, day, near_minutes=near, limit=3)
    if train_number:
        matches = [s for s in matches if s.train_number == str(train_number)] or matches
    if not matches:
        where = f" to {station_name(dest_id)}" if dest_id else ""
        return (
            f"No scheduled LIRR departures found from {station_name(origin_id)}{where}"
            f"{' near ' + time_of_day if time_of_day else ''} today."
        )

    header = f"{station_name(origin_id)}"
    if dest_id:
        header += f" to {station_name(dest_id)}"
    body = [_describe(stop, day, want_track=True) for stop in matches[:2]]
    return f"{header}:\n" + "\n".join(body)


@tool
def lirr_next_departures(origin: str, destination: str = "") -> str:
    """List the next few LIRR departures from a station.

    Args:
        origin: Station to depart from, e.g. "Penn Station"
        destination: Optional destination to filter by, e.g. "Babylon"

    Returns:
        The next departures with scheduled times and destinations.
    """
    origin_id = find_stop_id(origin)
    if not origin_id:
        return f"I don't recognise the LIRR station '{origin}'."
    dest_id = find_stop_id(destination) if destination else None

    now = _now_eastern()
    near = now.hour * 60 + now.minute
    matches = find_departures(origin_id, dest_id, now.date(), near_minutes=near, window=180, limit=6)
    upcoming = [s for s in matches if s.minutes_after_midnight >= near]
    if not upcoming:
        return f"No more LIRR departures from {station_name(origin_id)} today."

    ordered = sorted(upcoming, key=lambda s: s.minutes_after_midnight)[:5]
    lines = [
        f"  {s.departure_time[:5]}  train {s.train_number} to {s.headsign or station_name(s.destination_stop_id)}"
        for s in ordered
    ]
    return f"Next from {station_name(origin_id)}:\n" + "\n".join(lines)


LIRR_TOOLS = [lirr_train_status, lirr_next_departures]
