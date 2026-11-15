import time
from typing import Literal

from flask import Blueprint, jsonify, make_response, request
from pydantic import BaseModel, Field, ValidationError
from shop_common.flask_support import chaos_enabled

from . import db
from .models import Payment

payment_api = Blueprint("payment_api", __name__)

# Pattern 4 demo switch: "healthy", "failing" (every call returns 500) or "slow" (every call takes
# SLOW_SECONDS, longer than the order service waits). Held in memory: it is a lab switch, not data.
MODES = ("healthy", "failing", "slow")
SLOW_SECONDS = 3
_mode = {"value": "healthy"}


class ChargeRequest(BaseModel):
    order_id: int = Field(gt=0)
    amount_cents: int = Field(gt=0)
    # Pattern 8 demo: "decline" acts like a card the bank refuses. A decline is a normal business
    # answer (200, status DECLINED), not a failure, so it never trips the order service's breaker.
    simulate: Literal["approve", "decline"] = "approve"


@payment_api.before_request
def _apply_chaos():
    if request.endpoint == "payment_api.chaos":
        return None
    if _mode["value"] == "failing":
        return make_response(jsonify({"message": "Payment is failing (demo switch)"}), 500)
    if _mode["value"] == "slow":
        time.sleep(SLOW_SECONDS)
    return None


@payment_api.get("/api/payments")
def list_payments():
    return jsonify({"results": [p.to_json() for p in Payment.query.order_by(Payment.id.desc()).limit(50)]})


@payment_api.get("/api/payment/ping")
def ping():
    return jsonify({"status": "ok"})


@payment_api.post("/api/payment/charge")
def charge():
    raw = request.get_json(silent=True) or request.form.to_dict()
    try:
        data = ChargeRequest.model_validate(raw)
    except ValidationError as exc:
        return make_response(jsonify({"message": "Invalid request", "errors": exc.errors(include_url=False)}), 400)
    status = "DECLINED" if data.simulate == "decline" else "APPROVED"
    payment = Payment(order_id=data.order_id, amount_cents=data.amount_cents, status=status)
    db.session.add(payment)
    db.session.commit()
    return jsonify({"result": payment.to_json()})


@payment_api.route("/api/payment/chaos", methods=["GET", "POST"])
def chaos():
    if request.method == "POST":
        if not chaos_enabled():
            return make_response(jsonify({"message": "Chaos switches are off (CHAOS_ENABLED is not 1)"}), 403)
        mode = (request.get_json(silent=True) or request.form.to_dict()).get("mode")
        if mode not in MODES:
            return make_response(jsonify({"message": f"mode must be one of {list(MODES)}"}), 400)
        _mode["value"] = mode
    return jsonify({"mode": _mode["value"], "modes": list(MODES), "enabled": chaos_enabled()})
