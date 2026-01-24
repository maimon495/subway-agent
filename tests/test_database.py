"""Tests for database functionality."""

import pytest
import tempfile
from pathlib import Path
from subway_agent.database import Database


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        yield db


def test_set_and_get_preference(test_db):
    """Test saving and retrieving preferences."""
    test_db.set_preference("home_station", "times_square")
    value = test_db.get_preference("home_station")
    assert value == "times_square"


def test_get_missing_preference(test_db):
    """Test getting a preference that doesn't exist."""
    value = test_db.get_preference("nonexistent")
    assert value is None


def test_update_preference(test_db):
    """Test updating an existing preference."""
    test_db.set_preference("work", "old_value")
    test_db.set_preference("work", "new_value")
    value = test_db.get_preference("work")
    assert value == "new_value"


def test_add_trip(test_db):
    """Test adding trip history."""
    test_db.add_trip("times_square", "grand_central")
    test_db.add_trip("times_square", "grand_central")
    trips = test_db.get_common_trips()
    assert len(trips) > 0
    assert trips[0][2] == 2  # Count should be 2


def test_conversation_memory(test_db):
    """Test conversation memory storage."""
    test_db.add_message("user", "Hello")
    test_db.add_message("assistant", "Hi there!")
    messages = test_db.get_recent_messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_clear_conversation(test_db):
    """Test clearing conversation history."""
    test_db.add_message("user", "Test message")
    test_db.clear_conversation()
    messages = test_db.get_recent_messages()
    assert len(messages) == 0
