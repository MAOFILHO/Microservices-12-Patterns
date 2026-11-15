import time

import requests
from flask import jsonify, make_response, request

from . import order_api_blueprint
from .. import db
from ..models import Order, OrderItem
from ..schemas import OrderAddItemRequest
from ..validation import validate_form
from .api import clients


def _not_logged_in():
    return make_response(jsonify({"message": "Not logged in"}), 401)


def _user_id() -> int | None:
    return clients.current_user_id(request.headers.get("Authorization"))


@order_api_blueprint.route("/api/orders", methods=["GET"])
def orders():
    return jsonify([o.to_json() for o in Order.query.all()])


@order_api_blueprint.route("/api/order/add-item", methods=["POST"])
def order_add_item():
    u_id = _user_id()
    if u_id is None:
        return _not_logged_in()

    data, error = validate_form(OrderAddItemRequest, request.form)
    if error:
        return error

    # The cart lives in the order database, not in this process (pattern 10): any replica sees it.
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
    u_id = _user_id()
    if u_id is None:
        return _not_logged_in()

    open_order = Order.query.filter_by(user_id=u_id, is_open=True).first()
    if open_order is None:
        return jsonify({"message": "No order found"})
    return jsonify({"result": open_order.to_json()})


@order_api_blueprint.route("/api/order/checkout", methods=["POST"])
def checkout():
    u_id = _user_id()
    if u_id is None:
        return _not_logged_in()

    order_model = Order.query.filter_by(user_id=u_id, is_open=True).first()
    if order_model is None:
        return make_response(jsonify({"message": "No open order"}), 404)

    try:
        prices = clients.product_prices()
    except requests.RequestException:
        return make_response(jsonify({"message": "The catalog is unavailable, so the order cannot be priced. Your cart is kept."}), 503)
    missing = [i.product_id for i in order_model.items if i.product_id not in prices]
    if missing:
        return make_response(jsonify({"message": f"Product(s) {missing} are no longer sold"}), 409)
    amount = sum(prices[i.product_id] * i.quantity for i in order_model.items)

    try:
        payment = clients.charge(order_model.id, amount)
    except clients.PaymentUnavailable as exc:
        state = clients.breaker_state()
        wait = f" Try again in {state['retry_in_seconds']:.0f} s." if state["retry_in_seconds"] else ""
        return make_response(jsonify({
            "message": f"Payment is unavailable right now, so nothing was charged. Your cart is kept.{wait}",
            "reason": exc.reason,
            "breaker": state,
        }), 503)

    order_model.is_open = False
    db.session.add(order_model)
    db.session.commit()
    return jsonify({"result": order_model.to_json(), "payment": payment})


# Pattern 4 demo: one cheap call to payment through the same breaker that protects checkout.
@order_api_blueprint.route("/api/order/payment-check", methods=["GET"])
def payment_check():
    started = time.perf_counter()
    try:
        clients.call_payment("GET", "/api/payment/ping")
        outcome, status = "ok", 200
    except clients.PaymentUnavailable as exc:
        outcome, status = ("short-circuited" if exc.reason == "open" else "failed"), 503
    body = {"outcome": outcome, "ms": round((time.perf_counter() - started) * 1000, 1), "breaker": clients.breaker_state()}
    return make_response(jsonify(body), status)


@order_api_blueprint.route("/api/order/breaker", methods=["GET"])
def breaker():
    return jsonify(clients.breaker_state())


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
