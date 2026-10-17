from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.orm import Session

from db.session import create_database_engine, create_session_factory
from monitor.settings import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


_engine = create_database_engine(get_settings().database_url)
_session_factory = create_session_factory(_engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for each request."""
    db = _session_factory()
    try:
        yield db
    finally:
        db.close()
