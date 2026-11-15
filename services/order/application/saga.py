"""The checkout saga (pattern 8), orchestrated by the order service.

    1. price           ask catalog for current prices
    2. reserve_stock   inventory holds the units           compensation: release_stock
    3. charge_payment  payment charges the card            (nothing to undo if it fails)
    4. confirm         close the order and, in the SAME transaction, write OrderConfirmed to the
                       outbox. Inventory turns the hold into a sale when it reads that event (7).

If a later step fails, the earlier steps are undone in reverse order. Only step 2 changes another
service's data, so the only compensation is releasing the stock. If that direct call fails too,
a StockReleaseRequested event goes to the outbox, so inventory releases it once it can.
The cart stays open after a failed saga, so the shopper can try again.

Every step is written to saga_step, which is what the Saga page draws.
"""
import uuid

import requests

from . import db
from .models import Order, OutboxEvent, SagaStep
from .order_api.api import clients


class Saga:
    def __init__(self, order: Order, user_id: int):
        self.id = str(uuid.uuid4())
        self.order = order
        self.user_id = user_id

    def log(self, step: str, status: str, detail: str | None = None) -> None:
        db.session.add(SagaStep(saga_id=self.id, order_id=self.order.id, user_id=self.user_id,
                                step=step, status=status, detail=(detail or "")[:300]))
        db.session.commit()

    def emit(self, event_type: str, payload: dict) -> None:
        """Adds an event to the outbox. Committed by the caller, with the change it describes."""
        db.session.add(OutboxEvent(id=str(uuid.uuid4()), type=event_type,
                                   payload={"saga_id": self.id, "order_id": self.order.id, **payload}))

    def fail(self, step: str, detail: str, http_status: int, message: str, **extra) -> tuple[int, dict]:
        self.log(step, "failed", detail)
        self.emit("CheckoutFailed", {"failed_step": step, "reason": detail})
        db.session.commit()
        return http_status, {"message": message, "saga_id": self.id, "failed_step": step, **extra}


def run_checkout(order: Order, user_id: int, simulate: str = "approve") -> tuple[int, dict]:
    saga = Saga(order, user_id)
    items = [{"product_id": i.product_id, "quantity": i.quantity} for i in order.items]

    # 1. price
    try:
        prices = clients.product_prices()
    except requests.RequestException as exc:
        return saga.fail("price", f"catalog unreachable: {exc.__class__.__name__}", 503,
                         "The catalog is unavailable, so the order cannot be priced. Your cart is kept.")
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
                         "Not enough stock for your cart. Nothing was charged. Your cart is kept.", short=exc.short)
    except requests.RequestException as exc:
        return saga.fail("reserve_stock", f"inventory unreachable: {exc.__class__.__name__}", 503,
                         "Inventory is unavailable. Nothing was charged. Your cart is kept.")
    saga.log("reserve_stock", "done", f"held {sum(i['quantity'] for i in items)} unit(s)")

    # 3. charge payment (behind the M2 circuit breaker)
    failure = None
    try:
        payment = clients.charge(order.id, amount, simulate)
        if payment["status"] != "APPROVED":
            failure = ("declined", 402, "Your payment was declined. Nothing was charged; the stock was released. Your cart is kept.")
    except clients.PaymentUnavailable as exc:
        state = clients.breaker_state()
        wait = f" Try again in {state['retry_in_seconds']:.0f} s." if state["retry_in_seconds"] else ""
        failure = (f"payment unavailable ({exc.reason})", 503,
                   f"Payment is unavailable right now, so nothing was charged; the stock was released. Your cart is kept.{wait}")
    except requests.RequestException as exc:
        failure = (f"payment error: {exc.__class__.__name__}", 502, "Payment failed. The stock was released. Your cart is kept.")

    if failure:
        reason, http_status, message = failure
        saga.log("charge_payment", "failed", reason)
        _compensate(saga)
        saga.emit("CheckoutFailed", {"failed_step": "charge_payment", "reason": reason})
        db.session.commit()
        body = {"message": message, "saga_id": saga.id, "failed_step": "charge_payment"}
        if http_status == 503:
            body["breaker"] = clients.breaker_state()
        return http_status, body
    saga.log("charge_payment", "done", f"payment {payment['id']} APPROVED, {amount} cents")

    # 4. confirm: the order change and its event commit together, or not at all
    order.is_open = False
    saga.emit("OrderConfirmed", {"reservation_id": saga.id, "amount_cents": amount, "items": items})
    db.session.add(SagaStep(saga_id=saga.id, order_id=order.id, user_id=user_id, step="confirm",
                            status="done", detail="order closed; OrderConfirmed in the outbox"))
    db.session.commit()
    return 200, {"result": order.to_json(), "payment": payment, "saga_id": saga.id}


def _compensate(saga: Saga) -> None:
    try:
        clients.release_stock(saga.id)
        saga.log("release_stock", "compensated", "stock returned to inventory")
    except requests.RequestException as exc:
        # Could not undo directly: ask inventory through the bus. It is idempotent, so a release
        # that did go through and this event together are harmless.
        saga.emit("StockReleaseRequested", {"reservation_id": saga.id})
        saga.log("release_stock", "compensated", f"inventory unreachable ({exc.__class__.__name__}); release sent as an event")


def recent_sagas(user_id: int, limit: int = 5) -> list[dict]:
    saga_ids = [row.saga_id for row in db.session.query(SagaStep.saga_id, db.func.max(SagaStep.id).label("last"))
                .filter_by(user_id=user_id).group_by(SagaStep.saga_id).order_by(db.desc("last")).limit(limit)]
    result = []
    for saga_id in saga_ids:
        steps = SagaStep.query.filter_by(saga_id=saga_id).order_by(SagaStep.id).all()
        statuses = {s.status for s in steps}
        outcome = "compensated" if "compensated" in statuses else "failed" if "failed" in statuses else "completed"
        result.append({"saga_id": saga_id, "order_id": steps[0].order_id, "outcome": outcome,
                       "steps": [s.to_json() for s in steps]})
    return result
