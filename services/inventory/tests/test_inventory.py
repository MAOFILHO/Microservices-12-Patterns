from application.models import StockItem
from application.seed import SAMPLE_STOCK, seed_missing_stock


def test_available_is_on_hand_minus_reserved():
    assert StockItem(product_id=1, on_hand=10, reserved=3).available == 7


def test_seed_is_idempotent(app):
    seed_missing_stock()
    seed_missing_stock()
    assert StockItem.query.count() == len(SAMPLE_STOCK)


def test_get_stock_and_404(client):
    seed_missing_stock()
    r = client.get("/api/inventory/1")
    assert r.status_code == 200
    assert r.get_json()["result"]["on_hand"] == SAMPLE_STOCK[1]
    assert client.get("/api/inventory/999").status_code == 404


def test_health_db_reports_only_own_tables(client):
    body = client.get("/health/db").get_json()
    assert body["service"] == "inventory"
    assert body["tables"] == ["consumed_event", "reservation", "stock_item"]
