"""Tests for subway routing functionality."""

import pytest
from subway_agent.routing import find_route, subway_graph
from subway_agent.stations import find_station


def test_find_simple_route():
    """Test finding a simple route on one line."""
    route = find_route("south ferry", "times square")
    assert route is not None
    assert len(route.segments) >= 1
    assert route.total_time_minutes > 0


def test_find_route_with_transfer():
    """Test finding a route that requires transfer."""
    route = find_route("south ferry", "grand central")
    assert route is not None
    assert route.total_time_minutes > 0


def test_route_same_station():
    """Test route to same station returns empty route."""
    from_station = find_station("times square")
    route = subway_graph.find_route(from_station.id, from_station.id)
    # Same station should return route with no segments
    assert route is not None
    assert len(route.segments) == 0


def test_route_has_segments():
    """Test that routes have proper segment structure."""
    route = find_route("union square", "times square")
    assert route is not None
    for segment in route.segments:
        assert segment.line
        assert segment.from_station
        assert segment.to_station
        assert segment.travel_time_minutes >= 0


def test_invalid_station_route():
    """Test route with invalid station returns None."""
    route = find_route("nonexistent station", "times square")
    assert route is None
