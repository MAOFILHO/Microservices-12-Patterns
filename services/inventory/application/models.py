from . import db


class StockItem(db.Model):
    __tablename__ = "stock_item"

    # The catalog's product id. Not a foreign key: the product table lives in another service's
    # database, so referential integrity across services is a business rule, not a DB constraint.
    product_id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    on_hand = db.Column(db.Integer, nullable=False, default=0)
    reserved = db.Column(db.Integer, nullable=False, default=0)

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved

    def to_json(self):
        return {
            "product_id": self.product_id,
            "on_hand": self.on_hand,
            "reserved": self.reserved,
            "available": self.available,
        }


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


# Demo 14: the order id of a hold recorded only by its release (the hold itself never arrived).
NEVER_HELD = 0


class Reservation(db.Model):
    """Stock held for one checkout attempt (pattern 8). Keyed by the order service's saga id, so a
    retried request or a redelivered event finds the same row instead of holding stock twice."""

    __tablename__ = "reservation"

    id = db.Column(db.String(36), primary_key=True)  # the saga id
    order_id = db.Column(db.Integer, nullable=False, index=True)
    items = db.Column(db.JSON, nullable=False)  # [{"product_id": 1, "quantity": 2}]
    status = db.Column(db.String(10), nullable=False)  # RESERVED -> SOLD | RELEASED
    # Demo 14: how many release requests arrived (a direct call and its event copy can both come).
    releases_received = db.Column(db.Integer, nullable=True, default=0)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    def to_json(self):
        return {
            "reservation_id": self.id,
            "order_id": self.order_id,
            "items": self.items,
            "status": self.status,
            "releases_received": self.releases_received or 0,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ConsumedEvent(db.Model):
    """Every event inventory acted on (pattern 7). Also the dedupe record: an event id seen before
    is skipped, which makes handling idempotent under at-least-once delivery."""

    __tablename__ = "consumed_event"

    event_id = db.Column(db.String(36), primary_key=True)
    type = db.Column(db.String(40), nullable=False)
    reservation_id = db.Column(db.String(36), nullable=True)
    outcome = db.Column(db.String(120), nullable=False)
    handled_at = db.Column(db.DateTime, default=_utcnow)

    def to_json(self):
        return {
            "event_id": self.event_id,
            "type": self.type,
            "reservation_id": self.reservation_id,
            "outcome": self.outcome,
            "handled_at": self.handled_at.isoformat() if self.handled_at else None,
        }
