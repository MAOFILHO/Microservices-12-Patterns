"""Live demo endpoints for patterns 4 (Circuit Breaker), 7 (Event-Driven), 10 (Stateless Services)
and 12 (Service Discovery). The stop, break and bus switches work only with CHAOS_ENABLED=1 (make run)."""
import asyncio
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import config
from ..observability import upstream_headers

router = APIRouter(prefix="/api/patterns", tags=["patterns"])

_CHAOS_OFF = {"message": "Demo switches are off. Set CHAOS_ENABLED=1 (make run does this)."}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=config.UPSTREAM_TIMEOUT_SECONDS)


# --- Pattern 12: Service Discovery -------------------------------------------------------------

async def _registry_snapshot() -> dict | None:
    base = config.REGISTRY_URL
    if not base:
        return None
    try:
        async with _client() as client:
            response = await client.get(f"{base}/services")
        return response.json()
    except httpx.HTTPError:
        return None


@router.get("/registry")
async def registry():
    """What the registry knows right now. Without a registry, the gateway's static URL map."""
    snapshot = await _registry_snapshot()
    if snapshot is not None:
        return {"mode": "registry", **snapshot}
    services = {name: [{"instance_id": "static", "url": url, "last_heartbeat_s": None, "up_for_s": None}]
                for name, url in config.SERVICE_BASE_URLS.items()}
    return {"mode": "static" if not config.REGISTRY_URL else "registry-unreachable",
            "ttl_seconds": None, "services": services, "events": []}


@router.post("/replicas/{instance_id}/stop")
async def stop_replica(instance_id: str):
    """Stops one service process, as if it crashed. It does not say goodbye to the registry."""
    if not config.CHAOS_ENABLED:
        return JSONResponse(_CHAOS_OFF, status_code=403)
    snapshot = await _registry_snapshot()
    instances = [i for group in (snapshot or {}).get("services", {}).values() for i in group]
    target = next((i for i in instances if i["instance_id"] == instance_id), None)
    if target is None:
        return JSONResponse({"message": f"No live instance '{instance_id}' in the registry"}, status_code=404)
    try:
        async with _client() as client:
            response = await client.post(f"{target['url']}/debug/crash")
    except httpx.HTTPError as exc:
        return JSONResponse({"message": f"Could not reach {instance_id}: {exc.__class__.__name__}"}, status_code=502)
    return JSONResponse(response.json(), status_code=response.status_code)


# --- Pattern 4: Circuit Breaker ----------------------------------------------------------------

@router.get("/breaker/call")
async def breaker_call(request: Request):
    """One call from an order replica to payment, through that replica's breaker."""
    started = time.perf_counter()
    response = None
    async with _client() as client:
        for base in config.candidates("order"):  # skip a stopped replica, as the shop proxy does
            try:
                response = await client.get(f"{base}/api/order/payment-check", headers=upstream_headers(request))
                break
            except httpx.HTTPError:
                continue
    if response is None:
        return JSONResponse({"outcome": "order unreachable", "instance": None}, status_code=503)
    body = response.json()
    body.update(instance=response.headers.get("x-instance-id"),
                total_ms=round((time.perf_counter() - started) * 1000, 1))
    return JSONResponse(body, status_code=response.status_code)


@router.get("/breaker/state")
async def breaker_state(request: Request):
    """Each order replica's breaker (they do not share state), plus payment's demo switch."""
    async def one(url: str) -> dict:
        try:
            response = await client.get(f"{url}/api/order/breaker", headers=upstream_headers(request))
            return {"instance": response.headers.get("x-instance-id"), **response.json()}
        except httpx.HTTPError:
            return {"instance": url, "state": "unreachable"}

    async with _client() as client:
        breakers = await asyncio.gather(*(one(url) for url in config.urls_for("order")))
        try:
            mode = (await client.get(f"{config.url_for('payment')}/api/payment/chaos")).json()
        except httpx.HTTPError:
            mode = {"mode": "unreachable"}
    return {"breakers": sorted(breakers, key=lambda b: b["instance"] or ""), "payment": mode,
            "chaos_enabled": config.CHAOS_ENABLED}


class PaymentMode(BaseModel):
    mode: str


@router.post("/breaker/payment-mode")
async def set_payment_mode(body: PaymentMode):
    if not config.CHAOS_ENABLED:
        return JSONResponse(_CHAOS_OFF, status_code=403)
    try:
        async with _client() as client:
            response = await client.post(f"{config.url_for('payment')}/api/payment/chaos", json={"mode": body.mode})
    except httpx.HTTPError as exc:
        return JSONResponse({"message": f"payment unreachable ({exc.__class__.__name__})"}, status_code=503)
    return JSONResponse(response.json(), status_code=response.status_code)


# --- Pattern 7: Event-Driven Architecture ------------------------------------------------------

@router.get("/events")
async def events(request: Request):
    """Both ends of the bus: order's outbox (published or waiting) and what inventory acted on,
    plus current stock, so the page can show a hold turning into a sale."""
    async def get(service: str, path: str, base: str | None = None):
        try:
            response = await client.get(f"{base or config.url_for(service)}{path}", headers=upstream_headers(request))
            return response.json() if response.status_code == 200 else None
        except httpx.HTTPError:
            return None

    async with _client() as client:
        order_bases = config.urls_for("order")
        outbox, consumed, stock, reservations, *buses = await asyncio.gather(
            get("order", "/api/order/outbox"),
            get("inventory", "/api/inventory/events"),
            get("inventory", "/api/inventory"),
            get("inventory", "/api/inventory/reservations"),
            *(get("order", "/api/order/outbox", base=b) for b in order_bases),
        )
    return {
        "outbox": outbox,
        "consumed": consumed["results"] if consumed else None,
        "stock": stock["results"] if stock else None,
        "reservations": reservations["results"] if reservations else None,
        "bus_connected": [b["bus_connected"] for b in buses if b] or None,
        "chaos_enabled": config.CHAOS_ENABLED,
    }


class BusSwitch(BaseModel):
    connected: bool


@router.post("/events/bus")
async def set_bus(body: BusSwitch):
    """Disconnects (or reconnects) every order replica's outbox relay from the bus."""
    if not config.CHAOS_ENABLED:
        return JSONResponse(_CHAOS_OFF, status_code=403)
    async with _client() as client:
        results = await asyncio.gather(
            *(client.post(f"{base}/debug/bus", json={"connected": body.connected}) for base in config.urls_for("order")),
            return_exceptions=True,
        )
    switched = sum(1 for r in results if isinstance(r, httpx.Response) and r.status_code == 200)
    return {"bus_connected": body.connected, "replicas_switched": switched}


# --- Pattern 9: Containerization ---------------------------------------------------------------

@router.get("/runtime")
async def runtime(request: Request):
    """How every process runs: as root or not, in a container or not, which build (git SHA)."""
    from shop_common.runtime import runtime_info

    async def one(service: str, base: str) -> dict:
        try:
            response = await client.get(f"{base}/debug/runtime", headers=upstream_headers(request))
            return response.json()
        except (httpx.HTTPError, ValueError):
            return {"service": service, "instance": base, "unreachable": True}

    async with _client() as client:
        targets = [(n, url) for n in config.SERVICE_BASE_URLS for url in config.urls_for(n)]
        services = await asyncio.gather(*(one(n, url) for n, url in targets))
    return {"processes": [runtime_info("gateway", "gateway"), *services]}
