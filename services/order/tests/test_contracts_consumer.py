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
        .with_body({"order_id": match.int(42), "amount_cents": match.int(2598)}, "application/json")
        .will_respond_with(200)
        .with_body({"result": {
            "id": match.int(1),
            "order_id": match.int(42),
            "amount_cents": match.int(2598),
            "status": "APPROVED",
        }}, "application/json")
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
        payment = clients.charge(42, 2598)
        assert payment["status"] == "APPROVED"
        assert payment["amount_cents"] == 2598
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
