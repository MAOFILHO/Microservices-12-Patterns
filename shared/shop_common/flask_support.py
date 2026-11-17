"""Wires a Flask service into the shared observability plumbing and adds standard endpoints.

Endpoints added to every service:
  GET /health          liveness
  GET /health/db       which database this service owns (pattern 1); credentials never shown
  GET /debug/spans     this process's recent spans, optionally filtered by ?trace_id= (pattern 6)
  GET /metrics         Prometheus text format (pattern 6)
  GET /debug/runtime   what this process runs as: uid, container or not, image git SHA (pattern 9)
  POST /debug/crash    stops this process, for the replica and discovery demos (CHAOS_ENABLED=1 only)

Every response carries X-Instance-Id, so a demo can show which replica answered (pattern 10).
With REGISTRY_URL and SERVICE_PUBLIC_URL set, the service registers itself (pattern 12).
"""
import os
import threading
import time

from flask import Flask, Response, g, jsonify, request
from sqlalchemy import inspect

from . import metrics
from .discovery import DISCOVERY
from .runtime import runtime_info
from .telemetry import REQUEST_ID_HEADER, SPAN_STORE, current_trace_id, get_logger, init_tracing


INSTANCE_HEADER = "X-Instance-Id"


def instance_id(service_name: str) -> str:
    """Set by run_local.py (e.g. order-5113); Container Apps sets the replica name."""
    return os.environ.get("INSTANCE_ID") or os.environ.get("CONTAINER_APP_REPLICA_NAME") or f"{service_name}-{os.getpid()}"


def is_serving_process(app: Flask) -> bool:
    """False in the file-watcher process of app.run(debug=True).

    The reloader runs a watcher plus a worker (marked WERKZEUG_RUN_MAIN=true), and both build the
    app. Only the worker serves requests, so only it may run background threads (registry
    heartbeats, outbox relay, event consumer). Under gunicorn there is no reloader.
    """
    return not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def chaos_enabled() -> bool:
    return os.environ.get("CHAOS_ENABLED") == "1"


def switches_off() -> Response:
    """The one answer every demo switch gives when CHAOS_ENABLED is not 1."""
    response = jsonify({"message": "Demo switches are off (CHAOS_ENABLED is not 1)"})
    response.status_code = 403
    return response


class DemoSwitch:
    """A lab switch held in memory, one value per process: a demo setting, not data.
    GET reads it; POST {"mode": ...} sets it, only when CHAOS_ENABLED=1."""

    def __init__(self, *modes: str):
        self.modes = modes
        self.value = modes[0]

    def respond(self) -> Response:
        if request.method == "POST":
            if not chaos_enabled():
                return switches_off()
            mode = (request.get_json(silent=True) or request.form.to_dict()).get("mode")
            if mode not in self.modes:
                response = jsonify({"message": f"mode must be one of {list(self.modes)}"})
                response.status_code = 400
                return response
            self.value = mode
        return jsonify({"mode": self.value, "modes": list(self.modes), "enabled": chaos_enabled()})


def install(app: Flask, service_name: str, db) -> None:
    init_tracing(service_name)
    this_instance = instance_id(service_name)
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
        response.headers[INSTANCE_HEADER] = this_instance
        route = request.url_rule.rule if request.url_rule else "unmatched"
        if route in ("/health", "/debug/spans", "/metrics", "/debug/runtime"):
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
        return {"status": "ok", "service": service_name, "instance": this_instance}

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

    @app.get("/debug/runtime")
    def debug_runtime():
        return jsonify(runtime_info(service_name, this_instance))

    @app.post("/debug/crash")
    def debug_crash():
        if not chaos_enabled():
            return jsonify({"message": "Chaos endpoints are off (CHAOS_ENABLED is not 1)"}), 403
        # Exit just after the response is sent, like a crashed replica. No deregistration on
        # purpose: the registry has to notice the missing heartbeats by itself.
        threading.Timer(0.3, os._exit, [1]).start()
        return jsonify({"stopping": this_instance})

    public_url = os.environ.get("SERVICE_PUBLIC_URL")
    if public_url and is_serving_process(app):
        DISCOVERY.register(service_name, this_instance, public_url)
