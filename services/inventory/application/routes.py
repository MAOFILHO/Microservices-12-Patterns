import time

from flask import Blueprint, jsonify, make_response, request
from pydantic import BaseModel, Field, ValidationError
from shop_common.flask_support import DemoSwitch, chaos_enabled, switches_off

from . import consumer, db, stock
from .models import ConsumedEvent, Reservation, StockItem

inventory_api = Blueprint("inventory_api", __name__)

# Demo 14 switch: "slow_reserve" makes a hold land after the saga gave up on it (its timeout is
# 3 s), so the saga's release arrives first. "slow_release" makes the saga's direct release time
# out although it goes through, so the event copy arrives too. In memory: a lab switch, not data.
SWITCH = DemoSwitch("healthy", "slow_reserve", "slow_release")
SLOW_SECONDS = 6
_SLOWED = {"slow_reserve": "inventory_api.reserve", "slow_release": "inventory_api.release"}


@inventory_api.before_request
def _apply_chaos():
    if _SLOWED.get(SWITCH.value) == request.endpoint:
        time.sleep(SLOW_SECONDS)


@inventory_api.route("/api/inventory/chaos", methods=["GET", "POST"])
def chaos():
    return SWITCH.respond()


class Line(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class ReserveRequest(BaseModel):
    reservation_id: str = Field(min_length=8, max_length=36)
    order_id: int = Field(gt=0)
    items: list[Line] = Field(min_length=1)


@inventory_api.get("/api/inventory")
def list_stock():
    return jsonify({"results": [s.to_json() for s in StockItem.query.order_by(StockItem.product_id)]})


@inventory_api.get("/api/inventory/<int:product_id>")
def get_stock(product_id: int):
    item = db.session.get(StockItem, product_id)
    if item is None:
        return make_response(jsonify({"message": f"No stock record for product {product_id}"}), 404)
    return jsonify({"result": item.to_json()})


@inventory_api.post("/api/inventory/reservations")
def reserve():
    try:
        data = ReserveRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return make_response(jsonify({"message": "Invalid request", "errors": exc.errors(include_url=False)}), 400)
    try:
        reservation = stock.reserve(data.reservation_id, data.order_id, [line.model_dump() for line in data.items])
    except stock.OutOfStock as exc:
        return make_response(jsonify({"message": "Not enough stock", "short": exc.args[0]}), 409)
    return jsonify({"result": reservation.to_json()})


@inventory_api.post("/api/inventory/reservations/<reservation_id>/release")
def release(reservation_id: str):
    if not 8 <= len(reservation_id) <= 36:  # the same rule as a hold's id
        return make_response(jsonify({"message": "A hold id is 8 to 36 characters"}), 400)
    return jsonify({"result": stock.release(reservation_id).to_json()})


@inventory_api.get("/api/inventory/reservations")
def list_reservations():
    rows = Reservation.query.order_by(Reservation.updated_at.desc()).limit(20)
    return jsonify({"results": [r.to_json() for r in rows]})


@inventory_api.get("/api/inventory/events")
def consumed_events():
    rows = ConsumedEvent.query.order_by(ConsumedEvent.handled_at.desc()).limit(20)
    return jsonify({"results": [e.to_json() for e in rows], **consumer.counts})


class RestockRequest(BaseModel):
    quantity: int = Field(gt=0, le=1000)


@inventory_api.post("/api/inventory/<int:product_id>/restock")
def restock(product_id: int):
    """Demo and smoke-test helper: adds units on hand. Only with CHAOS_ENABLED=1 (make run)."""
    if not chaos_enabled():
        return switches_off()
    try:
        data = RestockRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return make_response(jsonify({"message": "Invalid request", "errors": exc.errors(include_url=False)}), 400)
    item = db.session.get(StockItem, product_id)
    if item is None:
        return make_response(jsonify({"message": f"No stock record for product {product_id}"}), 404)
    item.on_hand += data.quantity
    db.session.commit()
    return jsonify({"result": item.to_json()})
