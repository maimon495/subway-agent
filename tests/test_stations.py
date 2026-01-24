"""Tests for station lookup functionality."""

import pytest
from subway_agent.stations import find_station, find_stations_by_line, STATIONS


def test_find_station_exact():
    """Test exact station name matching."""
    station = find_station("Times Sq-42nd St")
    assert station is not None
    assert "1" in station.lines or "7" in station.lines


def test_find_station_partial():
    """Test partial station name matching."""
    station = find_station("times square")
    assert station is not None


def test_find_station_south_ferry():
    """Test finding South Ferry station."""
    station = find_station("south ferry")
    assert station is not None
    assert station.name == "South Ferry"
    assert "1" in station.lines


def test_find_station_not_found():
    """Test station not found returns None."""
    station = find_station("nonexistent station xyz")
    assert station is None


def test_find_stations_by_line():
    """Test finding stations on a line."""
    stations = find_stations_by_line("1")
    assert len(stations) > 0
    for station in stations:
        assert "1" in station.lines


def test_stations_have_required_fields():
    """Test all stations have required fields."""
    for station in STATIONS.values():
        assert station.id
        assert station.name
        assert len(station.lines) > 0
        assert station.borough in ["Manhattan", "Brooklyn", "Queens", "Bronx"]
