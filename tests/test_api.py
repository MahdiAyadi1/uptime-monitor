import os

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.dependencies.database import get_db
from app.main import app
from db.base import Base

os.environ["API_KEY"] = "test-key"

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_list_monitors():
    response = client.post(
        "/api/monitors",
        json={
            "name": "example-monitor",
            "url": "https://example.com",
            "expected_status": 200,
            "expected_keyword": "Example",
            "timeout_seconds": 5,
            "interval_seconds": 300,
        },
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["name"] == "example-monitor"
    assert payload["url"] == "https://example.com"

    list_response = client.get("/api/monitors")
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 1
    assert items[0]["name"] == "example-monitor"


def test_write_endpoints_require_api_key():
    response = client.post(
        "/api/monitors",
        json={
            "name": "blocked-monitor",
            "url": "https://example.com",
            "expected_status": 200,
        },
    )
    assert response.status_code == 401
