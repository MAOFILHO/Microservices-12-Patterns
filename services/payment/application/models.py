from datetime import datetime, timezone

from . import db


def _utcnow():
    return datetime.now(timezone.utc)


class Payment(db.Model):
    __tablename__ = "payment"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, nullable=False, index=True)  # the order service's id; no cross-DB FK
    amount_cents = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # PROCESSING | APPROVED | DECLINED | VOIDED
    # Demo 13: the caller's key for this charge. A retry with the same key gets this row back
    # instead of a second charge. Unique, so two racing requests cannot both insert it.
    idempotency_key = db.Column(db.String(64), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_json(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "amount_cents": self.amount_cents,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
