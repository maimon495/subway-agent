"""GTFS static data parser for subway travel times."""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from .config import DATA_DIR


@dataclass
class StationTravelTime:
    """Travel time between two stations on a specific route."""
    from_stop_id: str
    to_stop_id: str
    route_id: str
    trip_id: str
    travel_time_seconds: int
    is_express: bool = False


class GTFSStaticParser:
    """Parser for MTA GTFS static data."""

    GTFS_URL = "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip"
    GTFS_SUPPLEMENTED_URL = "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_supplemented.zip"

    def __init__(self, use_supplemented: bool = False):
        """Initialize the GTFS parser.
        
        Args:
            use_supplemented: If True, use supplemented GTFS with service changes
        """
        self.use_supplemented = use_supplemented
        self.gtfs_path = DATA_DIR / "gtfs_subway.zip"
        self.stops: dict[str, dict] = {}
        self.routes: dict[str, dict] = {}
        self.trips: dict[str, dict] = {}
        self.stop_times: list[dict] = []
        self.travel_times: dict[tuple[str, str, str], int] = {}  # (from_stop, to_stop, route) -> seconds

    def download_gtfs(self, force: bool = False) -> bool:
        """Download GTFS static data if not already present.
        
        Args:
            force: Force re-download even if file exists
            
        Returns:
            True if download successful, False otherwise
        """
        if self.gtfs_path.exists() and not force:
            return True

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        url = self.GTFS_SUPPLEMENTED_URL if self.use_supplemented else self.GTFS_URL
        print(f"Downloading GTFS data from {url}...")

        try:
            # Use longer timeout for large file (~10-20MB) and stream for better memory usage
            response = requests.get(url, timeout=120, stream=True)
            response.raise_for_status()
            
            # Stream download to handle large files better
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(self.gtfs_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            print(f"GTFS data downloaded to {self.gtfs_path} ({downloaded / 1024 / 1024:.1f} MB)")
            return True
        except requests.exceptions.Timeout:
            print(f"Error downloading GTFS data: Request timed out after 120 seconds")
            return False
        except requests.exceptions.ConnectionError as e:
            print(f"Error downloading GTFS data: Connection failed - {e}")
            print("  This may indicate network restrictions or firewall rules blocking HTTPS outbound traffic")
            return False
        except Exception as e:
            print(f"Error downloading GTFS data: {e}")
            return False

    def parse_gtfs(self) -> bool:
        """Parse GTFS zip file and extract travel times.
        
        Returns:
            True if parsing successful, False otherwise
        """
        if not self.gtfs_path.exists():
            if not self.download_gtfs():
                return False

        try:
            with zipfile.ZipFile(self.gtfs_path, 'r') as zf:
                # Parse stops.txt
                self._parse_stops(zf)
                
                # Parse routes.txt
                self._parse_routes(zf)
                
                # Parse trips.txt
                self._parse_trips(zf)
                
                # Parse stop_times.txt to get travel times
                self._parse_stop_times(zf)
                
                # Calculate travel times between consecutive stops
                self._calculate_travel_times()
                
            print(f"Parsed GTFS data: {len(self.stops)} stops, {len(self.routes)} routes")
            return True
        except Exception as e:
            print(f"Error parsing GTFS data: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _parse_stops(self, zf: zipfile.ZipFile):
        """Parse stops.txt file."""
        try:
            with zf.open('stops.txt') as f:
                reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
                for row in reader:
                    stop_id = row['stop_id']
                    self.stops[stop_id] = {
                        'stop_id': stop_id,
                        'stop_name': row.get('stop_name', ''),
                        'stop_lat': float(row.get('stop_lat', 0)),
                        'stop_lon': float(row.get('stop_lon', 0)),
                    }
        except KeyError:
            print("Warning: stops.txt not found in GTFS zip")

    def _parse_routes(self, zf: zipfile.ZipFile):
        """Parse routes.txt file."""
        try:
            with zf.open('routes.txt') as f:
                reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
                for row in reader:
                    route_id = row['route_id']
                    self.routes[route_id] = {
                        'route_id': route_id,
                        'route_short_name': row.get('route_short_name', ''),
                        'route_long_name': row.get('route_long_name', ''),
                        'route_type': int(row.get('route_type', 1)),
                    }
        except KeyError:
            print("Warning: routes.txt not found in GTFS zip")

    def _parse_trips(self, zf: zipfile.ZipFile):
        """Parse trips.txt file."""
        try:
            with zf.open('trips.txt') as f:
                reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
                for row in reader:
                    trip_id = row['trip_id']
                    self.trips[trip_id] = {
                        'trip_id': trip_id,
                        'route_id': row.get('route_id', ''),
                        'service_id': row.get('service_id', ''),
                        'trip_headsign': row.get('trip_headsign', ''),
                        'direction_id': row.get('direction_id', ''),
                    }
        except KeyError:
            print("Warning: trips.txt not found in GTFS zip")

    def _parse_stop_times(self, zf: zipfile.ZipFile):
        """Parse stop_times.txt file."""
        try:
            with zf.open('stop_times.txt') as f:
                reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
                for row in reader:
                    self.stop_times.append({
                        'trip_id': row['trip_id'],
                        'arrival_time': row.get('arrival_time', ''),
                        'departure_time': row.get('departure_time', ''),
                        'stop_id': row['stop_id'],
                        'stop_sequence': int(row.get('stop_sequence', 0)),
                    })
        except KeyError:
            print("Warning: stop_times.txt not found in GTFS zip")

    def _time_to_seconds(self, time_str: str) -> Optional[int]:
        """Convert HH:MM:SS time string to seconds since midnight.
        
        Args:
            time_str: Time string in HH:MM:SS format (can be > 24 hours)
            
        Returns:
            Seconds since midnight, or None if invalid
        """
        try:
            parts = time_str.split(':')
            if len(parts) != 3:
                return None
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            return None

    def _calculate_travel_times(self):
        """Calculate travel times between consecutive stops for each trip."""
        # Group stop_times by trip_id
        trips_stops: dict[str, list[dict]] = defaultdict(list)
        for stop_time in self.stop_times:
            trips_stops[stop_time['trip_id']].append(stop_time)

        # Sort by stop_sequence for each trip
        for trip_id, stops in trips_stops.items():
            stops.sort(key=lambda x: x['stop_sequence'])

        # Calculate travel times between consecutive stops
        for trip_id, stops in trips_stops.items():
            if trip_id not in self.trips:
                continue
            
            route_id = self.trips[trip_id]['route_id']
            if not route_id:
                continue

            for i in range(len(stops) - 1):
                from_stop = stops[i]
                to_stop = stops[i + 1]

                from_time = self._time_to_seconds(from_stop['departure_time'])
                to_time = self._time_to_seconds(to_stop['arrival_time'])

                if from_time is None or to_time is None:
                    continue

                # Handle times that cross midnight (next day)
                if to_time < from_time:
                    to_time += 24 * 3600

                travel_seconds = to_time - from_time

                # Skip unrealistic travel times (> 30 minutes between consecutive stops)
                if travel_seconds < 0 or travel_seconds > 1800:
                    continue

                key = (from_stop['stop_id'], to_stop['stop_id'], route_id)
                
                # Store minimum travel time for this route (most efficient)
                if key not in self.travel_times:
                    self.travel_times[key] = travel_seconds
                else:
                    self.travel_times[key] = min(self.travel_times[key], travel_seconds)

    def get_travel_time(
        self, 
        from_stop_id: str, 
        to_stop_id: str, 
        route_id: Optional[str] = None
    ) -> Optional[int]:
        """Get travel time between two stops in seconds.
        
        Args:
            from_stop_id: GTFS stop ID of origin station (without direction suffix)
            to_stop_id: GTFS stop ID of destination station (without direction suffix)
            route_id: Optional route ID to filter by specific line
            
        Returns:
            Travel time in seconds, or None if not found
        """
        # Remove direction suffix (N/S) if present for matching
        from_base = from_stop_id.rstrip('NS')
        to_base = to_stop_id.rstrip('NS')
        
        if route_id:
            # Try exact match first
            key = (from_base, to_base, route_id)
            if key in self.travel_times:
                return self.travel_times[key]
            
            # Try with original IDs
            key = (from_stop_id, to_stop_id, route_id)
            if key in self.travel_times:
                return self.travel_times[key]
            
            return None
        else:
            # Find minimum travel time across all routes
            min_time = None
            for (f, t, r), time_sec in self.travel_times.items():
                f_base = f.rstrip('NS')
                t_base = t.rstrip('NS')
                if (f_base == from_base and t_base == to_base) or (f == from_stop_id and t == to_stop_id):
                    if min_time is None or time_sec < min_time:
                        min_time = time_sec
            return min_time

    def get_travel_time_minutes(
        self,
        from_stop_id: str,
        to_stop_id: str,
        route_id: Optional[str] = None
    ) -> Optional[int]:
        """Get travel time between two stops in minutes (rounded).
        
        Args:
            from_stop_id: GTFS stop ID of origin station
            to_stop_id: GTFS stop ID of destination station
            route_id: Optional route ID to filter by specific line
            
        Returns:
            Travel time in minutes (rounded), or None if not found
        """
        seconds = self.get_travel_time(from_stop_id, to_stop_id, route_id)
        if seconds is None:
            return None
        return round(seconds / 60)

    def get_route_travel_times(self, route_id: str) -> dict[tuple[str, str], int]:
        """Get all travel times for a specific route.
        
        Args:
            route_id: Route ID (e.g., "1", "A")
            
        Returns:
            Dict mapping (from_stop_id, to_stop_id) -> travel_time_seconds
        """
        result = {}
        for (from_stop, to_stop, r_id), time_sec in self.travel_times.items():
            if r_id == route_id:
                result[(from_stop, to_stop)] = time_sec
        return result


# Singleton instance
_gtfs_parser: Optional[GTFSStaticParser] = None


def get_gtfs_parser(use_supplemented: bool = False) -> Optional[GTFSStaticParser]:
    """Get or create the GTFS parser singleton.
    
    Args:
        use_supplemented: Use supplemented GTFS with service changes
        
    Returns:
        GTFSStaticParser instance if successful, None otherwise
    """
    global _gtfs_parser
    if _gtfs_parser is None:
        _gtfs_parser = GTFSStaticParser(use_supplemented=use_supplemented)
        if not _gtfs_parser.parse_gtfs():
            _gtfs_parser = None
            return None
    return _gtfs_parser
