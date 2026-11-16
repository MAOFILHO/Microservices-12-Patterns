"""Post-provision smoke tests against Azure (issue #11). Run after `make provision`:

    .venv/bin/python -m pytest tests/smoke/test_post_provision_azure.py -v

Reads the gateway address from infra/.state.json and skips when nothing is provisioned. Checks
what only a real Azure run can prove: Redis inside the environment carries events, the signing
key secret works, containers run as uid 10001 on the commit they were tagged with, demo switches
are off, and the CI-CD page reads GitHub. Apps scale to zero, so the first calls wake them.
"""
import json
import time
import uuid
from pathlib import Path

import httpx
import pytest

TIMEOUT = httpx.Timeout(60.0)


@pytest.fixture(scope="module")
def azure():
    state_file = Path(__file__).resolve().parents[2] / "infra" / ".state.json"
    if not state_file.exists():
        pytest.skip("nothing provisioned (no infra/.state.json)")
    state = json.loads(state_file.read_text())
    gateway = f"https://{state['outputs']['gatewayFqdn']}"
    deadline = time.monotonic() + 180  # cold start of the gateway and every service it calls
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{gateway}/health", timeout=TIMEOUT).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(5)
    return {"gateway": gateway, "tag": state["image_tag"]}


def _wait_for(condition, seconds=60.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(2)
    return False


def _login_with_cart(shop: str, qty: int = 1) -> dict:
    tag = uuid.uuid4().hex[:8]
    httpx.post(f"{shop}/user/create", timeout=TIMEOUT,
               data={"username": f"az{tag}", "email": f"az{tag}@example.com", "password": "secret123"})
    r = httpx.post(f"{shop}/user/login", data={"username": f"az{tag}", "password": "secret123"}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    assert httpx.post(f"{shop}/order/add-item", data={"product_id": 1, "qty": qty}, headers=headers,
                      timeout=TIMEOUT).status_code == 200
    return headers


def _mug(shop: str) -> dict:
    return next(s for s in httpx.get(f"{shop}/inventory", timeout=TIMEOUT).json()["results"] if s["product_id"] == 1)


def test_every_process_runs_in_a_container_as_uid_10001_on_the_deployed_commit(azure):
    processes = httpx.get(f"{azure['gateway']}/api/patterns/runtime", timeout=TIMEOUT).json()["processes"]
    assert len(processes) == 6, processes  # gateway + 5 services, one replica each in Azure
    for p in processes:
        assert p.get("in_container") is True and p.get("uid") == 10001 and p.get("root") is False, p
        assert p.get("git_sha") == azure["tag"], p
        assert p.get("arch") == "x86_64", p


def test_a_sale_settles_through_redis_inside_azure(azure):
    shop = f"{azure['gateway']}/api/shop"
    headers = _login_with_cart(shop, qty=1)
    before = _mug(shop)
    r = httpx.post(f"{shop}/order/checkout", headers=headers, json={}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    # Order's outbox -> Redis Container App -> inventory's consumer turns the hold into a sale.
    assert _wait_for(lambda: _mug(shop)["on_hand"] == before["on_hand"] - 1), _mug(shop)
    assert _mug(shop)["reserved"] == before["reserved"]


def test_demo_switches_are_off_in_azure(azure):
    shop = f"{azure['gateway']}/api/shop"
    headers = _login_with_cart(shop)
    assert httpx.post(f"{shop}/order/checkout", headers=headers, json={"simulate_decline": True},
                      timeout=TIMEOUT).status_code == 403
    api = f"{azure['gateway']}/api/patterns"
    assert httpx.post(f"{api}/breaker/payment-mode", json={"mode": "failing"}, timeout=TIMEOUT).status_code == 403
    assert httpx.post(f"{api}/events/bus", json={"connected": False}, timeout=TIMEOUT).status_code == 403


def test_the_ci_cd_page_sees_every_service_on_main(azure):
    body = httpx.get(f"{azure['gateway']}/api/patterns/delivery", timeout=TIMEOUT).json()
    assert body["main"] is not None, "GitHub unreachable from Azure"
    assert {s["status"] for s in body["services"]} <= {"current", "unchanged"}, body["services"]
