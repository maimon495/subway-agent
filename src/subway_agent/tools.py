"""LangGraph tools for the subway agent."""

from typing import Optional
from langchain_core.tools import tool

from .stations import find_station, find_stations_by_line, STATIONS
from .mta_feed import get_arrivals
from .routing import find_route, subway_graph, AVG_TIME_BETWEEN_STOPS, LINE_SEQUENCES
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


def _find_direct_line_options(from_st, to_st):
    """Find lines that directly connect origin to destination without transfer."""
    shared_lines = set(from_st.lines) & set(to_st.lines)
    direct_options = []

    for line in shared_lines:
        if line not in LINE_SEQUENCES:
            continue

        sequence = LINE_SEQUENCES[line]
        try:
            from_idx = sequence.index(from_st.id)
            to_idx = sequence.index(to_st.id)
            num_stops = abs(to_idx - from_idx)
            travel_time = num_stops * AVG_TIME_BETWEEN_STOPS
            direct_options.append({
                'line': line,
                'num_stops': num_stops,
                'travel_time': travel_time
            })
        except ValueError:
            # Station not on this line's sequence
            continue

    return direct_options


def _calculate_transfer_route_time(route, from_st):
    """Calculate total end-to-end time for a transfer route using real-time arrivals."""
    cumulative_time = 0
    transfer_buffer = 2

    for i, seg in enumerate(route.segments):
        seg_origin_arrivals = get_arrivals(seg.from_station.id, [seg.line])

        if i == 0:
            # First leg
            if seg_origin_arrivals:
                next_train = seg_origin_arrivals[0]
                cumulative_time = next_train.minutes_until + seg.travel_time_minutes
            else:
                cumulative_time = seg.travel_time_minutes  # Assume immediate departure
        else:
            # Transfer leg
            user_arrives_at = cumulative_time
            min_connection_time = user_arrives_at + transfer_buffer

            connecting_trains = [
                arr for arr in seg_origin_arrivals
                if arr.minutes_until >= min_connection_time
            ]

            if connecting_trains:
                connection = connecting_trains[0]
                cumulative_time = connection.minutes_until + seg.travel_time_minutes
            elif seg_origin_arrivals:
                # Use latest visible train or estimate
                cumulative_time = user_arrives_at + 5 + seg.travel_time_minutes
            else:
                cumulative_time = user_arrives_at + 5 + seg.travel_time_minutes

    return cumulative_time


def _format_direct_route(line, from_st, to_st, next_train_minutes, num_stops, total_time):
    """Format output for a direct (no transfer) route."""
    return (
        f"Take the {line} arriving at {from_st.name} in {next_train_minutes} min.\n"
        f"You'll reach {to_st.name} in about {total_time} min from now "
        f"({num_stops} stops, no transfer needed)."
    )


def _format_transfer_route(route, from_st, to_st):
    """Format output for a transfer route with real-time timing details."""
    result = []
    result.append(f"Trip from {from_st.name} to {to_st.name}:\n")

    cumulative_time = 0
    transfer_buffer = 2

    for i, seg in enumerate(route.segments):
        is_first_leg = (i == 0)
        is_last_leg = (i == len(route.segments) - 1)
        seg_origin_arrivals = get_arrivals(seg.from_station.id, [seg.line])

        if is_first_leg:
            if not seg_origin_arrivals:
                result.append(f"Step {i+1}: Take the {seg.line} from {seg.from_station.name} to {seg.to_station.name}")
                result.append(f"  Warning: No real-time data for {seg.line} at {seg.from_station.name}")
                cumulative_time += seg.travel_time_minutes
            else:
                next_train = seg_origin_arrivals[0]
                board_time = next_train.minutes_until
                arrival_at_transfer = board_time + seg.travel_time_minutes
                cumulative_time = arrival_at_transfer

                result.append(f"Step {i+1}: Take the {seg.line} arriving in {board_time} min")
                result.append(f"  -> You'll reach {seg.to_station.name} in ~{arrival_at_transfer} min from now")
        else:
            user_arrives_at = cumulative_time
            min_connection_time = user_arrives_at + transfer_buffer

            connecting_trains = [
                arr for arr in seg_origin_arrivals
                if arr.minutes_until >= min_connection_time
            ]

            if not seg_origin_arrivals:
                result.append(f"\nStep {i+1}: Transfer to {seg.line} at {seg.from_station.name}")
                result.append(f"  Warning: No real-time data for {seg.line} - can't confirm connection")
                cumulative_time += 5 + seg.travel_time_minutes
            elif not connecting_trains:
                next_available = seg_origin_arrivals[-1]
                result.append(f"\nStep {i+1}: Transfer to {seg.line} at {seg.from_station.name}")
                result.append(f"  Warning: Tight connection! You arrive in ~{user_arrives_at} min")
                result.append(f"  Next {seg.line} visible: {next_available.minutes_until} min")
                cumulative_time += 5 + seg.travel_time_minutes
            else:
                connection = connecting_trains[0]
                wait_time = connection.minutes_until - user_arrives_at
                board_time = connection.minutes_until
                arrival_at_next = board_time + seg.travel_time_minutes
                cumulative_time = arrival_at_next

                result.append(f"\nStep {i+1}: Transfer to {seg.line} at {seg.from_station.name}")
                result.append(f"  You arrive at {seg.from_station.name} in ~{user_arrives_at} min")
                result.append(f"  {seg.line} train arrives in {connection.minutes_until} min - {wait_time} min wait")

                if is_last_leg:
                    result.append(f"  -> You'll reach {seg.to_station.name} in ~{arrival_at_next} min from now")
                else:
                    result.append(f"  -> Reach {seg.to_station.name} in ~{arrival_at_next} min")

                if len(connecting_trains) > 1:
                    backup = connecting_trains[1]
                    result.append(f"  Backup: Next {seg.line} in {backup.minutes_until} min if you miss it")

    result.append(f"\nTotal trip time: ~{cumulative_time} min from now")
    return "\n".join(result)


