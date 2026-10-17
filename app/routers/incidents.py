from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.monitor import IncidentRead
from db.models import Incident

router = APIRouter(prefix="/api")


@router.get("/incidents", response_model=list[IncidentRead])
def list_incidents(
    db: Annotated[Session, Depends(get_db)],
    open: bool | None = Query(default=None, description="Filter to open incidents only."),
) -> list[IncidentRead]:
    query = select(Incident)
    if open is not None:
        if open:
            query = query.where(Incident.resolved_at.is_(None))
        else:
            query = query.where(Incident.resolved_at.is_not(None))
    query = query.order_by(Incident.opened_at.desc(), Incident.id.desc())
    incidents = db.scalars(query).all()
    return [IncidentRead.model_validate(incident) for incident in incidents]
