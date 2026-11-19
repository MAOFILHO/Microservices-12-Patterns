"""Demo 15: a flash sale. Many signed-in buyers each add 1 item and check out, again and again,
for a fixed time. Works against the local gateway and the Azure one:

    .venv/bin/python scripts/flash_sale.py --gateway http://127.0.0.1:8100 --buyers 5 --seconds 10 --stock 200

Prints a JSON summary. --stock needs CHAOS_ENABLED=1 on inventory (on locally under make run).
"""
import argparse
import json
import math
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx

PRODUCTS = range(1, 25)  # the catalog's 24 sample products
TIMEOUT = httpx.Timeout(30.0)
RESTOCK_MAX = 1000  # inventory's restock accepts at most this many per call
PENDING_WAIT_SECONDS = 6  # the reconciler settles pending payments every 5 s


@dataclass(frozen=True)
class Attempt:
    status: int | None  # None: no answer (timeout or refused connection)
    ms: float


def _percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def summarize(attempts: list[Attempt], seconds: float) -> dict:
    """Only a 200 is a completed order: 202 is still pending, everything else is a lost sale."""
    completed = sum(1 for a in attempts if a.status == 200)
    times = [a.ms for a in attempts]
    return {
        "attempts": len(attempts),
        "completed": completed,
        "success_rate": round(completed / len(attempts), 4) if attempts else 0.0,
        "by_status": dict(Counter("no answer" if a.status is None else str(a.status) for a in attempts)),
        "p50_ms": round(_percentile(times, 0.50), 1) if times else 0.0,
        "p95_ms": round(_percentile(times, 0.95), 1) if times else 0.0,
        "orders_per_minute": round(completed / seconds * 60, 1) if seconds else 0.0,
    }


def top_up_amounts(stock: list[dict], target: int) -> dict[int, list[int]]:
    """Restock calls that bring each product's free stock to `target` (the API takes 1,000 at most)."""
    plan = {}
    for row in stock:
        missing = target - (row["on_hand"] - row["reserved"])
        if missing > 0:
            plan[row["product_id"]] = [RESTOCK_MAX] * (missing // RESTOCK_MAX) + ([missing % RESTOCK_MAX] if missing % RESTOCK_MAX else [])
    return plan


def top_up(gateway: str, target: int) -> None:
    """Every run starts from the same stock, so one run's sales never decide the next run's result."""
    shop = _shop(gateway)
    stock = httpx.get(f"{shop}/inventory", timeout=TIMEOUT).raise_for_status().json()["results"]
    for product_id, amounts in top_up_amounts([r for r in stock if r["product_id"] in PRODUCTS], target).items():
        for quantity in amounts:
            httpx.post(f"{shop}/inventory/{product_id}/restock", json={"quantity": quantity},
                       timeout=TIMEOUT).raise_for_status()


def _shop(gateway: str) -> str:
    return f"{gateway.rstrip('/')}/api/shop"


def _sign_up(shop: str) -> dict:
    tag = uuid.uuid4().hex[:10]
    user = {"username": f"fs{tag}", "password": "flashsale1"}
    httpx.post(f"{shop}/user/create", data={**user, "email": f"fs{tag}@example.com"}, timeout=TIMEOUT)
    r = httpx.post(f"{shop}/user/login", data=user, timeout=TIMEOUT)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _cart_has_items(client: httpx.Client) -> bool:
    try:
        return bool(client.get("/order").json().get("result", {}).get("items"))
    except (httpx.HTTPError, ValueError):
        return True  # unknown: retrying the checkout is safe, adding an item is not


def buy(client: httpx.Client, first_product: int, until: float, out: list[Attempt]) -> None:
    """One buyer: 1 item per order. A failed checkout keeps the cart, so the buyer pays for the same
    cart again instead of adding a second item (which would make that order bigger)."""
    product, cart_full = first_product, False
    while time.monotonic() < until:
        started = time.perf_counter()
        try:
            status = 200 if cart_full else client.post("/order/add-item", data={"product_id": product, "qty": 1}).status_code
            added = status == 200
            if added:
                status = client.post("/order/checkout").status_code
        except httpx.HTTPError:
            status, added = None, False
        out.append(Attempt(status, (time.perf_counter() - started) * 1000))  # list.append is thread-safe
        if status == 200:
            cart_full, product = False, product % len(PRODUCTS) + 1
        elif status == 202:
            time.sleep(PENDING_WAIT_SECONDS)
            cart_full = _cart_has_items(client)
        elif status is None or not added:
            cart_full = _cart_has_items(client)
        else:
            cart_full = True
            if status == 409:
                time.sleep(1)  # sold out, or still pending: do not hammer the order service


def sign_up(gateway: str, buyers: int) -> list[dict]:
    with ThreadPoolExecutor(max_workers=10) as pool:
        return list(pool.map(lambda _: _sign_up(_shop(gateway)), range(buyers)))


def sell(gateway: str, buyers: list[dict], seconds: float) -> dict:
    """Every buyer buys at once for `seconds`; returns the summary."""
    attempts: list[Attempt] = []
    until = time.monotonic() + seconds
    clients = [httpx.Client(base_url=_shop(gateway), headers=h, timeout=TIMEOUT) for h in buyers]
    threads = [threading.Thread(target=buy, args=(c, i % len(PRODUCTS) + 1, until, attempts))
               for i, c in enumerate(clients)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for c in clients:
        c.close()
    return summarize(attempts, seconds)


def run(gateway: str, buyers: int, seconds: float) -> dict:
    """Signs the buyers up first (not timed), then lets them all buy at once."""
    return sell(gateway, sign_up(gateway, buyers), seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gateway", default="http://127.0.0.1:8100")
    parser.add_argument("--buyers", type=int, default=5)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--stock", type=int, default=0, help="first top up each product's free stock to this")
    args = parser.parse_args()
    if args.stock:
        top_up(args.gateway, args.stock)
    print(json.dumps(run(args.gateway, args.buyers, args.seconds), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
