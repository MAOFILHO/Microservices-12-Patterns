"""Demo 15: the same flash sale under a replica cap of 3 and of 8. These cover the numbers the page
shows: success rate, replica-seconds read from Azure Monitor, and cost per 1,000 completed orders."""
import time

import httpx

import autoscale_demo
import flash_sale
from flash_sale import Attempt


def test_summary_counts_only_200s_as_completed_and_reports_latency():
    attempts = [Attempt(200, 100.0)] * 6 + [Attempt(503, 50.0)] * 2 + [Attempt(202, 900.0), Attempt(None, 3000.0)]
    summary = flash_sale.summarize(attempts, seconds=60)
    assert summary["attempts"] == 10
    assert summary["completed"] == 6
    assert summary["success_rate"] == 0.6
    assert summary["by_status"] == {"200": 6, "503": 2, "202": 1, "no answer": 1}
    assert summary["p50_ms"] == 100.0
    assert summary["p95_ms"] == 3000.0
    assert summary["orders_per_minute"] == 6.0


def test_summary_of_no_attempts_is_zero_not_a_crash():
    assert flash_sale.summarize([], seconds=60)["success_rate"] == 0.0


def _metric(name, points):
    return {"name": {"value": name}, "timeseries": [{"data": points}]}


def test_replica_usage_turns_one_minute_averages_into_seconds():
    metrics = {"value": [
        _metric("Replicas", [{"average": 1.0, "maximum": 1.0}, {"average": 2.5, "maximum": 3.0}, {}]),
        _metric("Requests", [{"total": 400.0}, {"total": 600.0}]),
    ]}
    assert autoscale_demo.replica_usage(metrics) == {"replica_seconds": 210.0, "peak_replicas": 3, "requests": 1000}


def test_replica_usage_adds_up_revisions_and_survives_empty_minutes():
    """A cap change starts a new revision: both run side by side for a while and both are billed."""
    old = {"data": [{"timeStamp": "t1", "average": 2.0, "maximum": 2.0}, {"timeStamp": "t2", "average": None}]}
    new = {"data": [{"timeStamp": "t1", "average": 1.0, "maximum": 2.0}, {"timeStamp": "t2", "average": 3.0, "maximum": 3.0}]}
    metrics = {"value": [{"name": {"value": "Replicas"}, "timeseries": [old, new]},
                         {"name": {"value": "Requests"}, "timeseries": []}]}
    assert autoscale_demo.replica_usage(metrics) == {"replica_seconds": 360.0, "peak_replicas": 4, "requests": 0}


def test_cost_prices_the_sale_active_the_cooldown_idle_and_adds_mysql():
    usage = {"gateway": {"replica_seconds": 1000.0, "cooldown_replica_seconds": 1000.0, "peak_replicas": 3,
                         "requests": 1_000_000},
             "order": {"replica_seconds": 1000.0, "cooldown_replica_seconds": 0.0, "peak_replicas": 3, "requests": 0}}
    cost = autoscale_demo.cost_usd(usage, mysql_seconds=3600)
    # sale: 2000 s x (0.25 x $0.000024 + 0.5 x $0.000003) = $0.015
    # cooldown: 1000 s x (0.25 x $0.000003 + 0.5 x $0.000003) = $0.00225
    # requests: 1M x $0.40/M = $0.40; MySQL B1ms: 1 hour x $0.017
    assert {k: round(v, 6) for k, v in cost.items()} == {
        "replicas": 0.01725, "requests": 0.4, "mysql": 0.017, "total": 0.43425}


def test_the_estimate_before_a_run_assumes_every_service_sits_at_the_cap():
    # 6 apps x 8 replicas x (240 s + 300 s cooldown) at the active rate, plus MySQL for 30 minutes
    assert round(autoscale_demo.estimate_max_usd(cap=8, seconds=240), 4) == round(
        6 * 8 * 540 * 0.0000075 + 0.5 * 0.017, 4)


def test_top_up_brings_every_product_to_the_same_level_in_steps_the_api_accepts():
    rows = [{"product_id": 1, "on_hand": 30, "reserved": 5}, {"product_id": 2, "on_hand": 2600, "reserved": 0},
            {"product_id": 3, "on_hand": 100, "reserved": 0}]
    assert flash_sale.top_up_amounts(rows, target=2500) == {1: [1000, 1000, 475], 3: [1000, 1000, 400]}


def test_cost_per_thousand_orders():
    assert autoscale_demo.per_thousand(0.5, completed=2000) == 0.25
    assert autoscale_demo.per_thousand(0.5, completed=0) is None


def test_a_rerun_replaces_the_run_with_the_same_cap():
    results = {"runs": [{"cap": 8, "completed": 1}, {"cap": 3, "completed": 1}]}
    merged = autoscale_demo.merge_run(results, {"cap": 3, "completed": 2})
    assert merged["runs"] == [{"cap": 3, "completed": 2}, {"cap": 8, "completed": 1}]


def _shop(checkout_statuses: list[int], calls: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/checkout"):
            return httpx.Response(checkout_statuses.pop(0) if checkout_statuses else 200)
        return httpx.Response(200, json={"result": {"items": []}})
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://shop")


def test_a_buyer_retries_the_same_cart_after_a_failed_checkout():
    """A failed checkout keeps the cart: adding another item would make the next order bigger."""
    calls: list[str] = []
    out: list[Attempt] = []
    flash_sale.buy(_shop([503, 503, 200], calls), first_product=1, until=time.monotonic() + 0.1, out=out)
    assert calls[:5] == ["/order/add-item", "/order/checkout", "/order/checkout", "/order/checkout", "/order/add-item"]
    assert [a.status for a in out[:3]] == [503, 503, 200]
