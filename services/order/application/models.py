from datetime import datetime, timezone

from . import db


def _utcnow():
    return datetime.now(timezone.utc)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)  # no FK — user table lives in another service
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")
    is_open = db.Column(db.Boolean, default=True)
    date_added = db.Column(db.DateTime, default=_utcnow)
    date_updated = db.Column(db.DateTime, onupdate=_utcnow)

    def to_json(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "is_open": self.is_open,
            "items": [i.to_json() for i in self.items],
        }


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, nullable=False)  # no FK — product table lives elsewhere
    quantity = db.Column(db.Integer, default=1)
    date_added = db.Column(db.DateTime, default=_utcnow)

    def __init__(self, product_id, quantity):
        self.product_id = product_id
        self.quantity = quantity

    def to_json(self):
        return {"product_id": self.product_id, "quantity": self.quantity}


class SagaStep(db.Model):
    """One line of a checkout saga's log (pattern 8). A saga is all rows sharing a saga_id."""

    __tablename__ = "saga_step"

    id = db.Column(db.Integer, primary_key=True)
    saga_id = db.Column(db.String(36), nullable=False, index=True)
    order_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    step = db.Column(db.String(30), nullable=False)    # price, reserve_stock, charge_payment, ...
    status = db.Column(db.String(12), nullable=False)  # done | failed | compensated | skipped
    detail = db.Column(db.String(300), nullable=True)
    at = db.Column(db.DateTime, default=_utcnow)

    def to_json(self):
        return {"step": self.step, "status": self.status, "detail": self.detail,
                "at": self.at.isoformat() if self.at else None}


class OutboxEvent(db.Model):
    """An event waiting to be published (pattern 7). Written in the same transaction as the change
    it describes; the relay in outbox.py publishes it to Redis and stamps published_at."""

    __tablename__ = "outbox_event"

    id = db.Column(db.String(36), primary_key=True)  # also the event id consumers dedupe on
    type = db.Column(db.String(40), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    published_at = db.Column(db.DateTime, nullable=True, index=True)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    last_error = db.Column(db.String(200), nullable=True)

    def to_json(self):
        return {
            "event_id": self.id,
            "type": self.type,
            "payload": self.payload,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "attempts": self.attempts,
            "last_error": self.last_error,
        }


class CheckoutLock(db.Model):
    """At most one checkout saga per order at a time. The primary key makes a second insert fail,
    even from the other replica, so a double click cannot hold stock or charge twice."""

    __tablename__ = "checkout_lock"

    order_id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    saga_id = db.Column(db.String(36), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
