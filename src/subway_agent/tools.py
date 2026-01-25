"""LangGraph tools for the subway agent."""

from typing import Optional
from langchain_core.tools import tool

from .stations import find_station, find_stations_by_line, STATIONS
from .mta_feed import get_arrivals, get_trip_duration
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


@tool
def plan_trip_with_transfers(from_station: str, to_station: str) -> str:
    """Plan a trip comparing direct and transfer options with real-time data.

    Args:
        from_station: The starting station name
        to_station: The destination station name

    Returns:
        Route options with arrival times and a recommendation
    """
    from_st = find_station(from_station)
    to_st = find_station(to_station)

    if not from_st:
        return f"Could not find station: {from_station}. Try being more specific."
    if not to_st:
        return f"Could not find station: {to_station}. Try being more specific."

    db.add_trip(from_st.id, to_st.id)

    direct_option = None  # (line, time, estimated, est_reason)
    transfer_option = None  # (line1, transfer_station, line2, time, estimated, est_reason)

    # 1. Check for DIRECT route (origin and destination share a line)
    shared_lines = set(from_st.lines) & set(to_st.lines)

    for line in shared_lines:
        if line not in LINE_SEQUENCES:
            continue

        seq = LINE_SEQUENCES[line]
        if from_st.id not in seq or to_st.id not in seq:
            continue

        from_idx = seq.index(from_st.id)
        to_idx = seq.index(to_st.id)
        num_stops = abs(to_idx - from_idx)

        arrivals = get_arrivals(from_st.id, [line])

        if arrivals:
            train = arrivals[0]
            duration = get_trip_duration(from_st.id, to_st.id, train.trip_id)
            if duration is not None:
                total = train.minutes_until + duration
                direct_option = (line, total, False, None)
            else:
                est = num_stops * AVG_TIME_BETWEEN_STOPS
                total = train.minutes_until + est
                direct_option = (line, total, True, f"{line} train duration unavailable")
        else:
            est = num_stops * AVG_TIME_BETWEEN_STOPS
            direct_option = (line, est, True, f"{line} train data unavailable")

        break  # Use first valid direct line

    # 2. Check for TRANSFER route
    route = subway_graph.find_route(from_st.id, to_st.id)

    if route and len(route.segments) >= 2:
        first_seg = route.segments[0]
        second_seg = route.segments[1]
        transfer_station = first_seg.to_station

        arrivals = get_arrivals(from_st.id, [first_seg.line])
        est_reasons = []

        if arrivals:
            train = arrivals[0]

            leg1_dur = get_trip_duration(from_st.id, transfer_station.id, train.trip_id)
            if leg1_dur is None:
                leg1_dur = first_seg.travel_time_minutes
                est_reasons.append(f"{first_seg.line} train duration unavailable")

            arrive_at_transfer = train.minutes_until + leg1_dur

            transfer_arrivals = get_arrivals(transfer_station.id, [second_seg.line])
            connecting = [a for a in transfer_arrivals if a.minutes_until >= arrive_at_transfer + 2]

            if connecting:
                conn = connecting[0]
                leg2_dur = get_trip_duration(transfer_station.id, to_st.id, conn.trip_id)
                if leg2_dur is None:
                    leg2_dur = second_seg.travel_time_minutes
                    est_reasons.append(f"{second_seg.line} train duration unavailable")

                total = conn.minutes_until + leg2_dur
                estimated = len(est_reasons) > 0
                transfer_option = (first_seg.line, transfer_station.name, second_seg.line, total, estimated, ", ".join(est_reasons) if est_reasons else None)
            else:
                total = arrive_at_transfer + 5 + second_seg.travel_time_minutes
                est_reasons.append(f"{second_seg.line} connection time unknown")
                transfer_option = (first_seg.line, transfer_station.name, second_seg.line, total, True, ", ".join(est_reasons))
        else:
            total = route.total_time_minutes
            transfer_option = (first_seg.line, transfer_station.name, second_seg.line, total, True, f"{first_seg.line} train data unavailable")

    # Build output
    result = [f"{from_st.name} to {to_st.name}:\n"]

    if not direct_option and not transfer_option:
        return f"No route options found from {from_st.name} to {to_st.name}."

    # Option 1: Direct (if exists)
    if direct_option:
        line, time, estimated, est_reason = direct_option
        est_label = f" ⚠️ estimated ({est_reason})" if estimated else ""
        result.append(f"Option 1 (Direct): {line} train to {to_st.name} - arrive in {time} min{est_label}")

    # Option 2: Transfer (if exists)
    if transfer_option:
        line1, xfer_station, line2, time, estimated, est_reason = transfer_option
        opt_num = 2 if direct_option else 1
        est_label = f" ⚠️ estimated ({est_reason})" if estimated else ""
        result.append(f"Option {opt_num} (Transfer): {line1} to {xfer_station}, {line2} to {to_st.name} - arrive in {time} min{est_label}")

    # Recommendation
    result.append("")
    if direct_option and transfer_option:
        d_time = direct_option[1]
        t_time = transfer_option[3]
        diff = abs(d_time - t_time)

        if d_time < t_time:
            result.append(f"Recommendation: Take the direct {direct_option[0]} train - saves {diff} min and no transfer risk.")
        elif t_time < d_time:
            result.append(f"Recommendation: Transfer via {transfer_option[1]} - saves {diff} min despite the transfer.")
        else:
            result.append(f"Recommendation: Take the direct {direct_option[0]} train - same time but no transfer risk.")
    elif direct_option:
        result.append(f"Recommendation: Take the {direct_option[0]} train (only option).")
    else:
        result.append(f"Recommendation: Transfer at {transfer_option[1]} (no direct route available).")

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
