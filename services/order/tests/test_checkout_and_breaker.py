"""Checkout and the payment circuit breaker (pattern 4), with no other service running.

The token check is replaced by a stub so these tests focus on the order service's own behaviour.
"""
import time

import pytest
import requests

from application.order_api.api import clients

AUTH = {"Authorization": "Bearer test"}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(clients, "current_user_id", lambda header: 1 if header else None)
    monkeypatch.setitem(clients.STATIC_URLS, "payment", "http://127.0.0.1:9")  # nothing listens on :9
    monkeypatch.setattr(clients, "product_prices", lambda: {1: 1299, 2: 899})
    # Inventory is not running in unit tests: holds always succeed unless a test says otherwise.
    monkeypatch.setattr(clients, "reserve_stock", lambda rid, order_id, items: {"status": "RESERVED"})
    monkeypatch.setattr(clients, "release_stock", lambda rid: {"status": "RELEASED"})
    clients.BREAKER.close()
    yield
    clients.BREAKER.close()


def _cart(client):
    client.post("/api/order/add-item", data={"product_id": 1, "qty": 2}, headers=AUTH)


def test_requests_without_a_token_are_rejected(client):
    assert client.get("/api/order").status_code == 401
    assert client.post("/api/order/checkout").status_code == 401


def test_breaker_opens_after_three_failures_then_fails_fast(client):
    outcomes = [client.get("/api/order/payment-check").get_json()["outcome"] for _ in range(3)]
    assert outcomes == ["failed", "failed", "failed"]
    assert clients.breaker_state()["state"] == "open"

    started = time.perf_counter()
    body = client.get("/api/order/payment-check").get_json()
    assert body["outcome"] == "short-circuited"
    assert time.perf_counter() - started < 0.05  # no network call was made
    assert 0 < body["breaker"]["retry_in_seconds"] <= clients.RESET_SECONDS


def test_checkout_keeps_the_cart_when_payment_is_down(client):
    _cart(client)
    r = client.post("/api/order/checkout", headers=AUTH)
    assert r.status_code == 503
    assert "Your cart is kept" in r.get_json()["message"]
    assert client.get("/api/order", headers=AUTH).get_json()["result"]["is_open"] is True


def test_checkout_charges_the_catalog_price_and_closes_the_order(client, monkeypatch):
    charged = {}

    def fake_charge(order_id, amount_cents, simulate="approve"):
        charged.update(order_id=order_id, amount_cents=amount_cents)
        return {"id": 1, "order_id": order_id, "amount_cents": amount_cents, "status": "APPROVED"}

    monkeypatch.setattr(clients, "charge", fake_charge)
    _cart(client)
    r = client.post("/api/order/checkout", headers=AUTH)
    assert r.status_code == 200
    assert charged["amount_cents"] == 2 * 1299
    assert r.get_json()["result"]["is_open"] is False


def test_client_errors_do_not_trip_the_breaker(monkeypatch):
    class Resp:
        status_code = 400

    monkeypatch.setattr(clients.requests, "request", lambda *a, **k: Resp())
    for _ in range(5):
        clients.call_payment("POST", "/api/payment/charge", {})
    assert clients.breaker_state()["state"] == "closed"


def test_catalog_down_means_no_charge(client, monkeypatch):
    def down():
        raise requests.ConnectionError("catalog down")

    monkeypatch.setattr(clients, "product_prices", down)
    _cart(client)
    assert client.post("/api/order/checkout", headers=AUTH).status_code == 503


def test_a_payment_timeout_never_claims_nothing_was_charged(client):
    """Payment at :9 refuses the call, which looks like a timeout: the charge state is unknown."""
    _cart(client)
    message = client.post("/api/order/checkout", headers=AUTH).get_json()["message"]
    assert "could not be confirmed" in message
    assert "nothing was charged" not in message


def test_an_open_breaker_does_say_nothing_was_charged(client):
    _cart(client)
    for _ in range(clients.FAIL_MAX):
        client.get("/api/order/payment-check")
    message = client.post("/api/order/checkout", headers=AUTH).get_json()["message"]
    assert "nothing was charged" in message
