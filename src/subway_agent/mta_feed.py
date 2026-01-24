"""MTA GTFS-realtime feed parser for real-time train arrivals."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests
from google.transit import gtfs_realtime_pb2

from .config import MTA_FEEDS, LINE_TO_FEED
from .stations import STATIONS, Station


@dataclass
class TrainArrival:
    """Represents a train arrival at a station."""
    line: str
    station_id: str
    station_name: str
    direction: str  # "N" (uptown/Manhattan-bound) or "S" (downtown/Brooklyn-bound)
    arrival_time: datetime
    minutes_until: int
    trip_id: str

    def __str__(self):
        direction_label = "Uptown" if self.direction == "N" else "Downtown"
        return f"{self.line} train ({direction_label}) - {self.minutes_until} min"


class MTAFeedParser:
    """Parser for MTA GTFS-realtime feeds."""

    def __init__(self):
        self._cache: dict[str, tuple[float, any]] = {}
        self._cache_ttl = 30  # seconds

    def _fetch_feed(self, feed_url: str) -> Optional[gtfs_realtime_pb2.FeedMessage]:
        """Fetch and parse a GTFS-realtime feed."""
        # Check cache
        if feed_url in self._cache:
            cached_time, cached_data = self._cache[feed_url]
            if time.time() - cached_time < self._cache_ttl:
                return cached_data

        try:
            response = requests.get(feed_url, timeout=10)
            response.raise_for_status()

            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)

            # Cache the result
            self._cache[feed_url] = (time.time(), feed)
            return feed

        except Exception as e:
            print(f"Error fetching MTA feed: {e}")
            return None

    def _parse_stop_id(self, stop_id: str) -> tuple[str, str]:
        """Parse GTFS stop ID into station ID and direction.

        GTFS stop IDs are formatted as: {stop_id}{direction}
        e.g., "142N" = South Ferry, Northbound
        """
        if stop_id and stop_id[-1] in ("N", "S"):
            return stop_id[:-1], stop_id[-1]
        return stop_id, ""

    def _find_station_by_gtfs_id(self, gtfs_id: str) -> Optional[Station]:
        """Find station by GTFS stop ID."""
        for station in STATIONS.values():
            if station.gtfs_stop_id == gtfs_id:
                return station
        return None

    def get_arrivals_for_station(
        self, station_id: str, lines: Optional[list[str]] = None
    ) -> list[TrainArrival]:
        """Get upcoming train arrivals for a station.

        Args:
            station_id: The station ID to get arrivals for
            lines: Optional list of lines to filter by

        Returns:
            List of TrainArrival objects sorted by arrival time
        """
        station = STATIONS.get(station_id)
        if not station:
            return []

        arrivals = []
        now = datetime.now()

        # Determine which feeds to query
        if lines:
            feed_urls = set(LINE_TO_FEED.get(line.upper()) for line in lines if line.upper() in LINE_TO_FEED)
        else:
            feed_urls = set(LINE_TO_FEED.get(line) for line in station.lines if line in LINE_TO_FEED)

        for feed_url in feed_urls:
            if not feed_url:
                continue

            feed = self._fetch_feed(feed_url)
            if not feed:
                continue

            for entity in feed.entity:
                if not entity.HasField("trip_update"):
                    continue

                trip_update = entity.trip_update
                route_id = trip_update.trip.route_id

                # Filter by requested lines
                if lines and route_id not in [l.upper() for l in lines]:
                    continue

                for stop_time_update in trip_update.stop_time_update:
                    gtfs_stop_id, direction = self._parse_stop_id(stop_time_update.stop_id)

                    # Check if this is the station we're looking for
                    if gtfs_stop_id != station.gtfs_stop_id:
                        continue

                    # Get arrival time
                    if stop_time_update.HasField("arrival"):
                        arrival_timestamp = stop_time_update.arrival.time
                    elif stop_time_update.HasField("departure"):
                        arrival_timestamp = stop_time_update.departure.time
                    else:
                        continue

                    arrival_time = datetime.fromtimestamp(arrival_timestamp)
                    minutes_until = int((arrival_time - now).total_seconds() / 60)

                    # Only include future arrivals
                    if minutes_until < 0:
                        continue

                    arrivals.append(TrainArrival(
                        line=route_id,
                        station_id=station_id,
                        station_name=station.name,
                        direction=direction,
                        arrival_time=arrival_time,
                        minutes_until=minutes_until,
                        trip_id=trip_update.trip.trip_id,
                    ))

        # Sort by arrival time
        arrivals.sort(key=lambda a: a.arrival_time)
        return arrivals

    def get_arrivals_for_line(self, line: str, limit: int = 10) -> dict[str, list[TrainArrival]]:
        """Get arrivals for all stations on a line.

        Returns:
            Dict mapping station_id to list of arrivals
        """
        line = line.upper()
        feed_url = LINE_TO_FEED.get(line)
        if not feed_url:
            return {}

        feed = self._fetch_feed(feed_url)
        if not feed:
            return {}

        arrivals_by_station: dict[str, list[TrainArrival]] = {}
        now = datetime.now()

        for entity in feed.entity:
            if not entity.HasField("trip_update"):
                continue

            trip_update = entity.trip_update
            route_id = trip_update.trip.route_id

            if route_id != line:
                continue

            for stop_time_update in trip_update.stop_time_update:
                gtfs_stop_id, direction = self._parse_stop_id(stop_time_update.stop_id)
                station = self._find_station_by_gtfs_id(gtfs_stop_id)

                if not station:
                    continue

                if stop_time_update.HasField("arrival"):
                    arrival_timestamp = stop_time_update.arrival.time
                elif stop_time_update.HasField("departure"):
                    arrival_timestamp = stop_time_update.departure.time
                else:
                    continue

                arrival_time = datetime.fromtimestamp(arrival_timestamp)
                minutes_until = int((arrival_time - now).total_seconds() / 60)

                if minutes_until < 0:
                    continue

                if station.id not in arrivals_by_station:
                    arrivals_by_station[station.id] = []

                arrivals_by_station[station.id].append(TrainArrival(
                    line=route_id,
                    station_id=station.id,
                    station_name=station.name,
                    direction=direction,
                    arrival_time=arrival_time,
                    minutes_until=minutes_until,
                    trip_id=trip_update.trip.trip_id,
                ))

        # Sort arrivals at each station
        for station_id in arrivals_by_station:
            arrivals_by_station[station_id].sort(key=lambda a: a.arrival_time)
            arrivals_by_station[station_id] = arrivals_by_station[station_id][:limit]

        return arrivals_by_station


# Singleton instance
mta_feed = MTAFeedParser()


def get_arrivals(station_id: str, lines: Optional[list[str]] = None) -> list[TrainArrival]:
    """Convenience function to get arrivals for a station."""
    return mta_feed.get_arrivals_for_station(station_id, lines)
