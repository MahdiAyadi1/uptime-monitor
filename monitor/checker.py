"""Scheduled checker orchestration for due monitors."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from db.models import Monitor, ProbeResult
from db.session import create_database_engine, create_session_factory
from monitor.incidents import IncidentTransition, record_probe_result
from monitor.logging_config import configure_logging
from monitor.probing import ProbeOutcome, probe_monitor
from monitor.settings import Settings

logger = logging.getLogger(__name__)


def _normalize_to_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime for comparison regardless of source timezone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class MonitorTarget:
    """Detached monitor settings needed by a probe task."""

    id: int
    name: str
    url: str
    expected_status: int
    expected_keyword: str | None
    timeout_seconds: int
    interval_seconds: int

    @classmethod
    def from_model(cls, monitor: Monitor) -> MonitorTarget:
        """Copy the settings needed for probing out of an ORM entity."""
        return cls(
            id=monitor.id,
            name=monitor.name,
            url=monitor.url,
            expected_status=monitor.expected_status,
            expected_keyword=monitor.expected_keyword,
            timeout_seconds=monitor.timeout_seconds,
            interval_seconds=monitor.interval_seconds,
        )


@dataclass(frozen=True, slots=True)
class CheckerSummary:
    """Counts from a complete checker pass."""

    probed: int
    up: int
    down: int
    incidents_opened: int
    incidents_resolved: int


def load_due_monitors(
    session: Session,
    *,
    now: datetime | None = None,
    due_tolerance_seconds: int = 5,
) -> list[MonitorTarget]:
    """Return enabled monitors whose interval has elapsed, with a small due tolerance."""
    if due_tolerance_seconds < 0:
        raise ValueError("due_tolerance_seconds must be non-negative")

    current_time = _normalize_to_utc(now or datetime.now(UTC))
    tolerance_window = timedelta(seconds=due_tolerance_seconds)
    monitors = session.scalars(select(Monitor).where(Monitor.enabled.is_(True))).all()
    if not monitors:
        return []

    latest_probe_rows = session.execute(
        select(ProbeResult.monitor_id, func.max(ProbeResult.probed_at))
        .where(ProbeResult.monitor_id.in_([monitor.id for monitor in monitors]))
        .group_by(ProbeResult.monitor_id)
    ).all()
    latest_probe_by_monitor = dict(latest_probe_rows)

    due_targets: list[MonitorTarget] = []
    for monitor in monitors:
        last_probed_at = latest_probe_by_monitor.get(monitor.id)
        if last_probed_at is None:
            due_at = None
        else:
            due_at = _normalize_to_utc(last_probed_at) + timedelta(seconds=monitor.interval_seconds)
        if due_at is None or due_at <= current_time + tolerance_window:
            due_targets.append(MonitorTarget.from_model(monitor))
    return due_targets


async def run_checker(
    session_factory: sessionmaker[Session],
    *,
    failure_threshold: int = 3,
    max_concurrent_probes: int = 20,
    response_bytes_limit: int = 1_048_576,
    user_agent: str = "uptime-monitor-portfolio/1.0",
    due_tolerance_seconds: int = 5,
    now: datetime | None = None,
) -> CheckerSummary:
    """Probe due monitors concurrently and persist each result and transition."""
    if failure_threshold < 1:
        raise ValueError("failure_threshold must be at least 1")
    if max_concurrent_probes < 1:
        raise ValueError("max_concurrent_probes must be at least 1")

    with session_factory() as session:
        targets = load_due_monitors(session, now=now, due_tolerance_seconds=due_tolerance_seconds)

    if not targets:
        return CheckerSummary(0, 0, 0, 0, 0)

    semaphore = asyncio.Semaphore(max_concurrent_probes)
    transitions: list[IncidentTransition] = []
    outcomes: list[ProbeOutcome] = []

    async with httpx.AsyncClient(
        follow_redirects=False,
        headers={"User-Agent": user_agent},
        trust_env=False,
    ) as client:

        async def check_one(target: MonitorTarget) -> tuple[ProbeOutcome, IncidentTransition]:
            async with semaphore:
                outcome = await probe_monitor(
                    client,
                    target,
                    response_bytes_limit=response_bytes_limit,
                )
            with session_factory() as session:
                monitor = session.get(Monitor, target.id)
                if monitor is None:
                    return outcome, IncidentTransition.NONE
                transition = record_probe_result(
                    session,
                    monitor,
                    outcome,
                    failure_threshold=failure_threshold,
                    probed_at=now,
                )
                session.commit()
                return outcome, transition

        results = await asyncio.gather(*(check_one(target) for target in targets))
        for target, (outcome, transition) in zip(targets, results, strict=True):
            outcomes.append(outcome)
            transitions.append(transition)
            logger.info(
                "Monitor probe completed",
                extra={
                    "event": "monitor.probe.completed",
                    "monitor_id": target.id,
                    "monitor_name": target.name,
                    "is_up": outcome.is_up,
                    "http_status": outcome.http_status,
                    "latency_ms": outcome.latency_ms,
                    "incident_transition": transition.value,
                },
            )

    return CheckerSummary(
        probed=len(outcomes),
        up=sum(outcome.is_up for outcome in outcomes),
        down=sum(not outcome.is_up for outcome in outcomes),
        incidents_opened=transitions.count(IncidentTransition.OPENED),
        incidents_resolved=transitions.count(IncidentTransition.RESOLVED),
    )


def main() -> int:
    """Load settings and run one checker pass."""
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        summary = asyncio.run(
            run_checker(
                session_factory,
                failure_threshold=settings.failure_threshold,
                max_concurrent_probes=settings.max_concurrent_probes,
                response_bytes_limit=settings.response_bytes_limit,
                user_agent=settings.probe_user_agent,
                due_tolerance_seconds=settings.due_tolerance_seconds,
            )
        )
        logger.info(
            "Checker pass completed",
            extra={
                "event": "checker.completed",
                "probed": summary.probed,
                "up": summary.up,
                "down": summary.down,
                "incidents_opened": summary.incidents_opened,
                "incidents_resolved": summary.incidents_resolved,
            },
        )
    except Exception:
        logger.exception("Checker run failed", extra={"event": "checker.failed"})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
