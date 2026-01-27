"""LangGraph tools for the subway agent."""

from typing import Optional
from langchain_core.tools import tool

from .stations import find_station, find_stations_by_line, STATIONS
from .mta_feed import get_arrivals
from .routing import find_route, subway_graph
from .database import db


@tool
def get_route(from_station: str, to_station: str) -> str:
    """Find the best subway route between two stations.

    Args:
        from_station: The starting station name (e.g., "Times Square", "South Ferry")
        to_station: The destination station name

    Returns:
        A description of the best route with transfers and timing
    """
    from_st = find_station(from_station)
    to_st = find_station(to_station)

    if not from_st:
        return f"Could not find station: {from_station}. Try being more specific."
    if not to_st:
        return f"Could not find station: {to_station}. Try being more specific."

    route = subway_graph.find_route(from_st.id, to_st.id)

    if not route:
        return f"Could not find a route from {from_st.name} to {to_st.name}."

    # Record the trip
    db.add_trip(from_st.id, to_st.id)

    result = [f"Route from {from_st.name} to {to_st.name}:\n"]
    for i, seg in enumerate(route.segments, 1):
        stops_text = f"{len(seg.stops)-1} stops" if len(seg.stops) > 2 else "1 stop"
        result.append(f"{i}. Take the {seg.line} train from {seg.from_station.name} to {seg.to_station.name} ({stops_text})")

    result.append(f"\nTotal travel time: ~{route.total_time_minutes} minutes")
    if route.transfer_count > 0:
        result.append(f"Transfers: {route.transfer_count}")

    return "\n".join(result)


@tool
def get_train_arrivals(station_name: str, line: Optional[str] = None) -> str:
    """Get real-time train arrivals for a station.

    Args:
        station_name: The station name to check arrivals for
        line: Optional specific subway line to filter (e.g., "1", "A", "N")

    Returns:
        List of upcoming train arrivals with times
    """
    station = find_station(station_name)
    if not station:
        return f"Could not find station: {station_name}. Try being more specific."

    lines = [line] if line else None
    arrivals = get_arrivals(station.id, lines)

    if not arrivals:
        lines_text = f" for the {line} train" if line else ""
        return f"No upcoming arrivals{lines_text} at {station.name}. The MTA feed may be temporarily unavailable."

    result = [f"Upcoming arrivals at {station.name}:\n"]
    for arr in arrivals[:8]:  # Limit to 8 arrivals
        direction = "Uptown/Bronx" if arr.direction == "N" else "Downtown/Brooklyn"
        result.append(f"  {arr.line} train ({direction}): {arr.minutes_until} min")

    return "\n".join(result)


@tool
def get_station_info(station_name: str) -> str:
    """Get information about a subway station including lines served.

    Args:
        station_name: The station name to look up

    Returns:
        Station information including lines and location
    """
    station = find_station(station_name)
    if not station:
        return f"Could not find station: {station_name}. Try being more specific."

    lines = ", ".join(station.lines)
    return f"{station.name}\nBorough: {station.borough}\nLines: {lines}"


@tool
def find_stations_on_line(line: str) -> str:
    """Find all stations on a specific subway line.

    Args:
        line: The subway line (e.g., "1", "A", "L", "7")

    Returns:
        List of stations on that line
    """
    line = line.upper()
    stations = find_stations_by_line(line)

    if not stations:
        return f"No stations found for line {line}. Valid lines include: 1,2,3,4,5,6,7,A,C,E,B,D,F,M,G,J,Z,L,N,Q,R,W,S"

    result = [f"Stations on the {line} line ({len(stations)} stations):\n"]
    for station in stations[:20]:  # Limit output
        result.append(f"  - {station.name}")

    if len(stations) > 20:
        result.append(f"  ... and {len(stations) - 20} more")

    return "\n".join(result)


@tool
def save_preference(key: str, value: str) -> str:
    """Save a user preference for future reference.

    Args:
        key: The preference name (e.g., "home_station", "work_station", "preferred_line")
        value: The preference value

    Returns:
        Confirmation message
    """
    db.set_preference(key, value)
    return f"Saved preference: {key} = {value}"


