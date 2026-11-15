"""Seeds stock for the catalog's 6 sample products (ids 1-6) on first local start. Idempotent."""
from . import db
from .models import StockItem

SAMPLE_STOCK = {1: 25, 2: 40, 3: 60, 4: 15, 5: 10, 6: 30}


def seed_stock_if_empty() -> None:
    if StockItem.query.first() is not None:
        return
    for product_id, on_hand in SAMPLE_STOCK.items():
        db.session.add(StockItem(product_id=product_id, on_hand=on_hand, reserved=0))
    db.session.commit()
