from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from db.models import Monitor

router = APIRouter()


@router.get("/api/status")
def status(db: Annotated[Session, Depends(get_db)]) -> list[dict[str, object]]:
    monitors = db.scalars(select(Monitor).order_by(Monitor.id)).all()
    return [
        {
            "id": monitor.id,
            "name": monitor.name,
            "url": monitor.url,
            "enabled": monitor.enabled,
            "status": "up",
            "uptime_percent": 100.0,
        }
        for monitor in monitors
    ]
