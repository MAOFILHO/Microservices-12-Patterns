"""Live demo endpoints for the pattern pages (patterns 1, 2, 5 and 6).

Each one calls real services and reports exactly what came back, including failures.
"""
import asyncio
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from prometheus_client.parser import text_string_to_metric_families

from shop_common.telemetry import SPAN_STORE, current_trace_id

from .. import config
from ..observability import upstream_headers

router = APIRouter(tags=["patterns"])


async def _call(client: httpx.AsyncClient, service: str, path: str, request: Request, calls: list[dict],
                base: str | None = None) -> httpx.Response | None:
    """GET one service, recording service, path, status and duration for the demo panel."""
    started = time.perf_counter()
    try:
        response = await client.get(f"{base or config.url_for(service)}{path}", headers=upstream_headers(request))
        status = response.status_code
    except httpx.HTTPError as exc:
        response, status = None, f"unreachable ({exc.__class__.__name__})"
    calls.append({"service": service, "path": path, "status": status,
                  "ms": round((time.perf_counter() - started) * 1000, 1)})
    return response


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=config.UPSTREAM_TIMEOUT_SECONDS)


# --- Pattern 1: Database per Service ---------------------------------------------------------

@router.get("/api/patterns/databases")
async def databases(request: Request):
    calls: list[dict] = []
    async with _client() as client:
        names = list(config.SERVICE_BASE_URLS)
        responses = await asyncio.gather(*(_call(client, n, "/health/db", request, calls) for n in names))
    results = []
    for name, response in zip(names, responses):
        if response is not None and response.status_code == 200:
            results.append({**response.json(), "reachable": True})
        else:
            results.append({"service": name, "reachable": False})
    return {"services": results}


@router.get("/api/patterns/isolation-test")
async def isolation_test(request: Request, table: str = "product"):
    calls: list[dict] = []
    async with _client() as client:
        response = await _call(client, "order", f"/api/order/isolation-test?table={table}", request, calls)
    if response is None:
        return JSONResponse({"message": "order service is unreachable"}, status_code=503)
    return JSONResponse(response.json(), status_code=response.status_code)


# --- Pattern 2: Bounded Context -----------------------------------------------------------------

@router.get("/api/patterns/bounded-context/{product_id}")
async def bounded_context(product_id: int, request: Request):
    """The same product as two contexts see it: Catalog (what we sell) and Inventory (how many)."""
    calls: list[dict] = []
    async with _client() as client:
        catalog_resp, inventory_resp = await asyncio.gather(
            _call(client, "catalog", "/api/products", request, calls),
            _call(client, "inventory", f"/api/inventory/{product_id}", request, calls),
        )
    catalog_view = None
    if catalog_resp is not None and catalog_resp.status_code == 200:
        catalog_view = next((p for p in catalog_resp.json()["results"] if p["id"] == product_id), None)
    inventory_view = inventory_resp.json().get("result") if inventory_resp is not None and inventory_resp.status_code == 200 else None
    return {"product_id": product_id, "catalog": catalog_view, "inventory": inventory_view, "calls": calls}


# --- Pattern 5: API Gateway aggregation ----------------------------------------------------------

@router.get("/api/order-summary")
async def order_summary(request: Request):
    """One browser call, four service calls: who you are, your cart, product details, stock.

    The user and cart calls run first (the cart says which products matter), then catalog and
    inventory run in parallel.
    """
    calls: list[dict] = []
    async with _client() as client:
        user_resp, cart_resp = await asyncio.gather(
            _call(client, "user", "/api/user", request, calls),
            _call(client, "order", "/api/order", request, calls),
        )
        if user_resp is None or user_resp.status_code != 200:
            return JSONResponse({"message": "Not logged in", "calls": calls}, status_code=401)
        cart = (cart_resp.json().get("result") if cart_resp is not None and cart_resp.status_code == 200 else None) or {"items": []}
        catalog_resp, stock_resp = await asyncio.gather(
            _call(client, "catalog", "/api/products", request, calls),
            _call(client, "inventory", "/api/inventory", request, calls),
        )

    products = {p["id"]: p for p in (catalog_resp.json()["results"] if catalog_resp is not None and catalog_resp.status_code == 200 else [])}
    stock = {s["product_id"]: s for s in (stock_resp.json()["results"] if stock_resp is not None and stock_resp.status_code == 200 else [])}
    lines = []
    for item in cart["items"]:
        product = products.get(item["product_id"], {})
        lines.append({
            "product_id": item["product_id"],
            "name": product.get("name"),
            "unit_price_cents": product.get("price"),
            "quantity": item["quantity"],
            "available": stock.get(item["product_id"], {}).get("available"),
        })
    return {
        "user": {"username": user_resp.json()["result"]["username"]},
        "lines": lines,
        "total_cents": sum((line["unit_price_cents"] or 0) * line["quantity"] for line in lines),
        "calls": calls,
        "request_id": request.state.request_id,
        "trace_id": current_trace_id(),
    }


# --- Pattern 6: Observability -------------------------------------------------------------------

@router.get("/api/observability/trace/{trace_id}")
async def trace_waterfall(trace_id: str, request: Request):
    """Stitches one trace's spans from the gateway and every service into a single list."""
    calls: list[dict] = []
    async with _client() as client:
        # Every instance, not just one: the trace may have passed through either order replica.
        targets = [(n, url) for n in config.SERVICE_BASE_URLS for url in config.urls_for(n)]
        responses = await asyncio.gather(
            *(_call(client, n, f"/debug/spans?trace_id={trace_id}", request, calls, base=url) for n, url in targets)
        )
    spans = list(SPAN_STORE.by_trace(trace_id))
    for response in responses:
        if response is not None and response.status_code == 200:
            spans.extend(response.json()["spans"])
    spans.sort(key=lambda s: s["start_ns"])
    return {"trace_id": trace_id, "spans": spans}


@router.get("/api/observability/metrics")
async def metrics_summary(request: Request):
    """Total requests and average latency per service, read from each service's /metrics."""
    calls: list[dict] = []
    async with _client() as client:
        targets = [(n, url) for n in config.SERVICE_BASE_URLS for url in config.urls_for(n)]
        responses = await asyncio.gather(*(_call(client, n, "/metrics", request, calls, base=url) for n, url in targets))
    by_service: dict[str, list[httpx.Response]] = {n: [] for n in config.SERVICE_BASE_URLS}
    for (name, _url), response in zip(targets, responses):
        if response is not None and response.status_code == 200:
            by_service[name].append(response)
    summary = []
    for name, ok_responses in by_service.items():  # replicas are summed into one row per service
        if not ok_responses:
            summary.append({"service": name, "reachable": False})
            continue
        requests_total, latency_sum, latency_count, errors = 0.0, 0.0, 0.0, 0.0
        for family in (f for r in ok_responses for f in text_string_to_metric_families(r.text)):
            for sample in family.samples:
                if sample.name == "shop_http_requests_total":
                    requests_total += sample.value
                    if sample.labels.get("status", "").startswith("5"):
                        errors += sample.value
                elif sample.name == "shop_http_request_duration_seconds_sum":
                    latency_sum += sample.value
                elif sample.name == "shop_http_request_duration_seconds_count":
                    latency_count += sample.value
        summary.append({
            "service": name,
            "reachable": True,
            "instances": len(ok_responses),
            "requests": int(requests_total),
            "errors_5xx": int(errors),
            "avg_ms": round(latency_sum / latency_count * 1000, 1) if latency_count else None,
        })
    return {"services": summary}
