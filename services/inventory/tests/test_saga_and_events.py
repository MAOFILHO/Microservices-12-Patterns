"""Stock holds for the checkout saga (pattern 8) and the OrderConfirmed handler (pattern 7)."""
import pytest

from application import consumer, db, stock
from application.models import StockItem
from application.seed import seed_stock_if_empty

RID = "saga-0001-aaaa"


@pytest.fixture
def seeded(app):
    seed_stock_if_empty()
    return app


def _stock(product_id):
    return db.session.get(StockItem, product_id).to_json()


def _reserve(client, rid=RID, qty=2):
    return client.post("/api/inventory/reservations",
                       json={"reservation_id": rid, "order_id": 7, "items": [{"product_id": 1, "quantity": qty}]})


def test_reserve_holds_stock_and_is_idempotent(seeded, client):
    assert _reserve(client).status_code == 200
    assert _reserve(client).status_code == 200  # a retried request holds nothing extra
    assert _stock(1) == {"product_id": 1, "on_hand": 25, "reserved": 2, "available": 23}


def test_reserve_is_all_or_nothing(seeded, client):
    r = client.post("/api/inventory/reservations", json={"reservation_id": RID, "order_id": 7, "items": [
        {"product_id": 1, "quantity": 1}, {"product_id": 5, "quantity": 99}]})
    assert r.status_code == 409
    assert r.get_json()["short"][0]["product_id"] == 5
    assert _stock(1)["reserved"] == 0


def test_release_returns_the_stock_once(seeded, client):
    _reserve(client)
    for _ in range(2):
        assert client.post(f"/api/inventory/reservations/{RID}/release").get_json()["result"]["status"] == "RELEASED"
    assert _stock(1)["reserved"] == 0


def test_order_confirmed_event_finishes_the_sale_once(seeded, client):
    _reserve(client, qty=3)
    event = {"event_id": "evt-1", "type": "OrderConfirmed", "payload": {"reservation_id": RID, "order_id": 7}}
    consumer.handle(event)
    consumer.handle(event)  # redelivered: must not sell twice
    assert _stock(1) == {"product_id": 1, "on_hand": 22, "reserved": 0, "available": 22}
    assert client.get("/api/inventory/events").get_json()["results"][0]["outcome"] == "reservation SOLD"


def test_released_reservation_cannot_be_sold_later(seeded, client):
    _reserve(client)
    stock.release(RID)
    consumer.handle({"event_id": "evt-2", "type": "OrderConfirmed", "payload": {"reservation_id": RID}})
    assert _stock(1)["on_hand"] == 25


def test_other_events_are_ignored(seeded):
    from application.models import ConsumedEvent

    consumer.handle({"event_id": "evt-3", "type": "CheckoutFailed", "payload": {}})
    assert ConsumedEvent.query.count() == 0


def test_restock_is_a_demo_switch(seeded, client, monkeypatch):
    monkeypatch.delenv("CHAOS_ENABLED", raising=False)
    assert client.post("/api/inventory/1/restock", json={"quantity": 5}).status_code == 403
    monkeypatch.setenv("CHAOS_ENABLED", "1")
    assert client.post("/api/inventory/1/restock", json={"quantity": 5}).get_json()["result"]["on_hand"] == 30
