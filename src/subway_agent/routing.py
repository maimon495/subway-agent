"""Subway routing with graph-based pathfinding."""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass
from typing import Optional

from .stations import STATIONS, Station, find_station
from .gtfs_static import get_gtfs_parser


@dataclass
class RouteSegment:
    """A segment of a subway route on one line."""
    line: str
    from_station: Station
    to_station: Station
    stops: list[Station]
    travel_time_minutes: int

    def __str__(self):
        return f"Take {self.line} from {self.from_station.name} to {self.to_station.name} ({len(self.stops)-1} stops, ~{self.travel_time_minutes} min)"


@dataclass
class Route:
    """A complete route with possible transfers."""
    segments: list[RouteSegment]
    total_time_minutes: int
    transfer_count: int

    def __str__(self):
        result = []
        for i, seg in enumerate(self.segments):
            result.append(f"{i+1}. {seg}")
        result.append(f"\nTotal: ~{self.total_time_minutes} minutes, {self.transfer_count} transfer(s)")
        return "\n".join(result)


# Average travel time between stations (in minutes) - fallback if GTFS data unavailable
AVG_TIME_BETWEEN_STOPS = 2
TRANSFER_TIME = 5  # minutes to transfer between lines

# Line connections - which stations connect which lines
# Format: {station_id: [lines]}
TRANSFER_STATIONS = {
    # Major Manhattan hubs
    "42nd_times_sq": ["1", "2", "3", "7", "N", "Q", "R", "W", "S"],
    "grand_central": ["4", "5", "6", "7", "S"],
    "34th_herald": ["B", "D", "F", "M", "N", "Q", "R", "W"],
    "34th_penn_123": ["1", "2", "3"],
    "34th_penn_ace": ["A", "C", "E"],
    "14th_123": ["1", "2", "3"],
    "union_sq": ["4", "5", "6", "N", "Q", "R", "W", "L"],
    "59th_columbus": ["1", "A", "C", "B", "D"],
    "fulton": ["2", "3", "4", "5", "A", "C", "J", "Z"],
    "canal_ace": ["A", "C", "E"],
    "canal_nqrw": ["N", "Q", "R", "W"],
    "west_4th": ["A", "C", "E", "B", "D", "F", "M"],
    "broadway_lafayette": ["B", "D", "F", "M"],
    "125th_abc": ["A", "B", "C", "D"],

    # Brooklyn
    "atlantic_barclays": ["2", "3", "4", "5", "B", "D", "N", "Q", "R"],
    "jay_st": ["A", "C", "F", "R"],
    "borough_hall": ["2", "3", "4", "5"],
    "dekalb_av": ["B", "Q", "R"],

    # Queens
    "jackson_hts": ["7", "E", "F", "M", "R"],
    "queens_plaza": ["E", "M", "R"],
    "court_sq_em": ["E", "M", "G"],
    "queensboro_plaza": ["7", "N", "W"],
    "forest_hills": ["E", "F", "M", "R"],
    "jamaica_center": ["E", "J", "Z"],

    # Bronx
    "149th_grand": ["2", "4", "5"],
    "yankee_stadium": ["4", "B", "D"],
}

