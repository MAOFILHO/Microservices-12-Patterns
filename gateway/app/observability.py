"""Gateway side of patterns 5 and 6.

- Request IDs: every request gets an X-Request-Id (kept if the client sent one), which is
  forwarded to every service call and echoed back, so one ID ties together all the logs.
- Tracing: FastAPI and httpx are instrumented, so each browser request becomes one trace that
  continues through every service the gateway calls.
- Metrics: request count and latency per route, at /metrics.
"""
import time
import uuid

from fastapi import FastAPI, Request, Response
from opentelemetry import trace

from shop_common import metrics
from shop_common.telemetry import REQUEST_ID_HEADER, SPAN_STORE, current_trace_id, get_logger, init_tracing

SERVICE_NAME = "gateway"
_QUIET_PATHS = ("/health", "/metrics", "/debug/spans")


def install(app: FastAPI) -> None:
    init_tracing(SERVICE_NAME)
    log = get_logger()

    @app.middleware("http")
    async def request_id_and_metrics(request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        trace.get_current_span().set_attribute("request.id", request_id)
        started = time.perf_counter()
        response = await call_next(request)
        if request.url.path in _QUIET_PATHS:
            return response
        route = getattr(request.scope.get("route"), "path", request.url.path)
        elapsed = time.perf_counter() - started
        metrics.observe(SERVICE_NAME, request.method, route, response.status_code, elapsed)
        log.info(f"{request.method} {route} -> {response.status_code} in {elapsed * 1000:.1f} ms",
                 extra={"request_id": request_id})
        response.headers[REQUEST_ID_HEADER] = request_id
        trace_id = current_trace_id()
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        return response

    # Instrument AFTER adding the middleware above: Starlette runs the last-added middleware
    # outermost, so the tracing middleware wraps ours and the span is active inside it.
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics,debug/spans")

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics():
        body, content_type = metrics.render()
        return Response(content=body, media_type=content_type)

    @app.get("/debug/spans", include_in_schema=False)
    async def debug_spans(trace_id: str | None = None):
        spans = SPAN_STORE.by_trace(trace_id) if trace_id else SPAN_STORE.recent()
        return {"service": SERVICE_NAME, "spans": spans}


def upstream_headers(request: Request) -> dict[str, str]:
    """Headers to forward to a service: the client's, minus hop-specific ones, plus the request ID."""
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    headers[REQUEST_ID_HEADER] = request.state.request_id
    return headers
