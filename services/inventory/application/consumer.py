"""Inventory's event handler (pattern 7): finishes a sale when the order service confirms it.

OrderConfirmed       -> commit the reservation (reserved units become sold, on hand goes down)
StockReleaseRequested -> release the reservation (the saga's fallback when its direct call failed)
Anything else is not inventory's business and is acknowledged without action.
"""
from . import db, stock
from .models import ConsumedEvent

HANDLERS = {"OrderConfirmed": stock.commit, "StockReleaseRequested": stock.release}


def handle(event: dict) -> None:
    action = HANDLERS.get(event.get("type"))
    if action is None:
        return
    if db.session.get(ConsumedEvent, event["event_id"]) is not None:
        return  # seen before: at-least-once delivery sent it twice
    reservation_id = event["payload"].get("reservation_id")
    # action() commits on its own. If we crash before the ConsumedEvent row below, the event is
    # redelivered and action() is a no-op the second time (it checks the reservation's status).
    reservation = action(reservation_id)
    outcome = f"reservation {reservation.status}" if reservation else "no such reservation"
    db.session.add(ConsumedEvent(event_id=event["event_id"], type=event["type"],
                                 reservation_id=reservation_id, outcome=outcome))
    db.session.commit()


def start(app, instance_id: str) -> None:
    from shop_common.events import start_consumer
    from shop_common.flask_support import is_serving_process
    from shop_common.telemetry import get_logger

    if not is_serving_process(app):
        return

    def in_app(event: dict) -> None:
        with app.app_context():
            try:
                handle(event)
            finally:
                db.session.remove()

    start_consumer("inventory", instance_id, in_app, log=get_logger())
