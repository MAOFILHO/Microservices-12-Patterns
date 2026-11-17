import time
from datetime import datetime, timedelta, timezone
from typing import Literal

from flask import Blueprint, jsonify, make_response, request
from pydantic import BaseModel, Field, ValidationError
from shop_common.flask_support import chaos_enabled
from sqlalchemy.exc import IntegrityError

from . import db
from .models import Payment

payment_api = Blueprint("payment_api", __name__)

# Pattern 4 demo switch: "healthy", "failing" (every call returns 500) or "slow" (every call takes
# SLOW_SECONDS, longer than the order service waits). Held in memory: it is a lab switch, not data.
# The switch makes charging sick, not settling: void and the list always answer, so the demo 13
# page can show where the money is while payment is slow.
MODES = ("healthy", "failing", "slow")
SLOW_SECONDS = 3
_mode = {"value": "healthy"}
_ALWAYS_ANSWERS = {"payment_api.chaos", "payment_api.void", "payment_api.list_payments"}
# Demo 13: a charge still PROCESSING after this long lost its process (a crash or restart), so a
# void may cancel it. Far longer than any charge takes, slow mode included.
PROCESSING_LIMIT_SECONDS = 30


class VoidRequest(BaseModel):
    order_id: int = Field(gt=0)
    amount_cents: int = Field(gt=0)


class ChargeRequest(VoidRequest):
    # Pattern 8 demo: "decline" acts like a card the bank refuses. A decline is a normal business
    # answer (200, status DECLINED), not a failure, so it never trips the order service's breaker.
    simulate: Literal["approve", "decline"] = "approve"
    # Demo 13: one key per checkout attempt, sent again on every retry of that attempt.
    idempotency_key: str = Field(min_length=1, max_length=64)


@payment_api.before_request
def _apply_chaos():
    if request.endpoint in _ALWAYS_ANSWERS:
        return None
    if _mode["value"] == "failing":
        return make_response(jsonify({"message": "Payment is failing (demo switch)"}), 500)
    if _mode["value"] == "slow" and request.endpoint != "payment_api.charge":  # charge() is slow itself
        time.sleep(SLOW_SECONDS)
    return None


@payment_api.get("/api/payments")
def list_payments():
    return jsonify({"results": [p.to_json() for p in Payment.query.order_by(Payment.id.desc()).limit(50)]})


@payment_api.get("/api/payment/ping")
def ping():
    return jsonify({"status": "ok"})


def _invalid(exc: ValidationError):
    return make_response(jsonify({"message": "Invalid request", "errors": exc.errors(include_url=False)}), 400)


def _record(key: str, data: VoidRequest, status: str) -> tuple[Payment, bool]:
    """The row for this key: the existing one, or a new one with this status. True if new."""
    payment = Payment.query.filter_by(idempotency_key=key).first()
    if payment is not None:
        return payment, False
    db.session.add(Payment(order_id=data.order_id, amount_cents=data.amount_cents, status=status, idempotency_key=key))
    try:
        db.session.commit()
    except IntegrityError:  # another request with this key got there first: use its row
        db.session.rollback()
        return Payment.query.filter_by(idempotency_key=key).one(), False
    return Payment.query.filter_by(idempotency_key=key).one(), True


def _finish(payment: Payment, status: str) -> Payment:
    """PROCESSING -> status, only if nothing (a void) changed the row meanwhile."""
    Payment.query.filter_by(id=payment.id, status="PROCESSING").update({"status": status})
    db.session.commit()
    db.session.refresh(payment)
    return payment


@payment_api.post("/api/payment/charge")
def charge():
    raw = request.get_json(silent=True) or request.form.to_dict()
    try:
        data = ChargeRequest.model_validate(raw)
    except ValidationError as exc:
        return _invalid(exc)
    # Demo 13: the charge is recorded as PROCESSING before the slow part, so a void sent while it
    # runs sees it in flight. A retry with the same key gets this row back, never a new charge.
    payment, created = _record(data.idempotency_key, data, "PROCESSING")
    if not created:
        if (payment.order_id, payment.amount_cents) != (data.order_id, data.amount_cents):
            return make_response(jsonify({"message": "This key was already used for a different charge"}), 409)
        return jsonify({"result": payment.to_json()})
    if _mode["value"] == "slow":
        time.sleep(SLOW_SECONDS)
    return jsonify({"result": _finish(payment, "DECLINED" if data.simulate == "decline" else "APPROVED").to_json()})


@payment_api.post("/api/payment/charges/<key>/void")
def void(key: str):
    """Demo 13: the order service's check before it undoes anything. A charge that never arrived
    is recorded as VOIDED, so it can never be charged later; one whose process died is voided.
    Answers the charge as it now stands: APPROVED, DECLINED, VOIDED or still PROCESSING."""
    try:
        data = VoidRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return _invalid(exc)
    payment, _ = _record(key, data, "VOIDED")
    created = payment.created_at.replace(tzinfo=payment.created_at.tzinfo or timezone.utc)
    if payment.status == "PROCESSING" and datetime.now(timezone.utc) - created > timedelta(seconds=PROCESSING_LIMIT_SECONDS):
        payment = _finish(payment, "VOIDED")
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
