"""Tests for incident debounce and transition persistence."""

from datetime import datetime, timedelta

from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from db.base import Base
from db.models import Incident, Monitor, ProbeResult
from monitor.incidents import IncidentTransition, determine_incident_transition, record_probe_result
from monitor.probing import ProbeOutcome


@compiles(BigInteger, "sqlite")
def _compile_bigint_as_integer(element: BigInteger, compiler: object, **kwargs: object) -> str:
    """Use SQLite's rowid-backed INTEGER primary key for local unit tests."""
    return "INTEGER"


def test_transition_opens_only_at_threshold() -> None:
    assert (
        determine_incident_transition(
            is_up=False,
            consecutive_failures=2,
            has_open_incident=False,
            failure_threshold=3,
        )
        is IncidentTransition.NONE
    )
    assert (
        determine_incident_transition(
            is_up=False,
            consecutive_failures=3,
            has_open_incident=False,
            failure_threshold=3,
        )
        is IncidentTransition.OPENED
    )


def test_success_resolves_open_incident_and_does_not_reopen() -> None:
    assert (
        determine_incident_transition(
            is_up=True,
            consecutive_failures=0,
            has_open_incident=True,
            failure_threshold=3,
        )
        is IncidentTransition.RESOLVED
    )
    assert (
        determine_incident_transition(
            is_up=True,
            consecutive_failures=0,
            has_open_incident=False,
            failure_threshold=3,
        )
        is IncidentTransition.NONE
    )


def test_record_probe_result_debounces_and_resolves_incident() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    start = datetime(2026, 1, 1)

    with Session(engine, expire_on_commit=False) as session:
        monitor = Monitor(id=1, name="demo", url="https://8.8.8.8", enabled=True)
        session.add(monitor)
        session.commit()

        failure = ProbeOutcome(False, None, 5, "connection refused")
        transitions = [
            record_probe_result(
                session,
                monitor,
                failure,
                failure_threshold=3,
                probed_at=start + timedelta(minutes=index),
            )
            for index in range(3)
        ]
        session.commit()

        assert transitions == [
            IncidentTransition.NONE,
            IncidentTransition.NONE,
            IncidentTransition.OPENED,
        ]
        incidents = session.scalars(select(Incident)).all()
        assert len(incidents) == 1
        incident = incidents[0]
        assert incident.resolved_at is None
        assert incident.last_error == "connection refused"

        success = ProbeOutcome(True, 200, 4, None)
        transition = record_probe_result(
            session,
            monitor,
            success,
            failure_threshold=3,
            probed_at=start + timedelta(minutes=3),
        )
        session.commit()

        assert transition is IncidentTransition.RESOLVED
        assert incident.resolved_at == start + timedelta(minutes=3)
        assert session.scalar(select(Incident).where(Incident.resolved_at.is_(None))) is None
        assert len(session.scalars(select(ProbeResult)).all()) == 4
