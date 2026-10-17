"""SQLAlchemy models for monitors, probe results, and incidents."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Monitor(Base):
    """A configured endpoint to probe on a recurring interval."""

    __tablename__ = "monitor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    expected_status: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("200")
    )
    expected_keyword: Mapped[str | None] = mapped_column(Text)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("10"))
    interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("300")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    probe_results: Mapped[list[ProbeResult]] = relationship(
        back_populates="monitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    incidents: Mapped[list[Incident]] = relationship(
        back_populates="monitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProbeResult(Base):
    """The outcome of one monitor probe."""

    __tablename__ = "probe_result"
    __table_args__ = (
        Index(
            "ix_probe_result_monitor_time",
            "monitor_id",
            text("probed_at DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitor.id", ondelete="CASCADE"), nullable=False
    )
    probed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_up: Mapped[bool] = mapped_column(Boolean, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tls_days_remaining: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)

    monitor: Mapped[Monitor] = relationship(back_populates="probe_results")


class Incident(Base):
    """A monitor outage, open until the first successful probe."""

    __tablename__ = "incident"
    __table_args__ = (
        Index(
            "ux_incident_one_open_per_monitor",
            "monitor_id",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitor.id", ondelete="CASCADE"), nullable=False
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    monitor: Mapped[Monitor] = relationship(back_populates="incidents")
