"""Stock rules for the checkout saga (pattern 8) and the event consumer (pattern 7).

reserve:  available -> reserved      (saga step 1; all lines or none)
release:  reserved  -> available     (saga compensation)
commit:   reserved  -> sold          (on OrderConfirmed: on hand goes down)

Each is idempotent: calling it again for the same reservation changes nothing.
"""
from . import db
from .models import Reservation, StockItem


class OutOfStock(Exception):
    pass


def _lock(product_id: int) -> StockItem | None:
    # Row lock on MySQL; SQLite serialises writers anyway.
    return db.session.query(StockItem).filter_by(product_id=product_id).with_for_update().one_or_none()


def reserve(reservation_id: str, order_id: int, items: list[dict]) -> Reservation:
    existing = db.session.get(Reservation, reservation_id)
    if existing is not None:
        return existing
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
    db.session.commit()
    return reservation


def release(reservation_id: str) -> Reservation | None:
    reservation = db.session.get(Reservation, reservation_id)
    if reservation is None or reservation.status != "RESERVED":
        return reservation
    for line in reservation.items:
        _lock(line["product_id"]).reserved -= line["quantity"]
    reservation.status = "RELEASED"
    db.session.commit()
    return reservation


def commit(reservation_id: str) -> Reservation | None:
    reservation = db.session.get(Reservation, reservation_id)
    if reservation is None or reservation.status != "RESERVED":
        return reservation
    for line in reservation.items:
        stock = _lock(line["product_id"])
        stock.reserved -= line["quantity"]
        stock.on_hand -= line["quantity"]
    reservation.status = "SOLD"
    db.session.commit()
    return reservation
