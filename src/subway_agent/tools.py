"""LangGraph tools for the subway agent."""

from typing import Optional
from langchain_core.tools import tool

from .stations import find_station, find_stations_by_line, STATIONS
from .mta_feed import get_arrivals
from .routing import find_route, subway_graph, get_travel_time_on_line
from .database import db
from .gtfs_static import get_gtfs_parser

# Express lines (faster; fewer stops). Same corridor locals: 1=local with 2,3; 6=local with 4,5; C=local with A; etc.
EXPRESS_LINES = {"2", "3", "4", "5", "A", "D", "N", "Q"}


def _line_label(line: str) -> str:
    """Return '(express)' or '(local)' for known lines."""
    if line in EXPRESS_LINES:
        return " (express)"
    return " (local)"


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
        label = _line_label(seg.line)
        result.append(f"{i}. Take the {seg.line} train{label} from {seg.from_station.name} to {seg.to_station.name} ({stops_text})")

    result.append(f"\nTotal travel time: ~{route.total_time_minutes} minutes")
    if route.transfer_count > 0:
        result.append(f"Transfers: {route.transfer_count}")

    return "\n".join(result)


@tool
def get_route_with_arrivals(from_station: str, to_station: str) -> str:
    """Get the best route between two stations PLUS real-time next train arrivals at the origin.

    Use this when the user asks for the fastest way 'right now', 'at the moment', or when
    they want to know when the next train is coming. This combines route info with live
    MTA arrival data so you can say e.g. 'Take the 4 train (~15 min). Next 4 train in 3 min.'

    Args:
        from_station: The starting station name (e.g., "Union Square", "Penn Station")
        to_station: The destination station name

    Returns:
        Route description plus real-time next train times at the origin for the recommended line(s)
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

    db.add_trip(from_st.id, to_st.id)

    # Build route text
    result = [f"Route from {from_st.name} to {to_st.name}:\n"]
    for i, seg in enumerate(route.segments, 1):
        stops_text = f"{len(seg.stops)-1} stops" if len(seg.stops) > 2 else "1 stop"
        label = _line_label(seg.line)
        result.append(f"{i}. Take the {seg.line} train{label} from {seg.from_station.name} to {seg.to_station.name} ({stops_text})")
    result.append(f"\nTotal travel time: ~{route.total_time_minutes} minutes")
    if route.transfer_count > 0:
        result.append(f"Transfers: {route.transfer_count}")
    # Single recommended first step so the agent doesn't say "4 or 6" when the best route is one of them
    first_line = route.segments[0].line
    result.append(f"\nRecommended: Take the {first_line} train first (this is the fastest option).")

    # Get real-time arrivals at origin for the line(s) on the first segment
    first_seg = route.segments[0]
    lines_needed = [first_seg.line]
    # Infer direction: northbound if destination is north of origin (higher latitude)
    going_north = first_seg.to_station.latitude > first_seg.from_station.latitude
    want_direction = "N" if going_north else "S"

    arrivals = get_arrivals(from_st.id, lines_needed)
    # Filter to the direction the user is traveling
    relevant = [a for a in arrivals if a.direction == want_direction]
    if not relevant:
        relevant = arrivals[:6]  # fallback: show any direction

    if relevant:
        result.append("\nReal-time next trains at " + from_st.name + ":")
        dir_label = "Uptown/Bronx" if want_direction == "N" else "Downtown/Brooklyn"
        for arr in relevant[:5]:
            result.append(f"  {arr.line} train ({dir_label}): {arr.minutes_until} min")
    else:
        result.append("\nReal-time arrivals: MTA feed unavailable. Check signs at the station for next train times.")

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


TRANSFER_BUFFER_MIN = 1


@tool
def compare_local_vs_express(
    from_station: str,
    to_station: str,
    transfer_station: str,
    local_line: str,
    express_lines: str,
) -> str:
    """Compare staying on a local train vs transferring to an express, using real-time arrivals. Works for any route (e.g. South Ferry→Penn 1 vs 2/3 at Chambers; 14th St→96th St 6 vs 4/5 at 14th).

    Args:
        from_station: Origin (e.g. "South Ferry", "14th St")
        to_station: Destination (e.g. "Penn Station", "96th St")
        transfer_station: Where to transfer, or same as from_station if comparing trains at one station (e.g. "Chambers St", "14th St")
        local_line: Local/slower line (e.g. "1", "6")
        express_lines: Comma-separated express lines (e.g. "2,3", "4,5")

    Returns:
        Next local departure, Option 1 (stay on local) total min, Option 2 (transfer to express) total min, wait at transfer, recommendation.
    """
    from_st = find_station(from_station)
    to_st = find_station(to_station)
    xfer_st = find_station(transfer_station)
    if not from_st or not to_st or not xfer_st:
        return f"Could not find station(s). Check: from={from_station}, to={to_station}, transfer={transfer_station}."

    express_list = [s.strip().upper() for s in express_lines.split(",")]
    going_north = to_st.latitude > from_st.latitude
    want_direction = "N" if going_north else "S"

    time_origin_to_xfer_local = get_travel_time_on_line(from_st.id, xfer_st.id, local_line)
    time_origin_to_dest_local = get_travel_time_on_line(from_st.id, to_st.id, local_line)
    if time_origin_to_dest_local is None:
        return f"No path on {local_line} from {from_st.name} to {to_st.name}. Check station names and line."
    if from_st.id != xfer_st.id and (time_origin_to_xfer_local is None or time_origin_to_xfer_local <= 0):
        return f"No path on {local_line} from {from_st.name} to {transfer_station}. Check station names."

    time_xfer_to_dest_express = None
    for ex in express_list:
        t = get_travel_time_on_line(xfer_st.id, to_st.id, ex)
        if t is not None:
            time_xfer_to_dest_express = t
            break
    if time_xfer_to_dest_express is None:
        return f"No path on express {express_lines} from {transfer_station} to {to_st.name}. Check station names."

    local_arrivals = get_arrivals(from_st.id, [local_line])
    local_same_dir = [a for a in local_arrivals if a.direction == want_direction]
    if not local_same_dir:
        return f"No upcoming {local_line} train ({'Uptown' if want_direction == 'N' else 'Downtown'}) at {from_st.name}. MTA feed may be unavailable."
    next_local = local_same_dir[0]
    depart_wait = next_local.minutes_until

    direct_total = depart_wait + time_origin_to_dest_local

    same_station = from_st.id == xfer_st.id
    if same_station:
        xfer_arrivals = get_arrivals(xfer_st.id, express_list)
        xfer_same_dir = [a for a in xfer_arrivals if a.direction == want_direction]
        catchable = xfer_same_dir[:1] if xfer_same_dir else []
        arrive_at_xfer = depart_wait
        min_connection = depart_wait + TRANSFER_BUFFER_MIN
    else:
        arrive_at_xfer = depart_wait + (time_origin_to_xfer_local or 0)
        min_connection = arrive_at_xfer + TRANSFER_BUFFER_MIN
        xfer_arrivals = get_arrivals(xfer_st.id, express_list)
        xfer_same_dir = [a for a in xfer_arrivals if a.direction == want_direction]
        catchable = [a for a in xfer_same_dir if a.minutes_until >= min_connection]

    if not catchable:
        result = [
            f"Next {local_line} train at {from_st.name}: {depart_wait} min",
            "",
            f"Option 1 (Stay on {local_line}): arrive at {to_st.name} in {direct_total} min",
            f"Option 2 (Transfer to {express_lines} at {transfer_station}): no {express_lines} train you can catch in time.",
            "",
            f"Recommendation: Stay on the {local_line}.",
        ]
        return "\n".join(result)

    next_express = catchable[0]
    express_depart_min = next_express.minutes_until
    transfer_total = express_depart_min + time_xfer_to_dest_express
    wait_at_xfer = max(0, express_depart_min - arrive_at_xfer - (0 if same_station else TRANSFER_BUFFER_MIN))

    result = [
        f"Next {local_line} train at {from_st.name}: {depart_wait} min",
        "",
        f"Option 1 (Stay on {local_line}): arrive at {to_st.name} in {direct_total} min",
        f"Option 2 (Transfer to {next_express.line} at {transfer_station}): arrive at {to_st.name} in {transfer_total} min",
        f"  If you transfer: next {express_lines} you can catch in {express_depart_min} min; wait at {transfer_station}: {wait_at_xfer} min.",
        "",
    ]
    if direct_total <= transfer_total:
        result.append(f"Recommendation: Stay on the {local_line} (saves {transfer_total - direct_total} min).")
    else:
        result.append(f"Recommendation: Transfer to {express_lines} at {transfer_station} (saves {direct_total - transfer_total} min).")
    return "\n".join(result)


@tool
def plan_trip_with_transfers() -> str:
    """South Ferry to Penn Station: stay on 1 vs transfer to 2/3 at Chambers. Convenience wrapper for compare_local_vs_express.

    USE THIS only for South Ferry → Penn Station (or "South Ferry to Penn" / "South Ferry uptown").
    For other routes (e.g. 14th St → 96th St: 6 vs 4/5), use compare_local_vs_express instead with the right from/to/transfer/local/express.
    """
    return compare_local_vs_express.invoke({
        "from_station": "South Ferry",
        "to_station": "Penn Station",
        "transfer_station": "Chambers St",
        "local_line": "1",
        "express_lines": "2,3",
    })


@tool
def get_transfer_timing(from_station: str, to_station: str) -> str:
    """Get real-time transfer timing: if you take the next train from origin, when do you arrive at the transfer and how long until the next train on the next leg?

    Use this when the user asks about transfer timing in context of a route you already gave, e.g.:
    - 'If I get on the next N train, what is the timing of the transfer?'
    - 'How long do I wait at Times Square?'
    - 'When do I get to the transfer and when is the next 1 train?'

    Args:
        from_station: Origin (e.g. 'Union Square', '14th St')
        to_station: Destination (e.g. 'Lincoln Center', '66th St')

    Returns:
        Next train at origin, travel time to transfer, arrival at transfer, next train you can catch at transfer, wait time, and time to destination.
    """
    from_st = find_station(from_station)
    to_st = find_station(to_station)
    if not from_st or not to_st:
        return f"Could not find station(s). Check: from={from_station}, to={to_station}."

    route = subway_graph.find_route(from_st.id, to_st.id)
    if not route:
        return f"Could not find a route from {from_st.name} to {to_st.name}."

    if route.transfer_count == 0:
        travel = get_travel_time_on_line(from_st.id, to_st.id, route.segments[0].line)
        arrivals = get_arrivals(from_st.id, [route.segments[0].line])
        going_north = to_st.latitude > from_st.latitude
        want_direction = "N" if going_north else "S"
        relevant = [a for a in arrivals if a.direction == want_direction]
        if not relevant:
            return f"No transfer on this route (direct {route.segments[0].line}). Next {route.segments[0].line} at {from_st.name}: MTA feed unavailable."
        next_min = relevant[0].minutes_until
        return f"No transfer. Direct {route.segments[0].line} from {from_st.name} to {to_st.name}. Next {route.segments[0].line} in {next_min} min; travel ~{travel or 0} min. Total ~{next_min + (travel or 0)} min."

    seg1, seg2 = route.segments[0], route.segments[1]
    xfer_st = seg1.to_station
    first_line, second_line = seg1.line, seg2.line
    going_north = to_st.latitude > from_st.latitude
    want_direction = "N" if going_north else "S"

    arrivals1 = get_arrivals(from_st.id, [first_line])
    relevant1 = [a for a in arrivals1 if a.direction == want_direction]
    if not relevant1:
        return f"No upcoming {first_line} train at {from_st.name}. MTA feed may be unavailable."

    next_depart_min = relevant1[0].minutes_until
    travel_to_xfer = get_travel_time_on_line(from_st.id, xfer_st.id, first_line)
    if travel_to_xfer is None:
        travel_to_xfer = 0
    arrive_at_xfer_min = next_depart_min + travel_to_xfer
    min_connection = arrive_at_xfer_min + TRANSFER_BUFFER_MIN

    arrivals2 = get_arrivals(xfer_st.id, [second_line])
    relevant2 = [a for a in arrivals2 if a.direction == want_direction]
    catchable = [a for a in relevant2 if a.minutes_until >= min_connection]
    if not catchable:
        result = [
            f"Next {first_line} at {from_st.name}: {next_depart_min} min.",
            f"Travel to {xfer_st.name}: ~{travel_to_xfer} min. You arrive at the transfer ~{arrive_at_xfer_min} min from now.",
            f"No {second_line} train you can catch in time at {xfer_st.name}. Next {second_line} times: " + ", ".join(f"{a.minutes_until} min" for a in relevant2[:3]) if relevant2 else "MTA feed unavailable.",
        ]
        return "\n".join(result)

    next_second = catchable[0]
    wait_at_xfer = max(0, next_second.minutes_until - arrive_at_xfer_min)
    travel_leg2 = get_travel_time_on_line(xfer_st.id, to_st.id, second_line) or 0
    total_from_now = next_second.minutes_until + travel_leg2

    result = [
        f"Next {first_line} at {from_st.name}: {next_depart_min} min.",
        f"Travel to {xfer_st.name}: ~{travel_to_xfer} min. You arrive at the transfer ~{arrive_at_xfer_min} min from now.",
        f"Next {second_line} you can catch at {xfer_st.name}: in {next_second.minutes_until} min (wait ~{wait_at_xfer} min at transfer).",
        f"Then ~{travel_leg2} min to {to_st.name}. Total to destination: ~{total_from_now} min from now.",
    ]
    return "\n".join(result)


# List of all tools for the agent
ALL_TOOLS = [
    get_route,
    get_route_with_arrivals,
    get_train_arrivals,
    get_station_info,
    find_stations_on_line,
    save_preference,
    get_preference,
    get_common_trips,
    compare_local_vs_express,
    plan_trip_with_transfers,
    get_transfer_timing,
]
