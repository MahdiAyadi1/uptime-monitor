from fastapi import FastAPI

from app.routers.health import router as health_router
from app.routers.incidents import router as incidents_router
from app.routers.monitors import router as monitors_router
from app.routers.status import router as status_router
from monitor.logging_config import configure_logging
from monitor.settings import Settings

configure_logging(Settings().log_level)

app = FastAPI(
    title="Uptime Monitor",
    version="0.1.0",
    description="Local uptime monitoring service for portfolio use.",
)

app.include_router(health_router)
app.include_router(status_router)
app.include_router(monitors_router)
app.include_router(incidents_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "uptime-monitor"}
