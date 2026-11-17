"""Provider side of pattern 11: payment replays the order service's contract against itself.

If payment renames or drops a field the order service relies on (for example amount_cents),
this test fails, so CI turns red before the change can break checkout.
"""
from pathlib import Path

from shop_common.contract_testing import verify_provider

PACT_DIR = Path(__file__).resolve().parents[3] / "contracts" / "pacts"


def test_payment_honours_the_order_services_contract(app):
    from application import db, routes
    from application.models import Payment

    # Pact calls the state handlers on another thread: end this thread's transaction first (SQLite).
    db.session.commit()
    db.session.remove()

    def healthy() -> None:
        routes._mode["value"] = "healthy"

    def charge_exists() -> None:
        healthy()
        with app.app_context():
            if Payment.query.filter_by(idempotency_key="saga-42").first() is None:
                db.session.add(Payment(order_id=42, amount_cents=2598, status="APPROVED", idempotency_key="saga-42"))
                db.session.commit()
            db.session.remove()

    verify_provider(app, provider="payment", consumer="order",
                    states={"payment is healthy": healthy, "a charge exists": charge_exists}, pact_dir=PACT_DIR)
