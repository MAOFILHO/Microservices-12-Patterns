"""Provider side of pattern 11: catalog replays the order service's contract against itself."""
from pathlib import Path

from shop_common.contract_testing import verify_provider

PACT_DIR = Path(__file__).resolve().parents[3] / "contracts" / "pacts"


def test_catalog_honours_the_order_services_contract(app):
    from application.seed import seed_products_if_empty

    # Seed here, on the test's own thread and database session. The state handler then has nothing
    # left to do (doing database writes from Pact's callback thread deadlocks on SQLite).
    seed_products_if_empty()
    verify_provider(app, provider="catalog", consumer="order", states={"products exist": lambda: None}, pact_dir=PACT_DIR)
