from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.dependencies.database import get_db
from app.main import app
from db.models import Monitor


class FakeScalarResult:
    def __init__(self, values: list[Monitor]) -> None:
        self.values = values

    def all(self) -> list[Monitor]:
        return self.values


class FakeDatabase:
    def __init__(self) -> None:
        self.monitors: dict[int, Monitor] = {}
        self.next_monitor_id = 1

    def scalars(self, statement: Any) -> FakeScalarResult:
        monitors = sorted(self.monitors.values(), key=lambda monitor: monitor.id)
        return FakeScalarResult(monitors)

    def add(self, monitor: Monitor) -> None:
        monitor.id = self.next_monitor_id
        monitor.created_at = datetime.now(UTC)
        self.next_monitor_id += 1
        self.monitors[monitor.id] = monitor

    def commit(self) -> None:
        pass

    def refresh(self, monitor: Monitor) -> None:
        pass

    def get(self, model: type[Monitor], monitor_id: int) -> Monitor | None:
        return self.monitors.get(monitor_id)

    def delete(self, monitor: Monitor) -> None:
        del self.monitors[monitor.id]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    database = FakeDatabase()
    previous_overrides = app.dependency_overrides.copy()

    def override_get_db() -> Generator[FakeDatabase, None, None]:
        yield database

    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setattr("app.routers.monitors.validate_monitor_url", lambda url: None)
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_monitor_crud(client: TestClient) -> None:
    create_response = client.post(
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
    assert create_response.status_code == 201, create_response.text
    payload = create_response.json()
    assert payload["name"] == "example-monitor"
    assert payload["url"] == "https://example.com"

    monitor_id = payload["id"]
    get_response = client.get(f"/api/monitors/{monitor_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == monitor_id

    list_response = client.get("/api/monitors")
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 1
    assert items[0]["name"] == "example-monitor"

    update_response = client.put(
        f"/api/monitors/{monitor_id}",
        json={"name": "updated-monitor", "enabled": False},
        headers={"X-API-Key": "test-key"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "updated-monitor"
    assert update_response.json()["enabled"] is False

    delete_response = client.delete(
        f"/api/monitors/{monitor_id}",
        headers={"X-API-Key": "test-key"},
    )
    assert delete_response.status_code == 204
    assert client.get(f"/api/monitors/{monitor_id}").status_code == 404


def test_write_endpoints_require_api_key(client: TestClient) -> None:
    response = client.post(
        "/api/monitors",
        json={
            "name": "blocked-monitor",
            "url": "https://example.com",
            "expected_status": 200,
        },
    )
    assert response.status_code == 401
