"""Can I make that train?

The question that starts every commute: I am somewhere on the subway system,
there is an LIRR train I want, will I make it. Answering it needs both halves —
when the next subway comes, how long it takes to the terminal, how long the walk
up to the concourse is, and when the LIRR train actually leaves — and until now
those halves could not see each other.

The honest output is a margin, not a yes. "Six minutes spare" lets a person
decide; "yes" hides how close it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from ..mta_feed import get_arrivals
from ..routing import subway_graph
from ..stations import STATIONS, find_station
from .schedule import ScheduledStop
from .feed import (
    ATLANTIC_TERMINAL_STOP_ID,
    GRAND_CENTRAL_STOP_ID,
    JAMAICA_STOP_ID,
    PENN_STATION_STOP_ID,
)
from .stations import station_name

EASTERN = ZoneInfo("America/New_York")

# Subway platform to LIRR concourse, on foot. These are not the same station
# even where they share a name: Grand Central Madison sits eight storeys down,
# and the walk is long enough to lose a train you would otherwise have made.
TERMINAL_WALK_MINUTES = {
    PENN_STATION_STOP_ID: 6,
    GRAND_CENTRAL_STOP_ID: 10,
    ATLANTIC_TERMINAL_STOP_ID: 4,
    JAMAICA_STOP_ID: 4,
}

# Subway stations that put a rider inside each LIRR terminal, by station id
# rather than name: display names are not unique, and "34th St-Penn Station"
# resolves to the A/C/E station or the 1/2/3 one depending on the spelling,
# which silently produced routes to the wrong platform. Several ids per
# terminal because Penn is reachable from either line group and the shorter
# ride depends on where the rider starts.
TERMINAL_SUBWAY_STATION_IDS = {
    PENN_STATION_STOP_ID: ["34th_penn_123", "34th_penn_ace"],
    GRAND_CENTRAL_STOP_ID: ["grand_central"],
    ATLANTIC_TERMINAL_STOP_ID: ["atlantic_barclays"],
    JAMAICA_STOP_ID: ["jamaica_179"],
}

# Below this, treat it as "running for it" rather than a comfortable catch.
TIGHT_MARGIN_MINUTES = 4


@dataclass
class Connection:
    origin: str
    terminal_stop_id: str
    line: Optional[str]
    wait_minutes: Optional[int]
    ride_minutes: Optional[int]
    walk_minutes: int
    arrive_by: Optional[datetime]
    train_departs: datetime
    margin_minutes: Optional[int]
    note: Optional[str] = None

    @property
    def makeable(self) -> Optional[bool]:
        if self.margin_minutes is None:
            return None
        return self.margin_minutes >= 0

    def describe(self) -> str:
        terminal = station_name(self.terminal_stop_id)
        if self.margin_minutes is None:
            return (
                f"Couldn't work out the subway leg from {self.origin} to {terminal}"
                + (f" — {self.note}" if self.note else "")
            )
        legs = []
        if self.line and self.wait_minutes is not None:
            legs.append(f"{self.line} train in {self.wait_minutes} min")
        if self.ride_minutes is not None:
            legs.append(f"{self.ride_minutes} min ride")
        legs.append(f"{self.walk_minutes} min walk up at {terminal}")
        route = ", ".join(legs)

        if self.margin_minutes < 0:
            return (
                f"No — {route} puts you at the platform about "
                f"{abs(self.margin_minutes)} min after it leaves."
            )
        if self.margin_minutes < TIGHT_MARGIN_MINUTES:
            return f"Tight — {route} leaves about {self.margin_minutes} min spare. You'd be moving."
        return f"Yes — {route}, about {self.margin_minutes} min spare."


def terminal_for(stop: ScheduledStop) -> Optional[str]:
    """Which terminal the rider boards at."""
    return stop.stop_id if stop.stop_id in TERMINAL_WALK_MINUTES else None


def assess(
    from_station_name: str,
    stop: ScheduledStop,
    now: Optional[datetime] = None,
) -> Connection:
    """Work out whether a rider at `from_station_name` makes this train."""
    now = now or datetime.now(EASTERN)
    terminal_id = terminal_for(stop) or PENN_STATION_STOP_ID
    walk = TERMINAL_WALK_MINUTES.get(terminal_id, 6)

    departs = datetime.combine(
        now.date(),
        datetime.strptime(stop.departure_time[:5], "%H:%M").time(),
        tzinfo=EASTERN,
    )
    # GTFS times run past 24:00 for after-midnight trains.
    if int(stop.departure_time[:2]) >= 24:
        departs += timedelta(days=1)

    blank = Connection(
        origin=from_station_name, terminal_stop_id=terminal_id, line=None,
        wait_minutes=None, ride_minutes=None, walk_minutes=walk,
        arrive_by=None, train_departs=departs, margin_minutes=None,
    )

    origin = find_station(from_station_name)
    if not origin:
        blank.note = f"I don't recognise the subway station '{from_station_name}'"
        return blank

    candidates = [
        STATIONS[sid]
        for sid in TERMINAL_SUBWAY_STATION_IDS.get(terminal_id, [])
        if sid in STATIONS
    ]
    if not candidates:
        blank.note = "no subway station mapped for that terminal"
        return blank

    # Pick whichever entrance actually gives the shorter ride from here.
    best = None
    for candidate in candidates:
        if origin.id == candidate.id:
            best = (0, candidate, None)
            break
        # By id, not name: find_route(name) re-resolves and collapses the
        # five stations called "23rd St" onto whichever one matches first.
        option = subway_graph.find_route(origin.id, candidate.id)
        if option and (best is None or option.total_time_minutes < best[0]):
            best = (option.total_time_minutes, candidate, option)
    if best is None:
        blank.note = "no subway route found"
        return blank
    _, destination, route = best

    if origin.id == destination.id:
        # Already there; only the walk upstairs is left.
        margin = int((departs - now).total_seconds() // 60) - walk
        return Connection(
            origin=from_station_name, terminal_stop_id=terminal_id, line=None,
            wait_minutes=0, ride_minutes=0, walk_minutes=walk,
            arrive_by=now + timedelta(minutes=walk),
            train_departs=departs, margin_minutes=margin,
        )

    if not route or not route.segments:
        blank.note = "no subway route found"
        return blank

    ride = route.total_time_minutes
    first_line = route.segments[0].line

    # Real waiting time, not an average — it is most of the variance on a
    # short hop and the whole reason a specific train is or is not makeable.
    wait = None
    try:
        # A train arriving in under a minute is one you are already missing;
        # counting it makes a connection look makeable when it is not.
        arrivals = [a for a in (get_arrivals(origin.id, [first_line]) or []) if a.minutes_until >= 1]
        if arrivals:
            wait = min(a.minutes_until for a in arrivals)
    except Exception:
        wait = None
    if wait is None:
        # No live data: assume a typical headway rather than refuse to answer,
        # and say so.
        wait = 6
        blank.note = "no live arrivals; assumed a 6 min wait"

    arrive_by = now + timedelta(minutes=wait + ride + walk)
    margin = int((departs - arrive_by).total_seconds() // 60)

    return Connection(
        origin=origin.name, terminal_stop_id=terminal_id, line=first_line,
        wait_minutes=wait, ride_minutes=ride, walk_minutes=walk,
        arrive_by=arrive_by, train_departs=departs, margin_minutes=margin,
        note=blank.note,
    )
