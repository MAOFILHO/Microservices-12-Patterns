"""Seeds stock for the catalog's 24 sample products (ids 1-24) on start. Idempotent: it only adds
rows that are missing, so counts that changed through sales are never reset."""
from . import db
from .models import StockItem

CATALOG_SAMPLE_COUNT = 24
SAMPLE_STOCK = {1: 25, 2: 40, 3: 60, 4: 15, 5: 10, 6: 30} | {
    product_id: 20 for product_id in range(7, CATALOG_SAMPLE_COUNT + 1)
}


def seed_missing_stock() -> None:
    existing = {row.product_id for row in db.session.query(StockItem.product_id)}
    for product_id, on_hand in SAMPLE_STOCK.items():
        if product_id not in existing:
            db.session.add(StockItem(product_id=product_id, on_hand=on_hand, reserved=0))
    db.session.commit()
