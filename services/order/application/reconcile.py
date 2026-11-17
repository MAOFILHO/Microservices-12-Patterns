"""Settles checkouts left pending by a slow payment (demo 13).

Every RECONCILE_SECONDS, each order replica voids every pending charge's key with payment, which
answers how the charge stands: APPROVED confirms the order, DECLINED or VOIDED releases the stock,
and PROCESSING or no answer leaves it pending for the next pass. Payment voids a charge stuck in
PROCESSING once its process is surely gone, so no order waits forever while payment answers.
The rules are the saga's own (saga.settle_charge).
"""
import logging
import threading
import time

import requests

from . import db, saga
from .models import Order, PendingPayment
from .order_api.api import clients

RECONCILE_SECONDS = 5
log = logging.getLogger(__name__)


def resolve_pending() -> int:
    """One pass. Returns how many pending checkouts it settled."""
    settled = 0
    for row in PendingPayment.query.order_by(PendingPayment.since).all():
        saga_id, order_id, user_id, amount = row.saga_id, row.order_id, row.user_id, row.amount_cents
        try:
            charge = clients.void_charge(saga_id, order_id, amount)
        except requests.RequestException:
            continue  # still no answer: ask again next pass
        if charge["status"] == "PROCESSING":
            continue
        # Claim it by deleting the row, and commit at once: settling calls inventory, and the other
        # replica must not wait on this database lock meanwhile. If the other replica already took
        # it, nothing is deleted and this replica leaves it alone.
        claimed = PendingPayment.query.filter_by(saga_id=saga_id).delete() == 1
        db.session.commit()
        if not claimed:
            continue
        checkout = saga.Saga(db.session.get(Order, order_id), user_id, saga_id=saga_id)
        saga.settle_charge(checkout, amount, charge)
        settled += 1
    return settled


def start(app) -> None:
    from shop_common.flask_support import is_serving_process

    if not is_serving_process(app):
        return  # unit tests and the reloader's watcher land here

    def loop() -> None:
        while True:
            time.sleep(RECONCILE_SECONDS)
            with app.app_context():
                try:
                    resolve_pending()
                except Exception:
                    log.exception("reconcile pass failed; the next pass retries")
                    db.session.rollback()
                finally:
                    db.session.remove()

    threading.Thread(target=loop, name="payment-reconciler", daemon=True).start()
