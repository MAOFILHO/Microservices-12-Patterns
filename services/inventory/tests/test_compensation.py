"""Demo 14: compensation under timeouts and duplicate events.

A saga's release can arrive before its hold (the hold request was slow, the saga gave up and sent
a release), and the same release can arrive twice (the direct call timed out but went through,
and the event copy follows). Either way the stock must end up exactly as before the checkout.
"""
import pytest

from application import consumer, db, routes
from application.models import StockItem
from application.seed import seed_missing_stock

RID = "saga-0014-aaaa"


@pytest.fixture
def seeded(app):
    seed_missing_stock()
    return app


def _stock(product_id=1):
    return db.session.get(StockItem, product_id).to_json()


def _reserve(client, rid=RID, qty=2):
    return client.post("/api/inventory/reservations",
                       json={"reservation_id": rid, "order_id": 7, "items": [{"product_id": 1, "quantity": qty}]})


def _release(client, rid=RID):
    return client.post(f"/api/inventory/reservations/{rid}/release")


def _mode(client, monkeypatch, mode):
    monkeypatch.setenv("CHAOS_ENABLED", "1")
    return client.post("/api/inventory/chaos", json={"mode": mode})


@pytest.fixture(autouse=True)
def _fresh():
    """The switch and the counters live in memory for the whole test run: reset them per test."""
    consumer.counts.update(duplicates_skipped=0, not_handled=0)
    yield
    routes.SWITCH.value = "healthy"


def _counts(client):
    body = client.get("/api/inventory/events").get_json()
    return body["duplicates_skipped"], body["not_handled"]


def test_a_release_that_arrives_before_its_hold_refuses_the_late_hold(seeded, client):
    before = _stock()
    assert _release(client).get_json()["result"]["status"] == "RELEASED"  # nothing held yet
    late = _reserve(client)
    assert late.status_code == 200
    assert late.get_json()["result"]["status"] == "RELEASED"  # the late hold holds nothing
    assert _stock() == before


def test_a_release_sent_twice_returns_the_stock_once_and_counts_both_copies(seeded, client):
    before = _stock()
    _reserve(client)
    consumer.handle({"event_id": "evt-r1", "type": "StockReleaseRequested", "payload": {"reservation_id": RID}})
    late = _release(client)  # the direct call that timed out, landing after the event copy
    assert _stock() == before
    assert late.get_json()["result"]["releases_received"] == 2  # the page shows both copies arrived


def test_a_release_for_a_hold_never_seen_is_logged(seeded, client, caplog):
    with caplog.at_level("WARNING"):
        _release(client)
    assert RID in caplog.text


def test_a_release_id_must_look_like_a_hold_id(seeded, client):
    assert _release(client, "x").status_code == 400
    assert _release(client, "y" * 37).status_code == 400


def test_a_replayed_checkout_is_skipped_or_ignored_event_by_event(seeded, client):
    _reserve(client, qty=3)
    checkout = [{"event_id": f"evt-{t}", "type": t, "payload": {"reservation_id": RID}}
                for t in ("StockReserved", "PaymentCharged", "OrderConfirmed")]
    for event in checkout:
        consumer.handle(event)
    sold = _stock()
    for event in checkout:  # redelivered
        consumer.handle(event)
    assert _stock() == sold
    assert _counts(client) == (1, 4)  # OrderConfirmed skipped once; the other 2 are not inventory's, twice


def test_a_database_from_before_demo_14_gains_the_release_count(app):
    from sqlalchemy import inspect, text

    from application import create_app

    db.drop_all()
    db.session.execute(text("CREATE TABLE reservation (id VARCHAR(36) PRIMARY KEY, order_id INTEGER NOT NULL, "
                            "items JSON NOT NULL, status VARCHAR(10) NOT NULL, created_at DATETIME, updated_at DATETIME)"))
    db.session.commit()
    create_app("development")
    assert "releases_received" in {c["name"] for c in inspect(db.engine).get_columns("reservation")}


def test_slow_reserve_delays_only_the_hold(seeded, client, monkeypatch):
    slept = []
    monkeypatch.setattr(routes.time, "sleep", slept.append)
    assert _mode(client, monkeypatch, "slow_reserve").status_code == 200
    _release(client, "saga-other-1")
    assert slept == []
    _reserve(client)
    assert slept == [routes.SLOW_SECONDS]


def test_slow_release_delays_only_the_release(seeded, client, monkeypatch):
    slept = []
    monkeypatch.setattr(routes.time, "sleep", slept.append)
    _mode(client, monkeypatch, "slow_release")
    _reserve(client)
    assert slept == []
    _release(client)
    assert slept == [routes.SLOW_SECONDS]


def test_the_inventory_switch_is_off_unless_chaos_is_enabled(seeded, client, monkeypatch):
    monkeypatch.delenv("CHAOS_ENABLED", raising=False)
    assert client.post("/api/inventory/chaos", json={"mode": "slow_reserve"}).status_code == 403
    assert client.get("/api/inventory/chaos").get_json()["mode"] == "healthy"


def test_the_inventory_switch_rejects_an_unknown_mode(seeded, client, monkeypatch):
    assert _mode(client, monkeypatch, "broken").status_code == 400
