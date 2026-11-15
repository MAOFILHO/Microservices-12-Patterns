import pytest
from pydantic import ValidationError

from application.models import Order, OrderItem
from application.schemas import OrderAddItemRequest


def test_order_has_no_direct_user_fk(app):
    """order-service's Order model intentionally has no ForeignKey to a user
    table — it doesn't own that data. See application/models.py."""
    from application import db

    with app.app_context():
        order = Order(user_id=42, is_open=True)
        order.items.append(OrderItem(1, 2))
        db.session.add(order)
        db.session.commit()

        assert order.to_json()["user_id"] == 42
        assert order.to_json()["items"] == [{"product_id": 1, "quantity": 2}]


def test_order_add_item_rejects_non_positive_qty():
    with pytest.raises(ValidationError):
        OrderAddItemRequest(product_id=1, qty=0)


def test_order_add_item_accepts_valid_payload():
    req = OrderAddItemRequest(product_id=1, qty=3)
    assert req.qty == 3


def test_order_cannot_read_another_services_table(client):
    body = client.get("/api/order/isolation-test?table=product").get_json()
    assert body["blocked"] is True
    assert body["owner"] == "catalog"
    assert "product" not in body["order_tables"]


def test_isolation_test_rejects_unknown_tables(client):
    assert client.get("/api/order/isolation-test?table=sqlite_master").status_code == 400
