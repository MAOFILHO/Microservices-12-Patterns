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
    api_key = r.json()["api_key"]

    r = httpx.post(f"{catalog_url}/product/create", data={"name": f"P{token}", "slug": f"p{token}", "price": "1500"})
    assert r.status_code == 200, r.text
    product_id = r.json()["product"]["id"]

    headers = {"Authorization": f"Basic {api_key}"}
    r = httpx.post(f"{order_url}/order/add-item", data={"product_id": product_id, "qty": 2}, headers=headers)
    assert r.status_code == 200, r.text  # order calls user internally to validate the api_key

    r = httpx.post(f"{order_url}/order/checkout", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["is_open"] is False


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
