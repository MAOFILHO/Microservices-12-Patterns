"""The checkout saga (pattern 8), orchestrated by the order service.

    1. price           ask catalog for current prices
    2. reserve_stock   inventory holds the units           event StockReserved; undo: release_stock
    3. charge_payment  payment charges the card            event PaymentCharged
    4. confirm         close the order and, in the SAME transaction, write OrderConfirmed to the
                       outbox. Inventory turns the hold into a sale when it reads that event (7).
    Any failure: event CheckoutFailed. One checkout per order at a time (checkout_lock).

Demo 13, a charge that times out: the customer may have been charged. The charge carries the saga
id as its idempotency key, so the retry cannot charge twice. Before it undoes anything, the saga
voids that key with payment, which answers how the charge stands (settle_charge). APPROVED
confirms the order; DECLINED or VOIDED (never arrived, and now never will) releases the stock;
PROCESSING or no answer leaves the order pending, with the stock held, until reconcile.py settles it.

If a later step fails, the earlier steps are undone in reverse order. Only step 2 changes another
service's data, so the only compensation is releasing the stock. If that direct call fails too,
a StockReleaseRequested event goes to the outbox, so inventory releases it once it can.
The cart stays open after a failed saga, so the shopper can try again.

Every step is written to saga_step, which is what the Saga page draws.
"""
import uuid
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy.exc import IntegrityError

from . import db
from .models import CheckoutLock, Order, OutboxEvent, PendingPayment, SagaStep
from .order_api.api import clients


class Saga:
    def __init__(self, order: Order, user_id: int, saga_id: str | None = None):
        self.id = saga_id or str(uuid.uuid4())
        self.order = order
        self.user_id = user_id

    def emit(self, event_type: str, payload: dict | None = None) -> None:
        """Adds an event to the outbox. It is committed together with the next log() line."""
        db.session.add(OutboxEvent(id=str(uuid.uuid4()), type=event_type,
                                   payload={"saga_id": self.id, "order_id": self.order.id, **(payload or {})}))

    def log(self, step: str, status: str, detail: str | None = None, event: str | None = None,
            payload: dict | None = None) -> None:
        """Records a step and, in the same transaction, its event and any pending order change."""
        db.session.add(SagaStep(saga_id=self.id, order_id=self.order.id, user_id=self.user_id,
                                step=step, status=status, detail=(detail or "")[:300]))
        if event:
            self.emit(event, payload)
        db.session.commit()

    def fail(self, step: str, detail: str, http_status: int, message: str, compensate: bool = False,
             **extra) -> tuple[int, dict]:
        """Logs the failed step, undoes the stock hold if asked, and reports CheckoutFailed."""
        self.log(step, "failed", detail)
        if compensate:
            _compensate(self)
        self.emit("CheckoutFailed", {"failed_step": step, "reason": detail})
        db.session.commit()
        return http_status, {"message": message, "saga_id": self.id, "failed_step": step, **extra}


# A lock older than this was left by a replica that crashed mid-saga; the next checkout may take it.
LOCK_TIMEOUT = timedelta(seconds=60)


def _acquire_lock(order: Order, saga_id: str) -> bool:
    now = datetime.now(timezone.utc)
    existing = db.session.get(CheckoutLock, order.id)
    if existing is not None:
        started = existing.started_at.replace(tzinfo=existing.started_at.tzinfo or timezone.utc)
        if now - started < LOCK_TIMEOUT:
            return False
        db.session.delete(existing)
        db.session.flush()
    db.session.add(CheckoutLock(order_id=order.id, saga_id=saga_id, started_at=now))
    try:
        db.session.commit()
        return True
    except IntegrityError:  # the other click (or replica) got there first
        db.session.rollback()
        return False


def _release_lock(order_id: int) -> None:
    lock = db.session.get(CheckoutLock, order_id)
    if lock is not None:
        db.session.delete(lock)
        db.session.commit()


