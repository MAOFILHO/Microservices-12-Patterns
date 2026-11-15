"""The checkout saga (pattern 8) and the outbox relay (pattern 7), with every other service stubbed."""
import pytest
import requests

from application import outbox
from application.models import OutboxEvent, SagaStep
from application.order_api.api import clients

AUTH = {"Authorization": "Bearer test"}


@pytest.fixture
def calls(monkeypatch):
    log = []
    monkeypatch.setattr(clients, "current_user_id", lambda header: 1 if header else None)
    monkeypatch.setattr(clients, "product_prices", lambda: {1: 1299})
    monkeypatch.setattr(clients, "reserve_stock", lambda rid, oid, items: log.append(("reserve", rid)) or {})
    monkeypatch.setattr(clients, "release_stock", lambda rid: log.append(("release", rid)) or {})
    monkeypatch.setattr(clients, "charge", lambda oid, amount, simulate="approve": log.append(("charge", simulate)) or {
        "id": 9, "status": "DECLINED" if simulate == "decline" else "APPROVED"})
    clients.BREAKER.close()
    return log


def _checkout(client, **body):
    client.post("/api/order/add-item", data={"product_id": 1, "qty": 2}, headers=AUTH)
    return client.post("/api/order/checkout", json=body, headers=AUTH)


def _steps():
    return [(s.step, s.status) for s in SagaStep.query.order_by(SagaStep.id)]


def _events():
    return [e.type for e in OutboxEvent.query.order_by(OutboxEvent.created_at)]


def test_happy_path_confirms_and_queues_order_confirmed(client, calls):
    r = _checkout(client)
    assert r.status_code == 200
    assert _steps() == [("price", "done"), ("reserve_stock", "done"), ("charge_payment", "done"), ("confirm", "done")]
    assert _events() == ["OrderConfirmed"]
    event = OutboxEvent.query.one()
    assert event.payload["reservation_id"] == r.get_json()["saga_id"]  # inventory sells exactly this hold
    assert event.published_at is None  # nothing published inside the request


def test_declined_payment_releases_the_stock_and_keeps_the_cart(client, calls):
    r = _checkout(client, simulate_decline=True)
    assert r.status_code == 402
    assert [c[0] for c in calls] == ["reserve", "charge", "release"]
    assert _steps()[-2:] == [("charge_payment", "failed"), ("release_stock", "compensated")]
    assert _events() == ["CheckoutFailed"]
    assert client.get("/api/order", headers=AUTH).get_json()["result"]["is_open"] is True


def test_out_of_stock_stops_before_payment(client, calls, monkeypatch):
    def short(rid, oid, items):
        raise clients.OutOfStock([{"product_id": 1, "wanted": 2, "available": 0}])

    monkeypatch.setattr(clients, "reserve_stock", short)
    r = _checkout(client)
    assert r.status_code == 409
    assert not any(c[0] == "charge" for c in calls)


def test_release_falls_back_to_an_event_when_inventory_is_down(client, calls, monkeypatch):
    def down(rid):
        raise requests.ConnectionError("inventory down")

    monkeypatch.setattr(clients, "release_stock", down)
    _checkout(client, simulate_decline=True)
    assert _events() == ["StockReleaseRequested", "CheckoutFailed"]


def test_saga_history_is_per_user(client, calls):
    _checkout(client, simulate_decline=True)
    sagas = client.get("/api/order/sagas", headers=AUTH).get_json()["results"]
    assert sagas[0]["outcome"] == "compensated"


class FakeBus:
    def __init__(self):
        self.sent = []

    def xadd(self, stream, fields, **kwargs):
        self.sent.append(fields["type"])


def test_relay_publishes_pending_events_once(client, calls):
    _checkout(client)
    bus = FakeBus()
    assert outbox.publish_pending(bus, "order-test") == 1
    assert outbox.publish_pending(bus, "order-test") == 0
    assert bus.sent == ["OrderConfirmed"]


def test_events_wait_while_the_bus_is_down(client, calls):
    _checkout(client)
    outbox.set_connected(False)
    try:
        assert outbox.publish_pending(FakeBus(), "order-test") == 0
        assert client.get("/api/order/outbox").get_json()["pending"] == 1
        assert OutboxEvent.query.one().attempts == 1
    finally:
        outbox.set_connected(True)
    assert outbox.publish_pending(FakeBus(), "order-test") == 1