@tool
def get_preference(key: str) -> str:
    """Get a saved user preference.

    Args:
        key: The preference name to retrieve

    Returns:
        The saved preference value or a message if not found
    """
    value = db.get_preference(key)
    if value:
        return f"{key}: {value}"
    return f"No preference saved for '{key}'"


@tool
def get_common_trips() -> str:
    """Get the user's most common trips based on history.

    Returns:
        List of frequently traveled routes
    """
    trips = db.get_common_trips()

    if not trips:
        return "No trip history yet. Start asking for routes to build up history!"

    result = ["Your most common trips:\n"]
    for from_id, to_id, count in trips:
        from_station = STATIONS.get(from_id)
        to_station = STATIONS.get(to_id)
        if from_station and to_station:
            result.append(f"  - {from_station.name} → {to_station.name} ({count} times)")

    return "\n".join(result)


@tool
def plan_trip_with_transfers() -> str:
    """Plan a trip from South Ferry to Penn Station comparing direct vs transfer options.

    Calculates real-time arrival times for:
    - Option 1: Stay on the 1 train the whole way
    - Option 2: Transfer to 2/3 express at Chambers

    Returns formatted comparison with recommendation.
    """
    # Constants
    SOUTH_FERRY_TO_CHAMBERS = 8  # minutes (estimate if MTA data unavailable)
    CHAMBERS_TO_PENN_ON_1 = 6    # minutes local
    CHAMBERS_TO_PENN_ON_EXPRESS = 4  # minutes express (2/3)
    TRANSFER_BUFFER = 2  # minutes to make connection

    # Step 1: Get next 1 train departure from South Ferry
    south_ferry_arrivals = get_arrivals("south_ferry", ["1"])
    northbound_1 = [a for a in south_ferry_arrivals if a.direction == "N"]

    if not northbound_1:
        return "No upcoming northbound 1 trains at South Ferry. MTA feed may be unavailable."

    next_1_train = northbound_1[0]
    depart_time = next_1_train.minutes_until

    # Step 2: Calculate arrival at Chambers
    arrive_at_chambers = depart_time + SOUTH_FERRY_TO_CHAMBERS

    # Step 3: Get 2/3 arrivals at Chambers
    chambers_arrivals = get_arrivals("chambers_123", ["2", "3"])
    northbound_express = [a for a in chambers_arrivals if a.direction == "N"]

    # Step 4: Filter to trains arriving AFTER user reaches Chambers + buffer
    min_connection_time = arrive_at_chambers + TRANSFER_BUFFER
    valid_express = [a for a in northbound_express if a.minutes_until >= min_connection_time]

    # Step 5: Calculate total time for direct option (stay on 1)
    direct_total = depart_time + SOUTH_FERRY_TO_CHAMBERS + CHAMBERS_TO_PENN_ON_1

    # Step 6: Calculate total time for transfer option
    if valid_express:
        next_express = valid_express[0]
        express_depart = next_express.minutes_until
        transfer_total = express_depart + CHAMBERS_TO_PENN_ON_EXPRESS
        transfer_line = next_express.line
        transfer_available = True
    else:
        transfer_total = None
        transfer_line = "2/3"
        transfer_available = False

    # Step 7: Build formatted output
    result = []

    result.append(f"Option 1 (Direct): Take 1 train - arrive in {direct_total} min")

    if transfer_available:
        result.append(f"Option 2 (Transfer): Take 1 to Chambers, transfer to {transfer_line} - arrive in {transfer_total} min")
        result.append("")
        if direct_total <= transfer_total:
            saved = transfer_total - direct_total
            result.append(f"Recommendation: Option 1 - saves {saved} min")
        else:
            saved = direct_total - transfer_total
            result.append(f"Recommendation: Option 2 - saves {saved} min")
    else:
        result.append("Option 2 (Transfer): No 2/3 trains available")
        result.append("")
        result.append("Recommendation: Option 1 - no express available")

    return "\n".join(result)


# List of all tools for the agent
ALL_TOOLS = [
    get_route,
    get_train_arrivals,
    get_station_info,
    find_stations_on_line,
    save_preference,
    get_preference,
    get_common_trips,
    plan_trip_with_transfers,
]
