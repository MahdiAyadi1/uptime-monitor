"""Incident transition rules and persistence helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Incident, Monitor, ProbeResult
from monitor.probing import ProbeOutcome


class IncidentTransition(StrEnum):
    """State transition caused by a probe result."""

    NONE = "none"
    OPENED = "opened"
    RESOLVED = "resolved"


def determine_incident_transition(
    *,
    is_up: bool,
    consecutive_failures: int,
    has_open_incident: bool,
    failure_threshold: int,
) -> IncidentTransition:
    """Return the incident transition for a probe without performing I/O."""
    if failure_threshold < 1:
        raise ValueError("failure_threshold must be at least 1")
    if is_up:
        return IncidentTransition.RESOLVED if has_open_incident else IncidentTransition.NONE
    if not has_open_incident and consecutive_failures >= failure_threshold:
        return IncidentTransition.OPENED
    return IncidentTransition.NONE


def record_probe_result(
    session: Session,
    monitor: Monitor,
    outcome: ProbeOutcome,
    *,
    failure_threshold: int = 3,
    probed_at: datetime | None = None,
) -> IncidentTransition:
    """Persist a probe and update the monitor's incident state atomically."""
    if failure_threshold < 1:
        raise ValueError("failure_threshold must be at least 1")

    timestamp = probed_at or datetime.now(UTC)
    # Serialize concurrent checker runs for this monitor before checking open state.
    session.execute(select(Monitor.id).where(Monitor.id == monitor.id).with_for_update())
    probe_result = ProbeResult(
        monitor_id=monitor.id,
        probed_at=timestamp,
        is_up=outcome.is_up,
        http_status=outcome.http_status,
        latency_ms=outcome.latency_ms,
        error_message=outcome.error_message,
    )
    session.add(probe_result)
    session.flush()

    open_incident = session.scalar(
        select(Incident)
        .where(Incident.monitor_id == monitor.id, Incident.resolved_at.is_(None))
        .with_for_update()
    )
    if outcome.is_up:
        if open_incident is None:
            return IncidentTransition.NONE
        open_incident.resolved_at = timestamp
        return IncidentTransition.RESOLVED

    if open_incident is not None:
        open_incident.last_error = outcome.error_message
        return IncidentTransition.NONE

    recent_results = session.scalars(
        select(ProbeResult.is_up)
        .where(ProbeResult.monitor_id == monitor.id)
        .order_by(ProbeResult.probed_at.desc(), ProbeResult.id.desc())
        .limit(failure_threshold)
    ).all()
    consecutive_failures = 0
    for is_up in recent_results:
        if is_up:
            break
        consecutive_failures += 1

    transition = determine_incident_transition(
        is_up=False,
        consecutive_failures=consecutive_failures,
        has_open_incident=False,
        failure_threshold=failure_threshold,
    )
    if transition is IncidentTransition.OPENED:
        session.add(
            Incident(
                monitor_id=monitor.id,
                opened_at=timestamp,
                last_error=outcome.error_message,
            )
        )
    return transition
