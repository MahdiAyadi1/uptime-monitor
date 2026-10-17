"""Tests for HTTP probe behavior."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from monitor.probing import ProbeOutcome, probe_monitor

TEST_URL = "https://8.8.8.8/check"


def _monitor(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "url": TEST_URL,
        "expected_status": 200,
        "expected_keyword": None,
        "timeout_seconds": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _probe(
    handler: httpx.MockTransport, monitor: SimpleNamespace, **kwargs: object
) -> ProbeOutcome:
    async def run() -> ProbeOutcome:
        async with httpx.AsyncClient(transport=handler) as client:
            return await probe_monitor(client, monitor, **kwargs)

    return asyncio.run(run())


def test_probe_reports_expected_status_and_latency() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"healthy"))

    result = _probe(transport, _monitor())

    assert result.is_up is True
    assert result.http_status == 200
    assert result.latency_ms is not None
    assert result.error_message is None


def test_probe_fails_on_unexpected_status_and_does_not_follow_redirects() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"Location": "/up"})
    )

    result = _probe(transport, _monitor())

    assert result.is_up is False
    assert result.http_status == 302
    assert result.error_message == "Expected HTTP 200, received 302"


def test_probe_checks_keyword_within_response_limit() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"prefix-healthy"))

    result = _probe(
        transport,
        _monitor(expected_keyword="healthy"),
        response_bytes_limit=14,
    )

    assert result.is_up is True


def test_probe_fails_when_keyword_is_beyond_response_limit() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"prefix-healthy"))

    result = _probe(
        transport,
        _monitor(expected_keyword="healthy"),
        response_bytes_limit=6,
    )

    assert result.is_up is False
    assert result.error_message == "Expected keyword was not found in the response body limit"


def test_probe_converts_timeout_to_down_result() -> None:
    def raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("late", request=request)

    result = _probe(httpx.MockTransport(raise_timeout), _monitor())

    assert result.is_up is False
    assert result.error_message == "Request timed out"


def test_probe_rejects_negative_body_limit() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200))

    with pytest.raises(ValueError, match="non-negative"):
        _probe(transport, _monitor(), response_bytes_limit=-1)
