"""Consumer side of contract testing (pattern 11): what the order service needs from payment and
catalog, written down as Pact contracts in contracts/pacts/.

Each test runs the order service's real client code against a Pact mock server. The mock only
answers requests that match the contract, and the test fails if the client sends anything else.
The payment and catalog suites then replay these contracts against the real services.
"""
from pathlib import Path

import pytest
from pact import Pact, match

from application.order_api.api import clients

PACT_DIR = Path(__file__).resolve().parents[3] / "contracts" / "pacts"


@pytest.fixture(autouse=True)
def _closed_breaker():
    clients.BREAKER.close()
    yield
    clients.BREAKER.close()


def test_order_to_payment_contract(monkeypatch):
    pact = Pact("order", "payment").with_specification("V4")
    (
        pact.upon_receiving("a charge for an order")
        .given("payment is healthy")
        .with_request("POST", "/api/payment/charge")
        .with_body({"order_id": match.int(42), "amount_cents": match.int(2598), "idempotency_key": match.str("saga-42")},
                   "application/json")
        .will_respond_with(200)
        .with_body({"result": {
            "id": match.int(1),
            "order_id": match.int(42),
            "amount_cents": match.int(2598),
            "status": "APPROVED",
        }}, "application/json")
    )
    (
        pact.upon_receiving("a charge the bank declines")
        .given("payment is healthy")
        .with_request("POST", "/api/payment/charge")
        .with_body({"order_id": match.int(43), "amount_cents": match.int(899), "simulate": "decline",
                    "idempotency_key": match.str("saga-43")}, "application/json")
        .will_respond_with(200)
        .with_body({"result": {"id": match.int(2), "status": "DECLINED"}}, "application/json")
    )
    (
        pact.upon_receiving("a void for a charge that went through")
        .given("a charge exists", idempotency_key="saga-42")
        .with_request("POST", "/api/payment/charges/saga-42/void")
        .with_body({"order_id": match.int(42), "amount_cents": match.int(2598)}, "application/json")
        .will_respond_with(200)
        .with_body({"result": {"id": match.int(1), "status": match.str("APPROVED")}}, "application/json")
    )
    (
        pact.upon_receiving("a void for a charge payment never saw")
        .given("payment is healthy")
        .with_request("POST", "/api/payment/charges/saga-never-sent/void")
        .with_body({"order_id": match.int(44), "amount_cents": match.int(500)}, "application/json")
        .will_respond_with(200)
        .with_body({"result": {"id": match.int(3), "status": "VOIDED"}}, "application/json")
    )
    (
        pact.upon_receiving("a health check through the circuit breaker")
        .given("payment is healthy")
        .with_request("GET", "/api/payment/ping")
        .will_respond_with(200)
        .with_body({"status": "ok"}, "application/json")
    )
    with pact.serve() as server:
        monkeypatch.setitem(clients.STATIC_URLS, "payment", str(server.url).rstrip("/"))
        payment = clients.charge(42, 2598, idempotency_key="saga-42")
        assert payment["status"] == "APPROVED"
        assert payment["amount_cents"] == 2598
        assert clients.charge(43, 899, "decline", idempotency_key="saga-43")["status"] == "DECLINED"
        assert clients.void_charge("saga-42", 42, 2598)["status"] == "APPROVED"
        assert clients.void_charge("saga-never-sent", 44, 500)["status"] == "VOIDED"
        assert clients.call_payment("GET", "/api/payment/ping").json() == {"status": "ok"}
    pact.write_file(PACT_DIR, overwrite=True)


def test_order_to_catalog_contract(monkeypatch):
    pact = Pact("order", "catalog").with_specification("V4")
    (
        pact.upon_receiving("a request for every product and its price")
        .given("products exist")
        .with_request("GET", "/api/products")
        .will_respond_with(200)
        .with_body({"results": match.each_like({"id": match.int(1), "price": match.int(1299)}, min=1)}, "application/json")
    )
    with pact.serve() as server:
        monkeypatch.setitem(clients.STATIC_URLS, "catalog", str(server.url).rstrip("/"))
        assert clients.product_prices() == {1: 1299}
    pact.write_file(PACT_DIR, overwrite=True)


def test_order_to_inventory_contract(monkeypatch):
    pact = Pact("order", "inventory").with_specification("V4")
    rid = "3f0c1d2e-0000-4000-8000-000000000001"
    (
        pact.upon_receiving("a stock hold for a checkout")
        .given("product 1 has stock")
        .with_request("POST", "/api/inventory/reservations")
        # Exact request bodies (no matchers): the mock tells this request and the next one apart
        # by their bodies, since both are POSTs to the same path.
        .with_body({"reservation_id": rid, "order_id": 42, "items": [{"product_id": 1, "quantity": 2}]},
                   "application/json")
        .will_respond_with(200)
        .with_body({"result": {"reservation_id": match.str(rid), "status": "RESERVED"}}, "application/json")
    )
    (
        pact.upon_receiving("a stock hold that is more than inventory has")
        .given("product 1 has stock")
        .with_request("POST", "/api/inventory/reservations")
        .with_body({"reservation_id": "3f0c1d2e-0000-4000-8000-000000000002", "order_id": 43,
                    "items": [{"product_id": 1, "quantity": 100000}]}, "application/json")
        .will_respond_with(409)
        .with_body({"short": match.each_like({"product_id": match.int(1), "available": match.int(25)}, min=1)},
                   "application/json")
    )
    (
        pact.upon_receiving("a release of a stock hold")
        .given("a stock hold exists", reservation_id=rid)
        .with_request("POST", f"/api/inventory/reservations/{rid}/release")
        .will_respond_with(200)
        .with_body({"result": {"reservation_id": rid, "status": "RELEASED"}}, "application/json")
    )
    with pact.serve() as server:
        monkeypatch.setitem(clients.STATIC_URLS, "inventory", str(server.url).rstrip("/"))
        assert clients.reserve_stock(rid, 42, [{"product_id": 1, "quantity": 2}])["status"] == "RESERVED"
        with pytest.raises(clients.OutOfStock):
            clients.reserve_stock("3f0c1d2e-0000-4000-8000-000000000002", 43, [{"product_id": 1, "quantity": 100000}])
        assert clients.release_stock(rid)["status"] == "RELEASED"
    pact.write_file(PACT_DIR, overwrite=True)
