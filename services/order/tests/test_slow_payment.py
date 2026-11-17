"""Demo 13: payment is slow in the middle of checkout. The charge call times out, so the saga
cannot know whether the customer was charged. It voids the charge's key before it undoes anything,
and payment answers how the charge now stands:

    APPROVED                 confirm the order (the customer paid, so they get it)
    DECLINED                 release the stock, 402 like any decline
    VOIDED                   release the stock (payment never took it, and now never will)
    PROCESSING / no answer   the order waits as pending; reconcile.resolve_pending() settles it later
"""
import pytest
import requests

from application import reconcile
from application.models import OutboxEvent, SagaStep
from application.order_api.api import clients

AUTH = {"Authorization": "Bearer test"}


@pytest.fixture
def payment(monkeypatch):
    """Payment that times out on charge. `status` is what a void answers."""
    state = {"status": "PROCESSING", "keys": [], "voids": [], "released": []}

    def timed_out(order_id, amount, simulate="approve", *, idempotency_key):
        state["keys"].append(idempotency_key)
        raise clients.PaymentUnavailable("failed")

    def void(key, order_id, amount_cents):
        state["voids"].append((key, amount_cents))
        if state["status"] == "UNREACHABLE":
            raise requests.ConnectTimeout("payment did not answer")
        return {"id": 9, "status": state["status"]}

    monkeypatch.setattr(clients, "current_user_id", lambda header: 1 if header else None)
    monkeypatch.setattr(clients, "product_prices", lambda: {1: 1299})
    monkeypatch.setattr(clients, "reserve_stock", lambda rid, oid, items: {})
    monkeypatch.setattr(clients, "release_stock", lambda rid: state["released"].append(rid) or {})
    monkeypatch.setattr(clients, "charge", timed_out)
    monkeypatch.setattr(clients, "void_charge", void)
    clients.BREAKER.close()
    return state


def _checkout(client):
    client.post("/api/order/add-item", data={"product_id": 1, "qty": 2}, headers=AUTH)
    return client.post("/api/order/checkout", json={}, headers=AUTH)


def _events():
    return [e.type for e in OutboxEvent.query.order_by(OutboxEvent.created_at)]


def _cart_is_open(client):
    return client.get("/api/order", headers=AUTH).get_json().get("result", {}).get("is_open") is True


def test_the_charge_and_the_void_carry_the_saga_id_as_the_key(client, payment):
    saga_id = _checkout(client).get_json()["saga_id"]
    assert payment["keys"] == [saga_id]
    assert payment["voids"] == [(saga_id, 2 * 1299)]


def test_a_timed_out_charge_that_went_through_confirms_the_order(client, payment):
    payment["status"] = "APPROVED"
    r = _checkout(client)
    assert r.status_code == 200
    assert payment["released"] == []  # the customer paid: never give their stock away
    assert _events() == ["StockReserved", "PaymentCharged", "OrderConfirmed"]
    assert not _cart_is_open(client)


@pytest.mark.parametrize("answer, http_status", [("VOIDED", 503), ("DECLINED", 402)])
def test_a_timed_out_charge_that_did_not_happen_releases_the_stock(client, payment, answer, http_status):
    payment["status"] = answer
    r = _checkout(client)
    assert r.status_code == http_status
    assert payment["released"] == [r.get_json()["saga_id"]]
    assert _events() == ["StockReserved", "CheckoutFailed"]
    assert "nothing was charged" in r.get_json()["message"].lower()
    assert _cart_is_open(client)


@pytest.mark.parametrize("answer", ["PROCESSING", "UNREACHABLE"])
def test_an_unknown_charge_leaves_the_order_pending_and_the_stock_held(client, payment, answer):
    payment["status"] = answer
    r = _checkout(client)
    assert r.status_code == 202
    assert r.get_json()["pending"] is True
    assert payment["released"] == []
    assert _events() == ["StockReserved"]  # no CheckoutFailed: nothing is decided yet
    assert SagaStep.query.order_by(SagaStep.id.desc()).first().status == "pending"


def test_a_pending_order_cannot_be_checked_out_or_changed(client, payment):
    _checkout(client)
    second = client.post("/api/order/checkout", json={}, headers=AUTH)
    assert second.status_code == 409
    changed = client.post("/api/order/add-item", data={"product_id": 1, "qty": 1}, headers=AUTH)
    assert changed.status_code == 409
    assert second.get_json()["message"] == changed.get_json()["message"]
    assert "waiting for payment" in changed.get_json()["message"]
    assert len(payment["keys"]) == 1  # no second charge attempt


def test_reconcile_confirms_a_pending_order_once_payment_approves(client, payment):
    _checkout(client)
    payment["status"] = "APPROVED"
    assert reconcile.resolve_pending() == 1
    assert _events() == ["StockReserved", "PaymentCharged", "OrderConfirmed"]
    assert payment["released"] == []
    assert not _cart_is_open(client)
    assert reconcile.resolve_pending() == 0  # settled once, never twice


def test_reconcile_releases_the_stock_when_payment_voided_the_charge(client, payment):
    saga_id = _checkout(client).get_json()["saga_id"]
    payment["status"] = "VOIDED"
    assert reconcile.resolve_pending() == 1
    assert payment["released"] == [saga_id]
    assert _events() == ["StockReserved", "CheckoutFailed"]
    assert _cart_is_open(client)
    payment["status"] = "APPROVED"  # the cart can be checked out again
    assert client.post("/api/order/checkout", json={}, headers=AUTH).status_code == 200


def test_reconcile_leaves_an_order_pending_while_payment_still_has_no_answer(client, payment):
    _checkout(client)
    payment["status"] = "UNREACHABLE"
    assert reconcile.resolve_pending() == 0
    assert _events() == ["StockReserved"]


def test_the_saga_history_shows_a_pending_checkout(client, payment):
    _checkout(client)
    assert client.get("/api/order/sagas", headers=AUTH).get_json()["results"][0]["outcome"] == "pending"


def test_reconcile_commits_its_claim_before_it_calls_inventory(client, payment, monkeypatch):
    """The release is an HTTP call: the other replica must not wait on this one's database lock."""
    from application.models import PendingPayment

    _checkout(client)
    payment["status"] = "VOIDED"
    seen = []
    monkeypatch.setattr(clients, "release_stock", lambda rid: seen.append(_claim_is_committed()) or {})
    reconcile.resolve_pending()
    assert seen == [True]
    assert PendingPayment.query.count() == 0


def _claim_is_committed() -> bool:
    from sqlalchemy import text

    from application import db

    with db.engine.connect() as other:  # a second connection sees only committed rows
        return other.execute(text("SELECT COUNT(*) FROM pending_payment")).scalar() == 0
