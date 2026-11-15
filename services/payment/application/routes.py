from flask import Blueprint, jsonify, make_response, request
from pydantic import BaseModel, Field, ValidationError

from . import db
from .models import Payment

payment_api = Blueprint("payment_api", __name__)


class ChargeRequest(BaseModel):
    order_id: int = Field(gt=0)
    amount_cents: int = Field(gt=0)


@payment_api.get("/api/payments")
def list_payments():
    return jsonify({"results": [p.to_json() for p in Payment.query.order_by(Payment.id.desc()).limit(50)]})


@payment_api.post("/api/payment/charge")
def charge():
    try:
        data = ChargeRequest.model_validate(request.form.to_dict())
    except ValidationError as exc:
        return make_response(jsonify({"message": "Invalid request", "errors": exc.errors(include_url=False)}), 400)
    payment = Payment(order_id=data.order_id, amount_cents=data.amount_cents, status="APPROVED")
    db.session.add(payment)
    db.session.commit()
    return jsonify({"result": payment.to_json()})
