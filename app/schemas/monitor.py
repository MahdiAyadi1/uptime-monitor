from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MonitorBase(BaseModel):
    name: str
    url: str
    expected_status: int = 200
    expected_keyword: str | None = None
    timeout_seconds: int = 10
    interval_seconds: int = 300
    enabled: bool = True


class MonitorCreate(MonitorBase):
    pass


class MonitorUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    expected_status: int | None = None
    expected_keyword: str | None = None
    timeout_seconds: int | None = None
    interval_seconds: int | None = None
    enabled: bool | None = None


class MonitorRead(MonitorBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProbeResultRead(BaseModel):
    id: int
    monitor_id: int
    probed_at: datetime
    is_up: bool
    http_status: int | None = None
    latency_ms: int | None = None
    tls_days_remaining: int | None = None
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class IncidentRead(BaseModel):
    id: int
    monitor_id: int
    opened_at: datetime
    resolved_at: datetime | None = None
    last_error: str | None = None

    model_config = ConfigDict(from_attributes=True)
