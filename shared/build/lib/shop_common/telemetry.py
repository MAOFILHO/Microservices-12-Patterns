"""Pattern 6, Observability: traces, JSON logs with trace IDs, and metrics.

Traces: OpenTelemetry. Every service keeps its most recent spans in memory (SPAN_STORE) and
serves them at /debug/spans, so the gateway can stitch one request's spans from every service
into a waterfall without any external tool. If OTEL_EXPORTER_OTLP_ENDPOINT is set, spans are
also exported over OTLP/HTTP (e.g. to otel-desktop-viewer locally or a collector in Azure).

Trace context crosses service boundaries in the W3C `traceparent` header, which the requests
and httpx instrumentations inject and the Flask/FastAPI instrumentations extract.
"""
import json
import logging
import os
import sys
import threading
from collections import deque

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

REQUEST_ID_HEADER = "X-Request-Id"


class SpanStore(SpanProcessor):
    """Ring buffer of finished spans. Thread-safe; oldest spans fall off first."""

    def __init__(self, maxlen: int = 2000):
        self._spans: deque[dict] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def on_end(self, span: ReadableSpan) -> None:
        ctx = span.get_span_context()
        attrs = dict(span.attributes or {})
        record = {
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
            "parent_id": format(span.parent.span_id, "016x") if span.parent else None,
            # Only database spans carry file paths (SQLite); HTTP span names keep their URL paths.
            "name": _strip_paths(span.name) if "db.system" in attrs else span.name,
            "service": span.resource.attributes.get("service.name", "unknown"),
            "kind": span.kind.name,
            "start_ns": span.start_time,
            "end_ns": span.end_time,
            "status": span.status.status_code.name,
            # Keep a few readable attributes only; never request bodies or headers.
            "attributes": {k: _strip_paths(str(v)) if k == "db.name" else v
                           for k, v in attrs.items() if k in _KEPT_ATTRIBUTES},
        }
        with self._lock:
            self._spans.append(record)

    def by_trace(self, trace_id: str) -> list[dict]:
        with self._lock:
            return [s for s in self._spans if s["trace_id"] == trace_id]

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._spans)[-limit:]

    def shutdown(self) -> None:  # SpanProcessor interface
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # SpanProcessor interface
        return True


def _strip_paths(text: str) -> str:
    """SQLite database names are absolute file paths; keep only the file name so a span never
    reveals the host's directory layout (e.g. 'SELECT /home/x/catalog.sqlite3' -> 'SELECT catalog.sqlite3')."""
    return " ".join(part.rsplit("/", 1)[-1] if part.startswith("/") else part for part in text.split(" "))


_KEPT_ATTRIBUTES = {
    "http.method", "http.request.method", "http.route", "http.target", "url.path",
    "http.status_code", "http.response.status_code", "http.url", "url.full",
    "db.system", "db.name", "db.statement", "request.id",
}

SPAN_STORE = SpanStore()
_initialised = False


def init_tracing(service_name: str) -> trace.Tracer:
    """Sets the global tracer provider once per process and instruments outgoing calls."""
    global _initialised
    if not _initialised:
        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(SPAN_STORE)
        if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)

        _instrument_if_installed()
        _configure_json_logging(service_name)
        _initialised = True
    return trace.get_tracer(service_name)


def _instrument_if_installed() -> None:
    """Instruments each HTTP client library only if this process has it: Flask services use
    requests, the gateway uses httpx. Database engines are instrumented one by one, see
    flask_support.install (Flask-SQLAlchemy creates its engine in a way the global hook misses)."""
    import importlib.util

    if importlib.util.find_spec("requests"):
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        RequestsInstrumentor().instrument()
    if importlib.util.find_spec("httpx"):
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line, carrying the active trace and span IDs."""

    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        ctx = trace.get_current_span().get_span_context()
        payload = {
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": format(ctx.trace_id, "032x") if ctx.is_valid else None,
            "span_id": format(ctx.span_id, "016x") if ctx.is_valid else None,
            "request_id": getattr(record, "request_id", None),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _configure_json_logging(service_name: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter(service_name))
    logger = logging.getLogger("shop")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False


def get_logger() -> logging.Logger:
    return logging.getLogger("shop")
