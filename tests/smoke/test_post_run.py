"""Post-run smoke tests: run AFTER `make run`. Exercises the real register -> login ->
create product -> add to cart -> checkout flow, first against the services directly and then
through the gateway. Skips (rather than fails) when the stack is not up."""
import uuid

import httpx
import pytest

from service_table import FLASK_SERVICES, GATEWAY

URLS = {s.name: s.local_url for s in FLASK_SERVICES}
GATEWAY_URL = GATEWAY.local_url


def _is_up(url: str) -> bool:
    try:
        return httpx.get(f"{url}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def _checkout_flow(user_url: str, catalog_url: str, order_url: str) -> None:
    token = uuid.uuid4().hex[:8]
    username, email, password = f"user{token}", f"{token}@example.com", "secret123"

    r = httpx.post(f"{user_url}/user/create", data={"username": username, "email": email, "password": password})
    assert r.status_code == 200, r.text

    r = httpx.post(f"{user_url}/user/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    login_token = r.json()["token"]  # pattern 10: a signed token, no server session

    r = httpx.post(f"{catalog_url}/product/create", data={"name": f"P{token}", "slug": f"p{token}", "price": "1500"})
    assert r.status_code == 200, r.text
    product_id = r.json()["product"]["id"]

    headers = {"Authorization": f"Bearer {login_token}"}
    # Buy a seeded product: a product created a moment ago has no stock record in inventory, so the
    # saga's reserve step would (correctly) refuse it.
    assert product_id > 0
    httpx.post(f"{order_url}/inventory/1/restock", json={"quantity": 10})
    r = httpx.post(f"{order_url}/order/add-item", data={"product_id": 1, "qty": 2}, headers=headers)
    assert r.status_code == 200, r.text  # order verifies the token itself, no call to user

    r = httpx.post(f"{order_url}/order/checkout", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["is_open"] is False
    assert r.json()["payment"]["amount_cents"] == 2 * 1299  # priced by catalog, charged by payment


def test_services_full_flow_direct():
    if not all(_is_up(u) for u in URLS.values()):
        pytest.skip("services not all running — start them with `make run` first")
    _checkout_flow(*(f"{URLS[n]}/api" for n in ("user", "catalog", "order")))


def test_full_flow_through_gateway():
    if not _is_up(GATEWAY_URL) or not all(_is_up(u) for u in URLS.values()):
        pytest.skip("gateway or services not running — start them with `make run` first")
    shop = f"{GATEWAY_URL}/api/shop"
    # The gateway forwards /api/shop/<path> to /api/<path> on the owning service.
    _checkout_flow(shop, shop, shop)
    r = httpx.get(f"{shop}/products")
    assert r.status_code == 200
    assert "results" in r.json()


# --- M1 pattern demos (patterns 1, 2, 5, 6), through the gateway ---------------------------------

def _require_stack():
    if not _is_up(GATEWAY_URL) or not all(_is_up(u) for u in URLS.values()):
        pytest.skip("gateway or services not running — start them with `make run` first")


def test_each_service_owns_only_its_tables():
    _require_stack()
    services = {s["service"]: s for s in httpx.get(f"{GATEWAY_URL}/api/patterns/databases").json()["services"]}
    assert set(services) == set(URLS)
    assert services["catalog"]["tables"] == ["product"]
    assert services["inventory"]["tables"] == ["consumed_event", "reservation", "stock_item"]
    assert "product" not in services["order"]["tables"]


def test_order_service_cannot_read_catalog_table():
    _require_stack()
    body = httpx.get(f"{GATEWAY_URL}/api/patterns/isolation-test", params={"table": "product"}).json()
    assert body["blocked"] is True


def test_bounded_context_shows_two_views_of_one_product():
    _require_stack()
    body = httpx.get(f"{GATEWAY_URL}/api/patterns/bounded-context/1").json()
    assert "price" in body["catalog"] and "on_hand" not in body["catalog"]
    assert "on_hand" in body["inventory"] and "price" not in body["inventory"]


def test_one_request_is_traced_across_services():
    _require_stack()
    r = httpx.get(f"{GATEWAY_URL}/api/patterns/bounded-context/1")
    trace_id = r.headers["X-Trace-Id"]
    spans = httpx.get(f"{GATEWAY_URL}/api/observability/trace/{trace_id}").json()["spans"]
    assert {"gateway", "catalog", "inventory"} <= {s["service"] for s in spans}


# --- M2 pattern demos (patterns 10, 12, 4), through the gateway ----------------------------------

def _login_with_cart() -> dict:
    # Top up stock first, so repeated smoke runs never run product 1 out of stock.
    httpx.post(f"{GATEWAY_URL}/api/shop/inventory/1/restock", json={"quantity": 10})
    tag = uuid.uuid4().hex[:8]
    shop = f"{GATEWAY_URL}/api/shop"
    httpx.post(f"{shop}/user/create", data={"username": f"m2{tag}", "email": f"m2{tag}@example.com", "password": "secret123"})
    login_token = httpx.post(f"{shop}/user/login", data={"username": f"m2{tag}", "password": "secret123"}).json()["token"]
    headers = {"Authorization": f"Bearer {login_token}"}
    httpx.post(f"{shop}/order/add-item", data={"product_id": 1, "qty": 3}, headers=headers)
    return headers


def test_registry_lists_both_order_replicas():
    _require_stack()
    view = httpx.get(f"{GATEWAY_URL}/api/patterns/registry").json()
    assert view["mode"] == "registry"
    assert {i["instance_id"] for i in view["services"]["order"]} == {"order-5103", "order-5113"}
    assert set(view["services"]) >= set(URLS)


def test_any_replica_serves_the_same_cart():
    _require_stack()
    headers = _login_with_cart()
    seen, carts = set(), set()
    for _ in range(6):
        r = httpx.get(f"{GATEWAY_URL}/api/shop/order", headers=headers)
        assert r.status_code == 200, r.text
        seen.add(r.headers["X-Instance-Id"])
        carts.add(r.json()["result"]["items"][0]["quantity"])
    assert seen == {"order-5103", "order-5113"}
    assert carts == {3}


def test_gateway_rejects_a_bad_token_at_the_edge():
    _require_stack()
    r = httpx.get(f"{GATEWAY_URL}/api/shop/order", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert "gateway" in r.json()["message"]


def test_breaker_opens_when_payment_fails_and_closes_after_it_heals():
    _require_stack()
    import time

    api = f"{GATEWAY_URL}/api/patterns/breaker"
    assert httpx.post(f"{api}/payment-mode", json={"mode": "failing"}).status_code == 200
    try:
        for _ in range(6):  # 3 failures on each of the 2 order replicas
            httpx.get(f"{api}/call", timeout=10)
        states = {b["instance"]: b["state"] for b in httpx.get(f"{api}/state").json()["breakers"]}
        assert set(states.values()) == {"open"}, states
        r = httpx.get(f"{api}/call").json()
        assert r["outcome"] == "short-circuited"
        assert r["ms"] < 50
    finally:
        httpx.post(f"{api}/payment-mode", json={"mode": "healthy"})
    time.sleep(16)  # past the 15 s reset window
    outcomes = {httpx.get(f"{api}/call").json()["outcome"] for _ in range(2)}
    assert outcomes == {"ok"}
    assert {b["state"] for b in httpx.get(f"{api}/state").json()["breakers"]} == {"closed"}


# --- M3a pattern demos (patterns 8, 7, 9), through the gateway ----------------------------------

def _stock(product_id: int) -> dict:
    return next(s for s in httpx.get(f"{GATEWAY_URL}/api/shop/inventory").json()["results"] if s["product_id"] == product_id)


def _wait_for(condition, seconds: float = 8.0) -> bool:
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.5)
    return False


def test_saga_sale_holds_then_sells_through_the_event_bus():
    _require_stack()
    headers = _login_with_cart()  # 3 units of product 1
    before = _stock(1)
    r = httpx.post(f"{GATEWAY_URL}/api/shop/order/checkout", headers=headers, timeout=15)
    assert r.status_code == 200, r.text
    steps = httpx.get(f"{GATEWAY_URL}/api/shop/order/sagas", headers=headers).json()["results"][0]["steps"]
    assert [s["step"] for s in steps] == ["price", "reserve_stock", "charge_payment", "confirm"]
    # Inventory sells the hold when it reads OrderConfirmed from Redis, a moment later.
    assert _wait_for(lambda: _stock(1)["on_hand"] == before["on_hand"] - 3), _stock(1)
    assert _stock(1)["reserved"] == before["reserved"]


def test_declined_payment_is_compensated_and_stock_is_unchanged():
    _require_stack()
    headers = _login_with_cart()
    before = _stock(1)
    r = httpx.post(f"{GATEWAY_URL}/api/shop/order/checkout", json={"simulate_decline": True}, headers=headers, timeout=15)
    assert r.status_code == 402, r.text
    saga = httpx.get(f"{GATEWAY_URL}/api/shop/order/sagas", headers=headers).json()["results"][0]
    assert saga["outcome"] == "compensated"
    assert _stock(1) == before
    assert httpx.get(f"{GATEWAY_URL}/api/shop/order", headers=headers).json()["result"]["is_open"] is True


def test_events_wait_in_the_outbox_while_the_bus_is_down_then_drain():
    _require_stack()
    api = f"{GATEWAY_URL}/api/patterns/events"
    assert httpx.post(f"{api}/bus", json={"connected": False}).json()["replicas_switched"] == 2
    try:
        headers = _login_with_cart()
        before = _stock(1)
        assert httpx.post(f"{GATEWAY_URL}/api/shop/order/checkout", headers=headers, timeout=15).status_code == 200
        assert _wait_for(lambda: httpx.get(api).json()["outbox"]["pending"] >= 1)
        assert _stock(1)["reserved"] == before["reserved"] + 3  # held, not yet sold
    finally:
        httpx.post(f"{api}/bus", json={"connected": True})
    assert _wait_for(lambda: httpx.get(api).json()["outbox"]["pending"] == 0)
    assert _wait_for(lambda: _stock(1)["on_hand"] == before["on_hand"] - 3)


def test_every_process_reports_how_it_runs():
    _require_stack()
    processes = httpx.get(f"{GATEWAY_URL}/api/patterns/runtime").json()["processes"]
    assert len(processes) == 7  # gateway + 5 services, order twice
    assert all("uid" in p for p in processes)
