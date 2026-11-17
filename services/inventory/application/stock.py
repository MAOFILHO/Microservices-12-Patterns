"""Stock rules for the checkout saga (pattern 8) and the event consumer (pattern 7).

reserve:  available -> reserved      (saga step 1; all lines or none)
release:  reserved  -> available     (saga compensation; an unknown hold is recorded as RELEASED,
                                      so a hold that arrives late is refused: demo 14)
commit:   reserved  -> sold          (on OrderConfirmed: on hand goes down)

Each is idempotent: calling it again for the same reservation changes nothing.
"""
import logging

from sqlalchemy.exc import IntegrityError

from . import db
from .models import NEVER_HELD, Reservation, StockItem

log = logging.getLogger(__name__)


class OutOfStock(Exception):
    pass


def _lock(product_id: int) -> StockItem | None:
    # Row lock on MySQL; SQLite serialises writers anyway.
    return db.session.query(StockItem).filter_by(product_id=product_id).with_for_update().one_or_none()


def _in_lock_order(items: list[dict]) -> list[dict]:
    """Always lock stock rows in product id order, so two checkouts for the same products cannot
    each hold one row and wait for the other's (a deadlock on MySQL)."""
    return sorted(items, key=lambda line: line["product_id"])


def reserve(reservation_id: str, order_id: int, items: list[dict]) -> Reservation:
    existing = db.session.get(Reservation, reservation_id)
    if existing is not None:  # a retry, or a hold its release beat here: either way, hold nothing new
        return existing
    items = _in_lock_order(items)
    short = []
    for line in items:
        stock = _lock(line["product_id"])
        if stock is None or stock.available < line["quantity"]:
            short.append({"product_id": line["product_id"], "wanted": line["quantity"],
                          "available": stock.available if stock else 0})
    if short:
        db.session.rollback()
        raise OutOfStock(short)
    for line in items:
        _lock(line["product_id"]).reserved += line["quantity"]
    reservation = Reservation(id=reservation_id, order_id=order_id, items=items, status="RESERVED")
    db.session.add(reservation)
    try:
        db.session.commit()
    except IntegrityError:  # the same hold, sent twice at once, landed first: keep that one
        db.session.rollback()
        return db.session.get(Reservation, reservation_id)
    return reservation


def release(reservation_id: str) -> Reservation:
    reservation = db.session.get(Reservation, reservation_id)
    if reservation is None:
        # Demo 14: the release beat its hold here (the hold request was slow and the saga gave
        # up). Record the release, so the late hold finds it and holds nothing.
        log.warning("release for hold %s, which never arrived: recorded so a late hold is refused", reservation_id)
        reservation = Reservation(id=reservation_id, order_id=NEVER_HELD, items=[], status="RELEASED",
                                  releases_received=1)
        db.session.add(reservation)
        try:
            db.session.commit()
        except IntegrityError:  # the hold or another release landed at the same moment
            db.session.rollback()
            return release(reservation_id)
        return reservation
    reservation.releases_received = (reservation.releases_received or 0) + 1
    if reservation.status != "RESERVED":
        db.session.commit()
        return reservation
    for line in _in_lock_order(reservation.items):
        _lock(line["product_id"]).reserved -= line["quantity"]
    reservation.status = "RELEASED"
    db.session.commit()
    return reservation


def commit(reservation_id: str) -> Reservation | None:
    reservation = db.session.get(Reservation, reservation_id)
    if reservation is None or reservation.status != "RESERVED":
        return reservation
    for line in _in_lock_order(reservation.items):
        stock = _lock(line["product_id"])
        stock.reserved -= line["quantity"]
        stock.on_hand -= line["quantity"]
    reservation.status = "SOLD"
    db.session.commit()
    return reservation
