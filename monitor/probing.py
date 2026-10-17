"""Asynchronous HTTP probe implementation, independent of FastAPI."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from monitor.url_validation import URLValidationError, validate_monitor_url


class MonitorProbeConfig(Protocol):
    """Configuration attributes consumed by the probe function."""

    url: str
    expected_status: int
    expected_keyword: str | None
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    """Persistable result of one HTTP probe attempt."""

    is_up: bool
    http_status: int | None
    latency_ms: int | None
    error_message: str | None


async def probe_monitor(
    client: httpx.AsyncClient,
    monitor: MonitorProbeConfig,
    *,
    response_bytes_limit: int = 1_048_576,
) -> ProbeOutcome:
    """Check a target's status and optional keyword without following redirects."""
    if response_bytes_limit < 0:
        raise ValueError("response_bytes_limit must be non-negative")

    try:
        await asyncio.to_thread(validate_monitor_url, monitor.url)
    except URLValidationError as exc:
        return ProbeOutcome(False, None, None, str(exc))

    started_at = time.perf_counter()
    try:
        async with client.stream(
            "GET",
            monitor.url,
            timeout=monitor.timeout_seconds,
            follow_redirects=False,
        ) as response:
            body = bytearray()
            if monitor.expected_keyword is not None:
                async for chunk in response.aiter_bytes():
                    remaining = response_bytes_limit - len(body)
                    if remaining <= 0:
                        break
                    body.extend(chunk[:remaining])
                    if len(chunk) >= remaining:
                        break

            latency_ms = round((time.perf_counter() - started_at) * 1000)
            if response.status_code != monitor.expected_status:
                return ProbeOutcome(
                    False,
                    response.status_code,
                    latency_ms,
                    f"Expected HTTP {monitor.expected_status}, received {response.status_code}",
                )

            if monitor.expected_keyword is not None:
                content = body.decode("utf-8", errors="replace")
                if monitor.expected_keyword not in content:
                    return ProbeOutcome(
                        False,
                        response.status_code,
                        latency_ms,
                        "Expected keyword was not found in the response body limit",
                    )

            return ProbeOutcome(True, response.status_code, latency_ms, None)
    except httpx.TimeoutException:
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        return ProbeOutcome(False, None, latency_ms, "Request timed out")
    except httpx.RequestError as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        return ProbeOutcome(False, None, latency_ms, f"Request failed: {exc}")
