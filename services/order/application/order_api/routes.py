import time

from flask import jsonify, make_response, request

from . import order_api_blueprint
from shop_common.flask_support import chaos_enabled

from .. import db, outbox, saga
from ..models import Order, OrderItem, OutboxEvent
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
    if known_order is not None and saga.is_pending(known_order.id):  # demo 13: the charge may have happened
        return make_response(jsonify({"message": saga.PENDING_MESSAGE, "pending": True}), 409)
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

    # Pattern 8 demo: {"simulate_decline": true} makes payment refuse the charge.
    options = request.get_json(silent=True) or request.form
    simulate = "decline" if str(options.get("simulate_decline", "")).lower() in ("1", "true", "yes") else "approve"
    if simulate == "decline" and not chaos_enabled():
        return make_response(jsonify({"message": "Demo switches are off (CHAOS_ENABLED is not 1)"}), 403)
    status, body = saga.run_checkout(order_model, u_id, simulate)
    return make_response(jsonify(body), status)


@order_api_blueprint.route("/api/order/sagas", methods=["GET"])
def sagas():
    u_id = _user_id()
    if u_id is None:
        return _not_logged_in()
    return jsonify({"results": saga.recent_sagas(u_id)})


# Pattern 7 demo: what is waiting in the outbox and what has been published. No personal data:
# events carry ids, quantities and amounts only.
@order_api_blueprint.route("/api/order/outbox", methods=["GET"])
def outbox_events():
    rows = OutboxEvent.query.order_by(OutboxEvent.created_at.desc()).limit(20).all()
    pending = OutboxEvent.query.filter(OutboxEvent.published_at.is_(None)).count()
    return jsonify({"pending": pending, "results": [r.to_json() for r in rows],
                    "bus_connected": outbox.is_connected()})


@order_api_blueprint.route("/debug/bus", methods=["POST"])
def bus_switch():
    if not chaos_enabled():
        return make_response(jsonify({"message": "Demo switches are off (CHAOS_ENABLED is not 1)"}), 403)
    connected = bool((request.get_json(silent=True) or {}).get("connected", True))
    outbox.set_connected(connected)
    return jsonify({"bus_connected": connected})


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
