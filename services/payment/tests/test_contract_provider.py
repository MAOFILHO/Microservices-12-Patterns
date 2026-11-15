"""Provider side of pattern 11: payment replays the order service's contract against itself.

If payment renames or drops a field the order service relies on (for example amount_cents),
this test fails, so CI turns red before the change can break checkout.
"""
from pathlib import Path

from shop_common.contract_testing import verify_provider

PACT_DIR = Path(__file__).resolve().parents[3] / "contracts" / "pacts"


def test_payment_honours_the_order_services_contract(app):
    from application import routes

    def healthy() -> None:
        routes._mode["value"] = "healthy"

    verify_provider(app, provider="payment", consumer="order", states={"payment is healthy": healthy}, pact_dir=PACT_DIR)
