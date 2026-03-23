"""
Centralized OpenTelemetry + Structured Logging setup.
Call setup_telemetry(app, service_name) once in each service's main.py.
"""

import logging
import logging.config
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


class TraceIDFilter(logging.Filter):
    """Ensures otelTraceID and otelSpanID are always present in the LogRecord."""

    def filter(self, record):
        if not hasattr(record, "otelTraceID"):
            record.otelTraceID = "0"
        if not hasattr(record, "otelSpanID"):
            record.otelSpanID = "0"
        return True


class SafeFormatter(logging.Formatter):
    """Fallback formatter that handles missing trace fields just in case."""

    def format(self, record):
        if not hasattr(record, "otelTraceID"):
            record.otelTraceID = "0"
        if not hasattr(record, "otelSpanID"):
            record.otelSpanID = "0"
        return super().format(record)


def setup_telemetry(app, service_name: str, db_engine=None) -> None:
    """
    Initialize OpenTelemetry tracing + auto-instrument FastAPI, SQLAlchemy & httpx.
    Set OTEL_EXPORTER_OTLP_ENDPOINT env var (default: http://jaeger:4318/v1/traces).
    """
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318/v1/traces").strip()

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    try:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    except Exception as e:
        # Don't let telemetry failure crash the service startup
        print(f"Failed to initialize OTLP exporter: {e}")
    try:
        trace.set_tracer_provider(provider)
    except Exception:
        # Tracer provider can only be set once per process.
        pass

    # Automatically inject trace_id/span_id into log records
    LoggingInstrumentor().instrument(set_logging_format=False)

    if app:
        FastAPIInstrumentor.instrument_app(app)

    # Propagate trace context on all outgoing httpx requests
    if not HTTPXClientInstrumentor().is_instrumented_by_opentelemetry:
        HTTPXClientInstrumentor().instrument()

    if db_engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=db_engine.sync_engine)


def setup_logging(service_name: str) -> None:
    """
    Overhauls logging using dictConfig to ensure consistency across services.
    Uses TraceIDFilter to prevent KeyError on otelTraceID/otelSpanID.
    """
    log_format = (
        f"[{service_name}] %(levelname)s: [trace_id=%(otelTraceID)s " f"span_id=%(otelSpanID)s] %(name)s - %(message)s"
    )

    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "trace_id": {
                "()": TraceIDFilter,
            },
        },
        "formatters": {
            "default": {
                "()": SafeFormatter,
                "format": log_format,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "filters": ["trace_id"],
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {  # root logger
                "handlers": ["console"],
                "level": "INFO",
            },
            "uvicorn": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "opentelemetry": {
                "level": "ERROR",  # Suppress export warnings that can cause recursion
            },
        },
    }

    logging.config.dictConfig(LOGGING_CONFIG)