def _describe_transfer_route(route):
    """Create a short description of a transfer route."""
    if len(route.segments) < 2:
        return f"Take the {route.segments[0].line}"

    first_seg = route.segments[0]
    second_seg = route.segments[1]
    transfer_station = first_seg.to_station.name

    return f"Transfer to {second_seg.line} at {transfer_station}"


@tool
def plan_trip_with_transfers(from_station: str, to_station: str) -> str:
    """Plan a trip with real-time transfer timing. Use this for any route that may involve transfers.

    This tool compares route options when a transfer is involved:
    1. Gets the transfer route from the routing algorithm
    2. Checks if origin and destination share a common line (direct route possible)
    3. Calculates real-time end-to-end time for BOTH options
    4. Returns both options with times, then recommends the faster one

    Args:
        from_station: The starting station name
        to_station: The destination station name

    Returns:
        Both route options with real-time timing, plus a recommendation
    """
    from_st = find_station(from_station)
    to_st = find_station(to_station)

    if not from_st:
        return f"Could not find station: {from_station}. Try being more specific."
    if not to_st:
        return f"Could not find station: {to_station}. Try being more specific."

    # Get the transfer route from subway_graph.find_route
    route = subway_graph.find_route(from_st.id, to_st.id)
    if not route:
        return f"Could not find a route from {from_st.name} to {to_st.name}."

    # Record the trip
    db.add_trip(from_st.id, to_st.id)

    # If no transfers in recommended route, just return it with real-time info
    if len(route.segments) == 1:
        seg = route.segments[0]
        origin_arrivals = get_arrivals(from_st.id, [seg.line])

        if not origin_arrivals:
            return (
                f"Route: Take the {seg.line} from {from_st.name} to {to_st.name} "
                f"({len(seg.stops)-1} stops, ~{seg.travel_time_minutes} min).\n\n"
                f"Real-time data unavailable for the {seg.line} right now."
            )

        next_train = origin_arrivals[0]
        total_time = next_train.minutes_until + seg.travel_time_minutes

        return (
            f"Take the {seg.line} arriving at {from_st.name} in {next_train.minutes_until} min.\n"
            f"You'll reach {to_st.name} in about {total_time} min from now "
            f"({len(seg.stops)-1} stops)."
        )

    # Multi-segment route - check if origin and destination share a common line
    direct_options = _find_direct_line_options(from_st, to_st)

    # Calculate real-time end-to-end time for transfer route
    transfer_total_time = _calculate_transfer_route_time(route, from_st)

    # Calculate real-time end-to-end time for direct options
    best_direct = None
    best_direct_time = float('inf')

    for option in direct_options:
        line = option['line']
        arrivals = get_arrivals(from_st.id, [line])

        if arrivals:
            next_train = arrivals[0]
            total_time = next_train.minutes_until + option['travel_time']

            if total_time < best_direct_time:
                best_direct_time = total_time
                best_direct = {
                    'line': line,
                    'next_train_minutes': next_train.minutes_until,
                    'num_stops': option['num_stops'],
                    'total_time': total_time
                }

    # Build response with both options and recommendation
    result = [f"Route options from {from_st.name} to {to_st.name}:\n"]

    transfer_desc = _describe_transfer_route(route)

    if best_direct:
        # Present both options
        result.append(f"Option A: Stay on {best_direct['line']} - {best_direct['total_time']} min")
        result.append(f"Option B: {transfer_desc} - {transfer_total_time} min")

        # Recommend the faster one
        result.append("")
        if best_direct_time < transfer_total_time:
            result.append(f"Recommendation: Stay on the {best_direct['line']}.")
        elif transfer_total_time < best_direct_time:
            result.append(f"Recommendation: {transfer_desc}.")
        else:
            result.append(f"Recommendation: Either option - same travel time.")
    else:
        # No direct option available, only show transfer route
        result.append(f"Option: {transfer_desc} - {transfer_total_time} min")
        result.append("")
        result.append("(No direct route available between these stations.)")

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