PENDING_MESSAGE = ("Your last checkout is still waiting for payment. It is confirmed, or the stock released, "
                   "as soon as payment answers.")


def run_checkout(order: Order, user_id: int, simulate: str = "approve") -> tuple[int, dict]:
    saga = Saga(order, user_id)
    if not _acquire_lock(order, saga.id):
        return 409, {"message": "A checkout for this order is already in progress."}
    try:
        if is_pending(order.id):
            return 409, {"message": PENDING_MESSAGE, "pending": True}
        return _run_steps(saga, simulate)
    finally:
        _release_lock(order.id)


def _run_steps(saga: Saga, simulate: str) -> tuple[int, dict]:
    order = saga.order
    items = [{"product_id": i.product_id, "quantity": i.quantity} for i in order.items]
    kept = "Your cart is kept."

    # 1. price
    try:
        prices = clients.product_prices()
    except requests.RequestException as exc:
        return saga.fail("price", f"catalog unreachable: {exc.__class__.__name__}", 503,
                         f"The catalog is unavailable, so the order cannot be priced. {kept}")
    missing = [i["product_id"] for i in items if i["product_id"] not in prices]
    if missing:
        return saga.fail("price", f"unknown products {missing}", 409, f"Product(s) {missing} are no longer sold")
    amount = sum(prices[i["product_id"]] * i["quantity"] for i in items)
    saga.log("price", "done", f"{len(items)} line(s), total {amount} cents")

    # 2. reserve stock
    try:
        clients.reserve_stock(saga.id, order.id, items)
    except clients.OutOfStock as exc:
        return saga.fail("reserve_stock", f"short: {exc.short}", 409,
                         f"Not enough stock for your cart. Nothing was charged. {kept}", short=exc.short)
    except requests.RequestException as exc:
        # No answer does not mean no hold: inventory may have held the stock before the reply was
        # lost. Ask it to release through the bus; releasing an unknown hold is a no-op.
        saga.emit("StockReleaseRequested", {"reservation_id": saga.id})
        return saga.fail("reserve_stock", f"inventory unreachable: {exc.__class__.__name__}", 503,
                         f"Inventory is unavailable. Nothing was charged. {kept}")
    units = sum(i["quantity"] for i in items)
    saga.log("reserve_stock", "done", f"held {units} unit(s)", event="StockReserved",
             payload={"reservation_id": saga.id, "items": items})

    # 3. charge payment (behind the M2 circuit breaker), keyed by the saga id (demo 13)
    try:
        payment = clients.charge(order.id, amount, simulate, idempotency_key=saga.id)
    except clients.PaymentUnavailable as exc:
        if exc.reason == "open":  # the breaker refused the call: payment was never contacted
            breaker = clients.breaker_state()
            wait = f" Try again in {breaker['retry_in_seconds']:.0f} s." if breaker["retry_in_seconds"] else ""
            return saga.fail("charge_payment", "payment unavailable (open)", 503,
                             f"Payment is unavailable right now, so nothing was charged; the stock was released. {kept}{wait}",
                             compensate=True, breaker=breaker)
        return _charge_unknown(saga, amount, f"payment unavailable ({exc.reason})")
    except requests.RequestException as exc:
        return _charge_unknown(saga, amount, f"payment error: {exc.__class__.__name__}")
    if payment["status"] == "PROCESSING":  # a retry answered while the first try is still running
        return _charge_unknown(saga, amount, "payment still processing")
    if payment["status"] != "APPROVED":
        return saga.fail("charge_payment", "declined", 402,
                         f"Your payment was declined. Nothing was charged; the stock was released. {kept}",
                         compensate=True)
    return _confirm(saga, amount, payment, "charge_payment")


