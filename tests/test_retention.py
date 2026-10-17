"""Tests for pruning stale probe history."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from db.base import Base
from db.models import Monitor, ProbeResult
from monitor.retention import prune_old_probe_results


@compiles(BigInteger, "sqlite")
def _compile_bigint_as_integer(element: BigInteger, compiler: object, **kwargs: object) -> str:
    """Use SQLite's rowid-backed INTEGER primary key for local unit tests."""
    return "INTEGER"


def test_prune_old_probe_results_deletes_only_rows_before_cutoff() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 10)

    with Session(engine, expire_on_commit=False) as session:
        session.add(Monitor(id=1, name="retention-test", url="https://8.8.8.8"))
        session.flush()
        session.add_all(
            [
                ProbeResult(
                    monitor_id=1,
                    probed_at=now - timedelta(days=31),
                    is_up=True,
                ),
                ProbeResult(
                    monitor_id=1,
                    probed_at=now - timedelta(days=30),
                    is_up=True,
                ),
            ]
        )
        session.commit()

        deleted = prune_old_probe_results(session, retention_days=30, now=now)
        remaining = session.scalars(select(ProbeResult)).all()

    assert deleted == 1
    assert len(remaining) == 1
    assert remaining[0].probed_at == now - timedelta(days=30)


def test_prune_old_probe_results_rejects_negative_retention() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session, pytest.raises(ValueError, match="non-negative"):
        prune_old_probe_results(session, retention_days=-1)
