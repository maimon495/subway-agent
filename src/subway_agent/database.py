"""SQLite database for user preferences and memory."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import DB_PATH

Base = declarative_base()


class UserPreference(Base):
    """User preferences table."""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), default="default")
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class TripHistory(Base):
    """Trip history for learning common routes."""
    __tablename__ = "trip_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), default="default")
    from_station = Column(String(100), nullable=False)
    to_station = Column(String(100), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class ConversationMemory(Base):
    """Conversation context memory."""
    __tablename__ = "conversation_memory"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), default="default")
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Database:
    """Database manager for the subway agent."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def set_preference(self, key: str, value: str, user_id: str = "default"):
        """Set a user preference."""
        session = self.Session()
        try:
            pref = session.query(UserPreference).filter_by(
                user_id=user_id, key=key
            ).first()

            if pref:
                pref.value = value
                pref.updated_at = datetime.utcnow()
            else:
                pref = UserPreference(user_id=user_id, key=key, value=value)
                session.add(pref)

            session.commit()
        finally:
            session.close()

    def get_preference(self, key: str, user_id: str = "default") -> Optional[str]:
        """Get a user preference."""
        session = self.Session()
        try:
            pref = session.query(UserPreference).filter_by(
                user_id=user_id, key=key
            ).first()
            return pref.value if pref else None
        finally:
            session.close()

    def get_all_preferences(self, user_id: str = "default") -> dict[str, str]:
        """Get all user preferences."""
        session = self.Session()
        try:
            prefs = session.query(UserPreference).filter_by(user_id=user_id).all()
            return {p.key: p.value for p in prefs}
        finally:
            session.close()

    def add_trip(self, from_station: str, to_station: str, user_id: str = "default"):
        """Record a trip in history."""
        session = self.Session()
        try:
            trip = TripHistory(
                user_id=user_id,
                from_station=from_station,
                to_station=to_station
            )
            session.add(trip)
            session.commit()
        finally:
            session.close()

    def get_common_trips(self, user_id: str = "default", limit: int = 5) -> list[tuple[str, str, int]]:
        """Get most common trips for a user."""
        session = self.Session()
        try:
            from sqlalchemy import func
            results = session.query(
                TripHistory.from_station,
                TripHistory.to_station,
                func.count().label("count")
            ).filter_by(user_id=user_id).group_by(
                TripHistory.from_station, TripHistory.to_station
            ).order_by(func.count().desc()).limit(limit).all()

            return [(r[0], r[1], r[2]) for r in results]
        finally:
            session.close()

    def add_message(self, role: str, content: str, user_id: str = "default"):
        """Add a message to conversation history."""
        session = self.Session()
        try:
            msg = ConversationMemory(user_id=user_id, role=role, content=content)
            session.add(msg)
            session.commit()
        finally:
            session.close()

    def get_recent_messages(self, user_id: str = "default", limit: int = 10) -> list[dict]:
        """Get recent conversation messages."""
        session = self.Session()
        try:
            messages = session.query(ConversationMemory).filter_by(
                user_id=user_id
            ).order_by(ConversationMemory.timestamp.desc()).limit(limit).all()

            return [{"role": m.role, "content": m.content} for m in reversed(messages)]
        finally:
            session.close()

    def clear_conversation(self, user_id: str = "default"):
        """Clear conversation history."""
        session = self.Session()
        try:
            session.query(ConversationMemory).filter_by(user_id=user_id).delete()
            session.commit()
        finally:
            session.close()


# Singleton instance
db = Database()