def _confirm(saga: Saga, amount: int, payment: dict, step: str) -> tuple[int, dict]:
    """The charge went through: record it, then 4. confirm. The order change, its log line and its
    event commit together, or not at all."""
    order = saga.order
    items = [{"product_id": i.product_id, "quantity": i.quantity} for i in order.items]
    saga.log(step, "done", f"payment {payment['id']} APPROVED, {amount} cents", event="PaymentCharged",
             payload={"payment_id": payment["id"], "amount_cents": amount})
    order.is_open = False
    saga.log("confirm", "done", "order closed; OrderConfirmed in the outbox", event="OrderConfirmed",
             payload={"reservation_id": saga.id, "amount_cents": amount, "items": items})
    return 200, {"result": order.to_json(), "payment": payment, "saga_id": saga.id}


def _charge_unknown(saga: Saga, amount: int, detail: str) -> tuple[int, dict]:
    """Demo 13: the charge call failed after it may have reached payment, so the customer may have
    been charged. Void the key first: payment then says how the charge stands."""
    saga.log("charge_payment", "timed_out", f"{detail}; asking payment what happened")
    try:
        charge = clients.void_charge(saga.id, saga.order.id, amount)
    except requests.RequestException as exc:
        charge = {"status": f"no answer ({exc.__class__.__name__})"}
    return settle_charge(saga, amount, charge)


def settle_charge(saga: Saga, amount: int, charge: dict) -> tuple[int, dict]:
    """How payment says the saga's charge stands decides the outcome (also used by reconcile.py)."""
    status = charge["status"]
    kept = "Your cart is kept."
    if status == "APPROVED":
        return _confirm(saga, amount, charge, "check_payment")
    if status == "DECLINED":
        return saga.fail("check_payment", "payment says DECLINED", 402,
                         f"Your payment was declined. Nothing was charged; the stock was released. {kept}",
                         compensate=True)
    if status == "VOIDED":
        return saga.fail("check_payment", "payment never took the charge; its key is now void", 503,
                         f"Payment did not go through. Nothing was charged; the stock was released. {kept}",
                         compensate=True)
    db.session.add(PendingPayment(saga_id=saga.id, order_id=saga.order.id, user_id=saga.user_id, amount_cents=amount))
    saga.log("check_payment", "pending", f"payment says {status}; the order waits, the stock stays held")
    return 202, {"message": "Payment is taking longer than usual. Your order is pending: it is confirmed, or the "
                            "stock released, as soon as payment answers. You cannot be charged twice.",
                 "saga_id": saga.id, "pending": True}


def is_pending(order_id: int) -> bool:
    return PendingPayment.query.filter_by(order_id=order_id).first() is not None


def _compensate(saga: Saga) -> None:
    try:
        clients.release_stock(saga.id)
        saga.log("release_stock", "compensated", "stock returned to inventory")
    except requests.RequestException as exc:
        # Could not undo directly: ask inventory through the bus. It is idempotent, so a release
        # that did go through and this event together are harmless.
        saga.log("release_stock", "compensated", f"inventory unreachable ({exc.__class__.__name__}); release sent as an event",
                 event="StockReleaseRequested", payload={"reservation_id": saga.id})


def recent_sagas(user_id: int, limit: int = 5) -> list[dict]:
    saga_ids = [row.saga_id for row in db.session.query(SagaStep.saga_id, db.func.max(SagaStep.id).label("last"))
                .filter_by(user_id=user_id).group_by(SagaStep.saga_id).order_by(db.desc("last")).limit(limit)]
    result = []
    for saga_id in saga_ids:
        steps = SagaStep.query.filter_by(saga_id=saga_id).order_by(SagaStep.id).all()
        statuses = {s.status for s in steps}
        outcome = ("compensated" if "compensated" in statuses else "failed" if "failed" in statuses
                   else "pending" if steps[-1].status == "pending" else "completed")
        result.append({"saga_id": saga_id, "order_id": steps[0].order_id, "outcome": outcome,
                       "steps": [s.to_json() for s in steps]})
    return result
