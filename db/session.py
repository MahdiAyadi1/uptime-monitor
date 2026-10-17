"""Database engine and session factory helpers."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_database_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine with stale-connection checks enabled."""
    return create_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create sessions that remain usable after a commit."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
