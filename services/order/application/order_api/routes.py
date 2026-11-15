from flask import jsonify, make_response, request

from . import order_api_blueprint
from .. import db
from ..models import Order, OrderItem
from ..schemas import OrderAddItemRequest
from ..validation import validate_form
from .api.UserClient import UserClient


@order_api_blueprint.route("/api/orders", methods=["GET"])
def orders():
    return jsonify([o.to_json() for o in Order.query.all()])


@order_api_blueprint.route("/api/order/add-item", methods=["POST"])
def order_add_item():
    api_key = request.headers.get("Authorization")
    response = UserClient.get_user(api_key)
    if not response:
        return make_response(jsonify({"message": "Not logged in"}), 401)

    data, error = validate_form(OrderAddItemRequest, request.form)
    if error:
        return error

    user = response["result"]
    u_id = int(user["id"])

    known_order = Order.query.filter_by(user_id=u_id, is_open=True).first()
    if known_order is None:
        known_order = Order(user_id=u_id, is_open=True)
        known_order.items.append(OrderItem(data.product_id, data.qty))
    else:
        existing = next((i for i in known_order.items if i.product_id == data.product_id), None)
        if existing:
            existing.quantity += data.qty
        else:
            known_order.items.append(OrderItem(data.product_id, data.qty))

    db.session.add(known_order)
    db.session.commit()
    return jsonify({"result": known_order.to_json()})


@order_api_blueprint.route("/api/order", methods=["GET"])
def order():
    api_key = request.headers.get("Authorization")
    response = UserClient.get_user(api_key)
    if not response:
        return make_response(jsonify({"message": "Not logged in"}), 401)

    user = response["result"]
    open_order = Order.query.filter_by(user_id=user["id"], is_open=True).first()
    if open_order is None:
        return jsonify({"message": "No order found"})
    return jsonify({"result": open_order.to_json()})


@order_api_blueprint.route("/api/order/checkout", methods=["POST"])
def checkout():
    api_key = request.headers.get("Authorization")
    response = UserClient.get_user(api_key)
    if not response:
        return make_response(jsonify({"message": "Not logged in"}), 401)

    user = response["result"]
    order_model = Order.query.filter_by(user_id=user["id"], is_open=True).first()
    if order_model is None:
        return make_response(jsonify({"message": "No open order"}), 404)

    order_model.is_open = False
    db.session.add(order_model)
    db.session.commit()
    return jsonify({"result": order_model.to_json()})


# Pattern 1 demo: each service only has its own tables. This tries to read another service's
# table through the order service's own database connection, and reports what really happens.
# Table names come from a fixed allow-list, never from raw user input, so no SQL injection.
FOREIGN_TABLES = {"product": "catalog", "stock_item": "inventory", "payment": "payment", "user": "user"}


@order_api_blueprint.route("/api/order/isolation-test", methods=["GET"])
def isolation_test():
    from sqlalchemy import inspect, text

    table = request.args.get("table", "product")
    if table not in FOREIGN_TABLES:
        return make_response(jsonify({"message": f"table must be one of {sorted(FOREIGN_TABLES)}"}), 400)
    # Quote for the real dialect: double quotes on SQLite, backticks on MySQL.
    sql = f"SELECT COUNT(*) FROM {db.engine.dialect.identifier_preparer.quote(table)}"
    result = {
        "attempted": sql,
        "owner": FOREIGN_TABLES[table],
        "order_tables": sorted(inspect(db.engine).get_table_names()),
    }
    try:
        db.session.execute(text(sql))
        result.update(blocked=False, error=None)
    except Exception as exc:  # the expected outcome: the table does not exist in order_db
        db.session.rollback()
        result.update(blocked=True, error=str(getattr(exc, "orig", exc)))
    return jsonify(result)
