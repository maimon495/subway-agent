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


# List of all tools for the agent
ALL_TOOLS = [
    get_route,
    get_train_arrivals,
    get_station_info,
    find_stations_on_line,
    save_preference,
    get_preference,
    get_common_trips,
]
