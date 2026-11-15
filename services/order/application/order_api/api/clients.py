"""How the order service reaches other services.

- Who is calling: verified locally from the signed token (pattern 10). No call to the user service
  per request, only one call to fetch its public key.
- Where a service lives: asked from the registry (pattern 12), static URL as the fallback.
- Payment: every call goes through one circuit breaker (pattern 4). After FAIL_MAX failed calls in
  a row it opens and calls fail instantly for RESET_SECONDS, then one trial call decides whether
  it closes again. Each failed call is first retried once (tenacity), so a single blip does not
  count as a failure.
"""
import os
from datetime import datetime, timezone

import pybreaker
import requests
from shop_common.auth import TokenVerifier
from shop_common.discovery import DISCOVERY
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

STATIC_URLS = {
    "user": os.environ.get("USER_SERVICE_BASE_URL", "http://127.0.0.1:5101"),
    "catalog": os.environ.get("CATALOG_SERVICE_BASE_URL", "http://127.0.0.1:5102"),
    "payment": os.environ.get("PAYMENT_SERVICE_BASE_URL", "http://127.0.0.1:5104"),
    "inventory": os.environ.get("INVENTORY_SERVICE_BASE_URL", "http://127.0.0.1:5105"),
}

PAYMENT_TIMEOUT_SECONDS = float(os.environ.get("PAYMENT_TIMEOUT_SECONDS", "1.0"))
FAIL_MAX = 3
RESET_SECONDS = 15


def base_url(service: str) -> str:
    return DISCOVERY.url_for(service, STATIC_URLS[service])


TOKENS = TokenVerifier(lambda: base_url("user"))


def current_user_id(authorization_header: str | None) -> int | None:
    claims = TOKENS.verify(authorization_header)
    return int(claims["sub"]) if claims else None


# --- Catalog -----------------------------------------------------------------------------------

def product_prices() -> dict[int, int]:
    """product id -> price in cents, from the catalog (the context that owns prices)."""
    response = requests.get(f"{base_url('catalog')}/api/products", timeout=3)
    response.raise_for_status()
    return {p["id"]: p["price"] for p in response.json()["results"]}


# --- Inventory (saga steps, pattern 8) ------------------------------------------------------------

class OutOfStock(Exception):
    def __init__(self, short: list[dict]):
        super().__init__("not enough stock")
        self.short = short


def reserve_stock(reservation_id: str, order_id: int, items: list[dict]) -> dict:
    response = requests.post(f"{base_url('inventory')}/api/inventory/reservations", timeout=3,
                             json={"reservation_id": reservation_id, "order_id": order_id, "items": items})
    if response.status_code == 409:
        raise OutOfStock(response.json().get("short", []))
    response.raise_for_status()
    return response.json()["result"]


def release_stock(reservation_id: str) -> dict:
    response = requests.post(f"{base_url('inventory')}/api/inventory/reservations/{reservation_id}/release", timeout=3)
    response.raise_for_status()
    return response.json()["result"]


# --- Payment, behind the circuit breaker ----------------------------------------------------------

BREAKER = pybreaker.CircuitBreaker(fail_max=FAIL_MAX, reset_timeout=RESET_SECONDS, name="payment")


class PaymentUnavailable(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason  # "open" (failed fast, no call made) or "failed" (call made, it failed)


@retry(stop=stop_after_attempt(2), wait=wait_fixed(0.2), retry=retry_if_exception_type(requests.RequestException), reraise=True)
def _send(method: str, path: str, json: dict | None) -> requests.Response:
    response = requests.request(method, f"{base_url('payment')}{path}", json=json, timeout=PAYMENT_TIMEOUT_SECONDS)
    if response.status_code >= 500:  # 4xx is the caller's mistake, not a sick service
        raise requests.HTTPError(f"payment returned {response.status_code}", response=response)
    return response


def call_payment(method: str, path: str, json: dict | None = None) -> requests.Response:
    attempted = []

    def attempt() -> requests.Response:
        attempted.append(True)
        return _send(method, path, json)

    try:
        return BREAKER.call(attempt)
    except pybreaker.CircuitBreakerError:
        # pybreaker raises this when already open (no call made) and on the failure that trips it.
        raise PaymentUnavailable("failed" if attempted else "open")
    except requests.RequestException:
        raise PaymentUnavailable("failed")


def charge(order_id: int, amount_cents: int, simulate: str = "approve") -> dict:
    body = {"order_id": order_id, "amount_cents": amount_cents}
    if simulate != "approve":
        body["simulate"] = simulate
    response = call_payment("POST", "/api/payment/charge", body)
    response.raise_for_status()
    return response.json()["result"]


def breaker_state() -> dict:
    retry_in = None
    opened_at = BREAKER._state_storage.opened_at  # pybreaker keeps no public accessor for this
    if BREAKER.current_state == "open" and opened_at:
        elapsed = (datetime.now(timezone.utc) - opened_at).total_seconds()
        retry_in = max(0, round(RESET_SECONDS - elapsed, 1))
    return {
        "state": BREAKER.current_state,
        "failures_in_a_row": BREAKER.fail_counter,
        "fail_max": FAIL_MAX,
        "reset_seconds": RESET_SECONDS,
        "retry_in_seconds": retry_in,
    }