# Define line sequences (stations in order)
# This is simplified - in reality we'd load from GTFS static data
LINE_SEQUENCES = {
    "1": [
        "south_ferry", "wall_st_23", "fulton", "park_place", "chambers_123",
        "canal_123", "houston", "christopher", "14th_123", "23rd_1", "28th_1",
        "34th_penn_123", "42nd_times_sq", "50th_1", "59th_columbus", "66th_lincoln",
        "72nd_123", "79th", "86th_1", "96th_123", "103rd_1", "110th_1", "116th_1",
        "125th_1", "137th", "145th_1", "157th", "168th_1", "181st_1", "191st",
        "dyckman_1", "207th", "215th"
    ],
    "2": [
        "south_ferry", "wall_st_23", "fulton", "park_place", "chambers_123",
        "14th_123", "34th_penn_123", "42nd_times_sq", "72nd_123", "96th_123",
        "125th_23", "135th_23", "145th_3", "149th_grand", "3rd_av_149",
        "pelham_pkwy", "allerton", "burke_av", "gun_hill", "219th", "225th",
        "233rd", "nereid", "wakefield_241"
    ],
    "3": [
        "south_ferry", "wall_st_23", "fulton", "park_place", "chambers_123",
        "14th_123", "34th_penn_123", "42nd_times_sq", "72nd_123", "96th_123",
        "125th_23", "135th_23", "145th_3"
    ],
    "4": [
        "bowling_green", "wall_st_45", "fulton", "brooklyn_bridge", "union_sq",
        "grand_central", "59th_456", "86th_456", "125th_456", "138th_grand",
        "149th_grand", "yankee_stadium", "167th", "170th", "176th", "burnside",
        "183rd", "fordham_4", "kingsbridge", "bedford_park_4", "mosholu", "woodlawn"
    ],
    "5": [
        "bowling_green", "wall_st_45", "fulton", "brooklyn_bridge", "union_sq",
        "grand_central", "59th_456", "86th_456", "125th_456", "138th_grand",
        "149th_grand", "3rd_av_149", "pelham_pkwy", "bronx_park_east", "allerton",
        "burke_av", "gun_hill_5", "baychester", "eastchester_dyre"
    ],
    "6": [
        "brooklyn_bridge", "canal_6", "spring_6", "bleecker", "astor_place",
        "union_sq", "23rd_6", "28th_6", "33rd_6", "grand_central", "51st",
        "59th_456", "77th", "86th_456", "96th_6", "103rd_6", "116th_6",
        "125th_456", "3rd_av_138", "brook_av", "cypress_av", "e_143rd",
        "e_149th", "longwood", "hunts_point", "whitlock", "elder_av",
        "morrison_soundview", "st_lawrence", "parkchester", "castle_hill",
        "zerega", "westchester_sq", "middletown", "buhre", "pelham_bay"
    ],
    "7": [
        "34th_penn_ace", "42nd_times_sq", "grand_central", "court_sq_7",
        "hunters_point", "vernon_jackson", "queensboro_plaza", "33rd_rawson",
        "40th_lowery", "46th_bliss", "52nd_lincoln", "61st_woodside", "69th_fisk",
        "74th_broadway", "82nd_jackson", "90th_elmhurst", "junction_blvd",
        "103rd_corona", "111th_st", "mets_willets", "flushing_main"
    ],
    "A": [
        "fulton", "chambers_ac", "canal_ace", "spring_ce", "west_4th",
        "14th_l_6th", "23rd_ce", "34th_penn_ace", "42nd_port_auth", "50th_ce",
        "59th_columbus", "125th_abc", "145th_acd", "155th_ac", "168th_ac",
        "175th", "181st_a", "190th", "dyckman_a", "inwood_207"
    ],
    "C": [
        "fulton", "chambers_ac", "canal_ace", "spring_ce", "west_4th",
        "14th_l_6th", "23rd_ce", "34th_penn_ace", "42nd_port_auth", "50th_ce",
        "59th_columbus", "72nd_bc", "81st_museum", "86th_bc", "96th_bc",
        "103rd_bc", "110th_bc", "116th_bc", "125th_abc", "135th_bc",
        "145th_acd", "155th_ac", "168th_ac"
    ],
    "E": [
        "world_trade", "canal_ace", "spring_ce", "west_4th", "14th_l_6th",
        "23rd_ce", "34th_penn_ace", "42nd_port_auth", "50th_ce", "53rd_lex",
        "5th_53rd", "queens_plaza", "court_sq_em", "jackson_hts", "forest_hills",
        "kew_gardens", "briarwood", "sutphin_archer", "jamaica_center"
    ],
    "B": [
        "brighton_beach", "atlantic_barclays", "dekalb_av", "broadway_lafayette",
        "west_4th", "34th_herald", "42nd_bryant", "47_50_rock", "59th_columbus",
        "72nd_bc", "81st_museum", "86th_bc", "96th_bc", "103rd_bc", "110th_bc",
        "116th_bc", "125th_abc", "135th_bc", "145th_acd", "155th_bd",
        "yankee_stadium", "tremont_bd", "182nd_183rd", "fordham_bd",
        "kingsbridge_bd", "bedford_park_bd"
    ],
    "D": [
        "coney_island", "atlantic_barclays", "dekalb_av", "broadway_lafayette",
        "west_4th", "34th_herald", "42nd_bryant", "47_50_rock", "59th_columbus",
        "125th_abc", "145th_acd", "155th_bd", "yankee_stadium", "tremont_bd",
        "182nd_183rd", "fordham_bd", "kingsbridge_bd", "bedford_park_bd", "norwood_205"
    ],
    "F": [
        "coney_island", "church_ave_fg", "15th_prospect", "7th_av_fg", "bergen_fg",
        "jay_st", "broadway_lafayette", "west_4th", "14th_fm", "23rd_fm",
        "34th_herald", "42nd_bryant", "47_50_rock", "57th_f", "53rd_lex",
        "queens_plaza", "jackson_hts", "forest_hills", "kew_gardens", "briarwood",
        "parsons_blvd", "sutphin_blvd", "jamaica_179"
    ],
    "G": [
        "court_sq_g", "greenpoint_av", "nassau_g", "metropolitan_g", "broadway_g",
        "lorimer_g", "bedford_nostrand", "classon_av", "clinton_wash", "fulton_g",
        "hoyt_schermerhorn", "bergen_fg", "7th_av_fg", "15th_prospect", "church_ave_fg"
    ],
    "L": [
        "8th_av_l", "6th_av_l", "union_sq", "3rd_av_l", "1st_av_l", "bedford_l",
        "lorimer_l", "graham_l", "grand_l", "montrose_l", "jefferson_l", "myrtle_wyckoff"
    ],
    "N": [
        "coney_island", "atlantic_barclays", "dekalb_av", "canal_nqrw", "prince",
        "8th_nyu", "union_sq", "23rd_nrw", "28th_nrw", "34th_herald",
        "42nd_times_sq", "49th", "57th_nqrw", "59th_nqrw", "queensboro_plaza",
        "astoria_ditmars"
    ],
    "Q": [
        "coney_island", "kings_hwy_bq", "atlantic_barclays", "dekalb_av",
        "canal_nqrw", "prince", "8th_nyu", "union_sq", "23rd_nrw", "28th_nrw",
        "34th_herald", "42nd_times_sq", "57th_nqrw", "72nd_q", "86th_q", "96th_q"
    ],
    "R": [
        "bay_ridge", "atlantic_barclays", "dekalb_av", "jay_st", "court_st",
        "whitehall", "city_hall", "canal_nqrw", "prince", "8th_nyu", "union_sq",
        "23rd_nrw", "28th_nrw", "34th_herald", "42nd_times_sq", "49th",
        "57th_nqrw", "59th_nqrw", "queensboro_plaza", "queens_plaza",
        "steinway", "46th_st", "northern_blvd", "65th_st", "jackson_hts",
        "elmhurst_av", "woodhaven_blvd", "63rd_drive", "67th_av", "forest_hills"
    ],
    "W": [
        "whitehall", "city_hall", "canal_nqrw", "prince", "8th_nyu", "union_sq",
        "23rd_nrw", "28th_nrw", "34th_herald", "42nd_times_sq", "49th",
        "57th_nqrw", "59th_nqrw", "queensboro_plaza", "39th_av", "36th_av",
        "broadway_nw", "30th_av", "astoria_blvd", "astoria_ditmars"
    ],
    "J": [
        "jamaica_center", "sutphin_archer", "marcy_av", "hewes", "lorimer_jm",
        "flushing_jm", "broadway_g", "canal_jz", "chambers_123", "fulton"
    ],
    "M": [
        "myrtle_wyckoff", "flushing_jm", "lorimer_jm", "marcy_av", "hewes",
        "broadway_lafayette", "west_4th", "14th_fm", "23rd_fm", "34th_herald",
        "42nd_bryant", "47_50_rock", "53rd_lex", "5th_53rd", "queens_plaza",
        "steinway", "46th_st", "northern_blvd", "65th_st", "jackson_hts",
        "elmhurst_av", "woodhaven_blvd", "63rd_drive", "67th_av", "forest_hills"
    ],
}


