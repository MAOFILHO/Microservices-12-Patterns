"""Wires a Flask service into the shared observability plumbing and adds standard endpoints.

Endpoints added to every service:
  GET /health          liveness
  GET /health/db       which database this service owns (pattern 1); credentials never shown
  GET /debug/spans     this process's recent spans, optionally filtered by ?trace_id= (pattern 6)
  GET /metrics         Prometheus text format (pattern 6)
"""
import time

from flask import Flask, Response, g, jsonify, request
from sqlalchemy import inspect

from . import metrics
from .telemetry import REQUEST_ID_HEADER, SPAN_STORE, current_trace_id, get_logger, init_tracing


def install(app: Flask, service_name: str, db) -> None:
    init_tracing(service_name)
    from opentelemetry.instrumentation.flask import FlaskInstrumentor

    FlaskInstrumentor().instrument_app(app, excluded_urls="health,debug/spans,metrics")
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    # Needs an app context (every service calls install() inside one). Once per process.
    SQLAlchemyInstrumentor().instrument(engine=db.engine)
    log = get_logger()

    @app.before_request
    def _start_timer():
        g.request_started = time.perf_counter()
        g.request_id = request.headers.get(REQUEST_ID_HEADER)

    @app.after_request
    def _record(response):
        route = request.url_rule.rule if request.url_rule else "unmatched"
        if route in ("/health", "/debug/spans", "/metrics"):
            return response
        elapsed = time.perf_counter() - g.get("request_started", time.perf_counter())
        metrics.observe(service_name, request.method, route, response.status_code, elapsed)
        log.info(
            f"{request.method} {route} -> {response.status_code} in {elapsed * 1000:.1f} ms",
            extra={"request_id": g.get("request_id")},
        )
        if g.get("request_id"):
            response.headers[REQUEST_ID_HEADER] = g.request_id
        trace_id = current_trace_id()
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "service": service_name}

    @app.get("/health/db")
    def health_db():
        engine = db.engine
        url = engine.url
        return jsonify({
            "service": service_name,
            "engine": url.get_backend_name(),
            # SQLite: the file name only. MySQL: the logical database name only.
            "database": (url.database or "").rsplit("/", 1)[-1],
            "tables": sorted(inspect(engine).get_table_names()),
        })

    @app.get("/debug/spans")
    def debug_spans():
        trace_id = request.args.get("trace_id")
        spans = SPAN_STORE.by_trace(trace_id) if trace_id else SPAN_STORE.recent()
        return jsonify({"service": service_name, "spans": spans})

    @app.get("/metrics")
    def prometheus_metrics():
        body, content_type = metrics.render()
        return Response(body, content_type=content_type)
