"""Retention job for pruning stale probe history."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from db.models import ProbeResult
from db.session import create_database_engine, create_session_factory
from monitor.settings import Settings


def prune_old_probe_results(
    session: Session,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> int:
    """Delete probe results older than the configured retention window."""
    if retention_days < 0:
        raise ValueError("retention_days must be non-negative")

    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    deleted = session.execute(delete(ProbeResult).where(ProbeResult.probed_at < cutoff))
    session.commit()
    return int(deleted.rowcount or 0)


def main() -> int:
    """Load settings and delete expired probe rows."""
    settings = Settings()
    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            prune_old_probe_results(session, retention_days=settings.retention_days)
    except Exception:
        logging.exception("retention cleanup failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
