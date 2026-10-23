from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies.auth import require_api_key
from app.dependencies.database import get_db
from app.schemas.monitor import MonitorCreate, MonitorRead, MonitorUpdate, ProbeResultRead
from db.models import Monitor, ProbeResult
from monitor.url_validation import URLValidationError, validate_monitor_url

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _hydrate_monitor(monitor: Monitor) -> MonitorRead:
    return MonitorRead.model_validate(monitor)


@router.get("/monitors", response_model=list[MonitorRead])
def list_monitors(db: Annotated[Session, Depends(get_db)]) -> list[MonitorRead]:
    monitors = db.scalars(select(Monitor).order_by(Monitor.id)).all()
    return [_hydrate_monitor(monitor) for monitor in monitors]


@router.post("/monitors", response_model=MonitorRead, status_code=status.HTTP_201_CREATED)
def create_monitor(
    payload: MonitorCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_api_key)],
) -> MonitorRead:
    try:
        validate_monitor_url(payload.url)
    except URLValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    monitor = Monitor(**payload.model_dump())
    db.add(monitor)
    db.commit()
    db.refresh(monitor)
    logger.info(
        "Monitor created",
        extra={"event": "monitor.created", "monitor_id": monitor.id, "monitor_name": monitor.name},
    )
    return _hydrate_monitor(monitor)


@router.get("/monitors/{monitor_id}", response_model=MonitorRead)
def get_monitor(monitor_id: int, db: Annotated[Session, Depends(get_db)]) -> MonitorRead:
    monitor = db.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return _hydrate_monitor(monitor)


@router.put("/monitors/{monitor_id}", response_model=MonitorRead)
def update_monitor(
    monitor_id: int,
    payload: MonitorUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_api_key)],
) -> MonitorRead:
    monitor = db.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")

    updates = payload.model_dump(exclude_unset=True)
    if "url" in updates and updates["url"] is not None:
        try:
            validate_monitor_url(updates["url"])
        except URLValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    for key, value in updates.items():
        setattr(monitor, key, value)

    db.commit()
    db.refresh(monitor)
    logger.info(
        "Monitor updated",
        extra={"event": "monitor.updated", "monitor_id": monitor.id, "monitor_name": monitor.name},
    )
    return _hydrate_monitor(monitor)


@router.delete("/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monitor(
    monitor_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_api_key)],
) -> Response:
    monitor = db.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    db.delete(monitor)
    db.commit()
    logger.info(
        "Monitor deleted",
        extra={"event": "monitor.deleted", "monitor_id": monitor.id, "monitor_name": monitor.name},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/monitors/{monitor_id}/results", response_model=list[ProbeResultRead])
def monitor_results(
    monitor_id: int,
    db: Annotated[Session, Depends(get_db)],
    limit: int = 20,
) -> list[ProbeResultRead]:
    if limit <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be positive",
        )
    rows = db.scalars(
        select(ProbeResult)
        .where(ProbeResult.monitor_id == monitor_id)
        .order_by(ProbeResult.probed_at.desc(), ProbeResult.id.desc())
        .limit(limit)
    ).all()
    return [ProbeResultRead.model_validate(row) for row in rows]