class SubwayGraph:
    """Graph representation of the NYC subway system."""

    def __init__(self):
        self.adjacency: dict[str, list[tuple[str, str, int]]] = {}  # station_id -> [(neighbor_id, line, time)]
        self.gtfs_parser = None
        try:
            self.gtfs_parser = get_gtfs_parser()
            if self.gtfs_parser:
                print("Using GTFS static data for travel times")
            else:
                print("Warning: Could not load GTFS data, using estimates")
        except Exception as e:
            print(f"Warning: Could not load GTFS data, using estimates: {e}")
        self._build_graph()

    def _build_graph(self):
        """Build adjacency list from line sequences."""
        for line, stations in LINE_SEQUENCES.items():
            for i in range(len(stations) - 1):
                from_id = stations[i]
                to_id = stations[i + 1]

                if from_id not in STATIONS or to_id not in STATIONS:
                    continue

                # Add both directions
                self._add_edge(from_id, to_id, line)
                self._add_edge(to_id, from_id, line)

        # Add transfer edges
        self._add_transfers()

    def _add_edge(self, from_id: str, to_id: str, line: str, time: Optional[int] = None):
        """Add an edge to the graph with travel time from GTFS or estimate."""
        if from_id not in self.adjacency:
            self.adjacency[from_id] = []
        
        # Try to get real travel time from GTFS
        if time is None:
            if self.gtfs_parser and from_id in STATIONS and to_id in STATIONS:
                from_station = STATIONS[from_id]
                to_station = STATIONS[to_id]
                
                # Try to get travel time for this specific route
                travel_minutes = self.gtfs_parser.get_travel_time_minutes(
                    from_station.gtfs_stop_id,
                    to_station.gtfs_stop_id,
                    route_id=line
                )
                
                if travel_minutes is not None:
                    time = travel_minutes
                else:
                    # Fallback to estimate
                    time = AVG_TIME_BETWEEN_STOPS
            else:
                time = AVG_TIME_BETWEEN_STOPS
        
        self.adjacency[from_id].append((to_id, line, time))

    def _add_transfers(self):
        """Add transfer edges between lines at transfer stations."""
        for station_id, lines in TRANSFER_STATIONS.items():
            if station_id not in STATIONS:
                continue

            # Add zero-cost edges for staying at same station on different lines
            # This is handled implicitly by the pathfinding algorithm

    def find_route(self, from_station_id: str, to_station_id: str) -> Optional[Route]:
        """Find the best route between two stations using modified Dijkstra."""
        if from_station_id not in self.adjacency or to_station_id not in self.adjacency:
            return None

        # Priority queue: (total_time, transfers, current_station, current_line, path)
        # path is list of (station_id, line)
        start_station = STATIONS.get(from_station_id)
        if not start_station:
            return None

        # Start with all possible lines at the origin
        pq = []
        for line in start_station.lines:
            heapq.heappush(pq, (0, 0, from_station_id, line, [(from_station_id, line)]))

        visited = set()

        while pq:
            time, transfers, current, current_line, path = heapq.heappop(pq)

            if current == to_station_id:
                return self._build_route(path)

            state = (current, current_line)
            if state in visited:
                continue
            visited.add(state)

            for neighbor, edge_line, edge_time in self.adjacency.get(current, []):
                # Calculate cost
                new_time = time + edge_time
                new_transfers = transfers

                # Penalty for changing lines
                if edge_line != current_line:
                    new_time += TRANSFER_TIME
                    new_transfers += 1

                new_state = (neighbor, edge_line)
                if new_state not in visited:
                    new_path = path + [(neighbor, edge_line)]
                    heapq.heappush(pq, (new_time, new_transfers, neighbor, edge_line, new_path))

        return None

    def _build_route(self, path: list[tuple[str, str]]) -> Route:
        """Convert path to Route object with segments using real GTFS travel times."""
        if not path:
            return None

        segments = []
        current_line = path[0][1]
        segment_start = 0

        for i in range(1, len(path)):
            station_id, line = path[i]
            if line != current_line:
                # End current segment
                segment_stations = [STATIONS[path[j][0]] for j in range(segment_start, i)]
                if len(segment_stations) > 1:
                    # Calculate total travel time for this segment using GTFS or estimates
                    travel_time = self._calculate_segment_time(segment_stations, current_line)
                    segments.append(RouteSegment(
                        line=current_line,
                        from_station=segment_stations[0],
                        to_station=segment_stations[-1],
                        stops=segment_stations,
                        travel_time_minutes=travel_time
                    ))
                segment_start = i - 1  # Include transfer station
                current_line = line

        # Add final segment
        segment_stations = [STATIONS[path[j][0]] for j in range(segment_start, len(path))]
        if len(segment_stations) > 1:
            travel_time = self._calculate_segment_time(segment_stations, current_line)
            segments.append(RouteSegment(
                line=current_line,
                from_station=segment_stations[0],
                to_station=segment_stations[-1],
                stops=segment_stations,
                travel_time_minutes=travel_time
            ))

        total_time = sum(seg.travel_time_minutes for seg in segments)
        total_time += (len(segments) - 1) * TRANSFER_TIME  # Transfer time
        transfer_count = len(segments) - 1

        return Route(
            segments=segments,
            total_time_minutes=total_time,
            transfer_count=transfer_count
        )

    def _calculate_segment_time(self, stations: list[Station], line: str) -> int:
        """Calculate total travel time for a segment using GTFS data or estimates.
        
        Args:
            stations: List of stations in order
            line: Route line ID
            
        Returns:
            Total travel time in minutes
        """
        if len(stations) < 2:
            return 0
        
        if self.gtfs_parser:
            # Sum up travel times between consecutive stations using GTFS data
            total_seconds = 0
            for i in range(len(stations) - 1):
                from_station = stations[i]
                to_station = stations[i + 1]
                
                travel_seconds = self.gtfs_parser.get_travel_time(
                    from_station.gtfs_stop_id,
                    to_station.gtfs_stop_id,
                    route_id=line
                )
                
                if travel_seconds is not None:
                    total_seconds += travel_seconds
                else:
                    # Fallback to estimate for this segment
                    total_seconds += AVG_TIME_BETWEEN_STOPS * 60
            
            return round(total_seconds / 60)
        else:
            # Fallback to estimate
            return (len(stations) - 1) * AVG_TIME_BETWEEN_STOPS

    def get_travel_time_on_line(
        self, from_station_id: str, to_station_id: str, line: str
    ) -> Optional[int]:
        """Travel time in minutes from A to B staying on one line. Returns None if no path on that line."""
        if from_station_id == to_station_id:
            return 0
        if from_station_id not in self.adjacency or to_station_id not in self.adjacency:
            return None
        # BFS from from_station_id following only edges with this line
        q = deque([(from_station_id, 0)])
        seen = {from_station_id}
        while q:
            current, total_time = q.popleft()
            for neighbor, edge_line, edge_time in self.adjacency.get(current, []):
                if edge_line != line:
                    continue
                if neighbor == to_station_id:
                    return total_time + edge_time
                if neighbor not in seen:
                    seen.add(neighbor)
                    q.append((neighbor, total_time + edge_time))
        return None

    def find_routes(
        self, from_station_id: str, to_station_id: str, max_results: int = 3
    ) -> list[Route]:
        """Find multiple route options."""
        routes = []

        # Get best route
        best = self.find_route(from_station_id, to_station_id)
        if best:
            routes.append(best)

        # Could implement k-shortest paths here for alternatives
        return routes


# Singleton instance
subway_graph = SubwayGraph()


def find_route(from_name: str, to_name: str) -> Optional[Route]:
    """Find a route between two stations by name."""
    from_station = find_station(from_name)
    to_station = find_station(to_name)

    if not from_station:
        return None
    if not to_station:
        return None

    return subway_graph.find_route(from_station.id, to_station.id)


def get_travel_time_on_line(from_station_id: str, to_station_id: str, line: str) -> Optional[int]:
    """Travel time in minutes from A to B on one line. None if no path on that line."""
    return subway_graph.get_travel_time_on_line(from_station_id, to_station_id, line)
