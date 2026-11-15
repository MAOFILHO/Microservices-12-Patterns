"""Provider side of pattern 11: inventory replays the order service's contract against itself."""
from pathlib import Path

from shop_common.contract_testing import verify_provider

PACT_DIR = Path(__file__).resolve().parents[3] / "contracts" / "pacts"
HOLD_ID = "3f0c1d2e-0000-4000-8000-000000000001"


def test_inventory_honours_the_order_services_contract(app):
    from application import db, stock
    from application.models import Reservation
    from application.seed import seed_stock_if_empty

    seed_stock_if_empty()
    # Pact calls the state handlers on another thread. End this thread's transaction first, or
    # SQLite's write lock makes the handlers wait forever.
    db.session.commit()
    db.session.remove()

    def no_hold_yet() -> None:
        with app.app_context():
            if db.session.get(Reservation, HOLD_ID) is not None:
                stock.release(HOLD_ID)
                db.session.delete(db.session.get(Reservation, HOLD_ID))
                db.session.commit()
            db.session.remove()

    def hold_exists() -> None:
        no_hold_yet()
        with app.app_context():
            stock.reserve(HOLD_ID, 42, [{"product_id": 1, "quantity": 2}])
            db.session.remove()

    verify_provider(app, provider="inventory", consumer="order",
                    states={"product 1 has stock": no_hold_yet, "a stock hold exists": hold_exists}, pact_dir=PACT_DIR)
