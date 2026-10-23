"""Tests for structured JSON logging."""

import json
import logging

from monitor.logging_config import JsonLogFormatter


def test_json_log_formatter_includes_context_fields() -> None:
    record = logging.LogRecord(
        name="monitor.checker",
        level=logging.WARNING,
        pathname=__file__,
        lineno=12,
        msg="Probe failed",
        args=(),
        exc_info=None,
    )
    record.event = "probe.completed"
    record.monitor_id = 42

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["level"] == "WARNING"
    assert payload["logger"] == "monitor.checker"
    assert payload["message"] == "Probe failed"
    assert payload["event"] == "probe.completed"
    assert payload["monitor_id"] == 42
    assert payload["timestamp"].endswith("Z")
