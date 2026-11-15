"""Prometheus metrics shared by every process: request count and latency per route.

Labels are kept low-cardinality on purpose: the route template (e.g. /api/product/<slug>), never
the raw URL, so one metric series does not appear per product slug.
"""
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter(
    "shop_http_requests_total", "HTTP requests handled", ["service", "method", "route", "status"]
)
LATENCY = Histogram(
    "shop_http_request_duration_seconds", "HTTP request latency", ["service", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)


def observe(service: str, method: str, route: str, status: int, seconds: float) -> None:
    REQUESTS.labels(service, method, route, str(status)).inc()
    LATENCY.labels(service, method, route).observe(seconds)


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
