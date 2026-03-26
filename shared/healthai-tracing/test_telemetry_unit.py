import sys
from unittest.mock import MagicMock

# Mock opentelemetry before they are imported by telemetry.py
sys.modules["opentelemetry"] = MagicMock()
sys.modules["opentelemetry.trace"] = MagicMock()
sys.modules["opentelemetry.exporter"] = MagicMock()
sys.modules["opentelemetry.exporter.otlp"] = MagicMock()
sys.modules["opentelemetry.exporter.otlp.proto"] = MagicMock()
sys.modules["opentelemetry.exporter.otlp.proto.http"] = MagicMock()
sys.modules["opentelemetry.exporter.otlp.proto.http.trace_exporter"] = MagicMock()
sys.modules["opentelemetry.instrumentation"] = MagicMock()
sys.modules["opentelemetry.instrumentation.fastapi"] = MagicMock()
sys.modules["opentelemetry.instrumentation.httpx"] = MagicMock()
sys.modules["opentelemetry.instrumentation.logging"] = MagicMock()
sys.modules["opentelemetry.instrumentation.sqlalchemy"] = MagicMock()
sys.modules["opentelemetry.sdk"] = MagicMock()
sys.modules["opentelemetry.sdk.resources"] = MagicMock()
sys.modules["opentelemetry.sdk.trace"] = MagicMock()
sys.modules["opentelemetry.sdk.trace.export"] = MagicMock()

import logging  # noqa: E402
from telemetry import TraceIDFilter, SafeFormatter, setup_logging  # noqa: E402


def test_trace_id_filter():
    filter_instance = TraceIDFilter()
    record = MagicMock(spec=logging.LogRecord)
    # Test when attributes are missing
    delattr(record, "otelTraceID") if hasattr(record, "otelTraceID") else None
    delattr(record, "otelSpanID") if hasattr(record, "otelSpanID") else None

    assert filter_instance.filter(record) is True
    assert record.otelTraceID == "0"
    assert record.otelSpanID == "0"

    # Test when attributes are present
    record.otelTraceID = "trace-123"
    filter_instance.filter(record)
    assert record.otelTraceID == "trace-123"


def test_safe_formatter():
    formatter = SafeFormatter()
    record = logging.LogRecord("name", logging.INFO, "path", 10, "msg", None, None)

    # Before formatting, the record doesn't have the attributes
    # The formatter should add them during format()
    assert not hasattr(record, "otelTraceID")
    formatter.format(record)
    assert record.otelTraceID == "0"


def test_setup_logging_no_crash():
    # Smoke test to ensure setup_logging runs without error
    setup_logging("test_service")
    logger = logging.getLogger("test_service")
    # Should inherit INFO from root or be specifically set
    assert logger.getEffectiveLevel() == logging.INFO
