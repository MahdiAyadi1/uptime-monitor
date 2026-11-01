"""Tests for due-monitor selection and checker orchestration."""

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import BigInteger, create_engine, select, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base
from db.models import Monitor, ProbeResult
from monitor import checker
from monitor.checker import load_due_monitors, run_checker
from monitor.probing import ProbeOutcome


@compiles(BigInteger, "sqlite")
def _compile_bigint_as_integer(element: BigInteger, compiler: object, **kwargs: object) -> str:
    """Use SQLite's rowid-backed INTEGER primary key for local unit tests."""
    return "INTEGER"


def test_sqlite_migration_creates_auto_increment_ids() -> None:
    project_root = Path(__file__).resolve().parents[1]
    db_path = project_root / ".tmp_sqlite_migration_test.db"
    if db_path.exists():
        db_path.unlink()

    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    try:
        alembic_cfg = Config(str(project_root / "alembic.ini"))
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO monitor (name, url, expected_status, expected_keyword, timeout_seconds, interval_seconds, enabled) "
                    "VALUES (:name, :url, :expected_status, :expected_keyword, :timeout_seconds, :interval_seconds, :enabled)"
                ),
                {
                    "name": "demo-google",
                    "url": "https://www.google.com",
                    "expected_status": 200,
                    "expected_keyword": None,
                    "timeout_seconds": 10,
                    "interval_seconds": 300,
                    "enabled": True,
                },
            )
            row = connection.execute(text("SELECT id, name FROM monitor WHERE name = :name"), {"name": "demo-google"}).first()
            assert row is not None
            assert row[0] is not None
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        if db_path.exists():
            engine.dispose()
            db_path.unlink()


def test_load_due_monitors_respects_interval_and_enabled_flag() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, 12, 0)

    with Session(engine, expire_on_commit=False) as session:
        due = Monitor(id=1, name="due", url="https://8.8.8.8", interval_seconds=60)
        not_due = Monitor(id=2, name="not-due", url="https://1.1.1.1", interval_seconds=300)
        disabled = Monitor(
            id=3,
            name="disabled",
            url="https://9.9.9.9",
            interval_seconds=60,
            enabled=False,
        )
        session.add_all([due, not_due, disabled])
        session.flush()
        session.add_all(
            [
                ProbeResult(
                    monitor_id=1,
                    probed_at=now - timedelta(seconds=60),
                    is_up=True,
                ),
                ProbeResult(
                    monitor_id=2,
                    probed_at=now - timedelta(seconds=30),
                    is_up=True,
                ),
                ProbeResult(
                    monitor_id=3,
                    probed_at=now - timedelta(minutes=5),
                    is_up=True,
                ),
            ]
        )
        session.commit()

        targets = load_due_monitors(session, now=now)

    assert [target.name for target in targets] == ["due"]


def test_load_due_monitors_uses_due_tolerance() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, 12, 0)

    with Session(engine, expire_on_commit=False) as session:
        target = Monitor(id=1, name="within-tolerance", url="https://8.8.8.8", interval_seconds=60)
        session.add(target)
        session.flush()
        session.add(
            ProbeResult(
                monitor_id=1,
                probed_at=now - timedelta(seconds=55),
                is_up=True,
            )
        )
        session.commit()

        targets = load_due_monitors(session, now=now, due_tolerance_seconds=10)

    assert [target.name for target in targets] == ["within-tolerance"]


def test_run_checker_returns_empty_summary_when_no_monitors_are_due() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    summary = asyncio.run(run_checker(session_factory))

    assert summary.probed == 0
    assert summary.up == 0
    assert summary.down == 0


def test_run_checker_probes_due_monitor_and_persists_result(monkeypatch: Any) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime(2026, 1, 1, 12, 0)

    with session_factory() as session:
        session.add(Monitor(id=1, name="checker-test", url="https://8.8.8.8"))
        session.commit()

    client_options: dict[str, Any] = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            client_options.update(kwargs)

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

    async def fake_probe_monitor(
        client: Any,
        target: Any,
        *,
        response_bytes_limit: int,
    ) -> ProbeOutcome:
        return ProbeOutcome(True, 200, 42, None)

    monkeypatch.setattr(checker, "probe_monitor", fake_probe_monitor)
    monkeypatch.setattr(checker.httpx, "AsyncClient", FakeAsyncClient)
    summary = asyncio.run(run_checker(session_factory, now=now))

    with session_factory() as session:
        result = session.scalar(select(ProbeResult))

    assert summary.probed == 1
    assert summary.up == 1
    assert summary.down == 0
    assert result is not None
    assert result.is_up is True
    assert result.http_status == 200
    assert result.latency_ms == 42
    assert client_options["trust_env"] is False
