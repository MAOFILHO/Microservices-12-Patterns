#!/usr/bin/env python3
"""make flash-sale CAP=3 (then CAP=8) — demo 15, against a provisioned Azure stack.

Caps every service at CAP replicas, runs the same flash sale (scripts/flash_sale.py), then reads
how many replicas Azure ran and how many requests it served from Azure Monitor, and prices them.
The result goes into frontend/src/patterns/demos/flashSaleResults.json for the demo page.

Every run starts from the same stock (2,500 free units of each product), and a buyer whose checkout
fails pays for the same 1-item cart again, so both runs sell orders of the same size.
Restocking needs inventory's demo switches, which are off in Azure: CHAOS_ENABLED=1 is set on
inventory for the run only and removed afterwards, even when the run fails. The cap goes back to 3
afterwards, also when the run fails. It prints the most the run can cost and asks before starting.
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import httpx  # noqa: E402

import flash_sale  # noqa: E402
from resume import MAX_REPLICAS_DEFAULT  # noqa: E402
from service_table import AZURE_SERVICES  # noqa: E402

DEFAULT_CAP = int(MAX_REPLICAS_DEFAULT)  # what provision and make resume set

STATE_FILE = REPO_ROOT / "infra" / ".state.json"
RESULTS_FILE = REPO_ROOT / "frontend" / "src" / "patterns" / "demos" / "flashSaleResults.json"

# Every app runs 0.25 vCPU and 0.5 GiB per replica (infra/bicep/modules/container-app.bicep).
REPLICA_VCPU = 0.25
REPLICA_GIB = 0.5
# List prices, East US, from https://prices.azure.com/api/retail/prices (Azure Container Apps,
# Consumption; Azure Database for MySQL, B1MS compute), checked 2026-11-18. The monthly free grant
# is ignored: it would make both runs read $0.
PRICES = {
    "vcpu_second": 0.000024, "idle_vcpu_second": 0.000003, "gib_second": 0.000003,
    "per_million_requests": 0.40, "mysql_hour": 0.017,
}
COOLDOWN_SECONDS = 300  # Container Apps keeps extra replicas this long after the load ends
METRICS_DELAY_SECONDS = 180  # Azure Monitor shows a minute's numbers a few minutes later
SESSION_HOURS = 0.5  # MySQL bills from make provision to make teardown: about this long for one run
STOCK_PER_PRODUCT = 2500  # free stock every run starts from, so no run sells out


def _value(point: dict, key: str) -> float:
    return point.get(key) or 0.0  # Azure Monitor sends null for a minute with no data


def replica_usage(metrics: dict) -> dict:
    """One app's `az monitor metrics list` answer, 1-minute points, one series per revision ->
    replica-seconds, peak replicas, requests. Revisions running side by side are both billed."""
    series = {m["name"]["value"]: m["timeseries"] for m in metrics["value"]}
    per_minute: dict = {}
    seconds = 0.0
    for revision in series.get("Replicas", []):
        for i, point in enumerate(revision["data"]):
            seconds += _value(point, "average") * 60
            minute = point.get("timeStamp", i)
            per_minute[minute] = per_minute.get(minute, 0.0) + _value(point, "maximum")
    requests = sum(_value(p, "total") for revision in series.get("Requests", []) for p in revision["data"])
    return {"replica_seconds": seconds, "peak_replicas": int(max(per_minute.values(), default=0)),
            "requests": int(requests)}


def _active_replica_second() -> float:
    return REPLICA_VCPU * PRICES["vcpu_second"] + REPLICA_GIB * PRICES["gib_second"]


def cost_usd(usage: dict[str, dict], mysql_seconds: float) -> dict:
    """Replicas during the sale at the active rate, through the cooldown at the idle rate (they
    serve nothing then), requests, and the MySQL server for the same time."""
    idle_replica_second = REPLICA_VCPU * PRICES["idle_vcpu_second"] + REPLICA_GIB * PRICES["gib_second"]
    replicas = sum(u["replica_seconds"] * _active_replica_second()
                   + u["cooldown_replica_seconds"] * idle_replica_second for u in usage.values())
    requests = sum(u["requests"] for u in usage.values()) / 1_000_000 * PRICES["per_million_requests"]
    mysql = mysql_seconds / 3600 * PRICES["mysql_hour"]
    return {"replicas": replicas, "requests": requests, "mysql": mysql, "total": replicas + requests + mysql}


def estimate_max_usd(cap: int, seconds: float) -> float:
    """The most one run can cost: every service at the cap for the sale and the cooldown, all at the
    active rate, plus MySQL for the whole session."""
    return (len(AZURE_SERVICES) * cap * (seconds + COOLDOWN_SECONDS) * _active_replica_second()
            + SESSION_HOURS * PRICES["mysql_hour"])


def per_thousand(cost: float, completed: int) -> float | None:
    return round(cost / completed * 1000, 4) if completed else None


def merge_run(results: dict, run: dict) -> dict:
    """A rerun with the same cap replaces the old one; runs stay sorted by cap."""
    runs = [r for r in results.get("runs", []) if r["cap"] != run["cap"]] + [run]
    return {**results, "runs": sorted(runs, key=lambda r: r["cap"])}


def _az(args: list[str]) -> str:
    print(f"$ az {' '.join(args)}")
    return subprocess.run(["az", *args, "--output", "json"], capture_output=True, text=True, check=True).stdout


def _set_cap(resource_group: str, cap: int) -> None:
    for svc in AZURE_SERVICES:
        _az(["containerapp", "update", "--name", svc.name, "--resource-group", resource_group,
             "--max-replicas", str(cap)])


def _inventory_switches(resource_group: str, on: bool) -> None:
    change = ["--set-env-vars", "CHAOS_ENABLED=1"] if on else ["--remove-env-vars", "CHAOS_ENABLED"]
    _az(["containerapp", "update", "--name", "inventory", "--resource-group", resource_group, *change])


def _wait_until_ready(resource_group: str, timeout: float = 600) -> None:
    """Every update starts a new revision. The sale starts only once every app runs its latest one."""
    deadline = time.monotonic() + timeout
    for svc in AZURE_SERVICES:
        while True:
            app = json.loads(_az(["containerapp", "show", "--name", svc.name, "--resource-group", resource_group]))
            props = app["properties"]
            if props.get("latestReadyRevisionName") == props.get("latestRevisionName"):
                break
            if time.monotonic() > deadline:
                raise SystemExit(f"{svc.name} never got its new revision ready")
            time.sleep(10)


def _top_up_when_ready(gateway: str, timeout: float = 300) -> None:
    """Restock answers 403 until inventory's new revision (with CHAOS_ENABLED=1) takes the traffic."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            flash_sale.top_up(gateway, STOCK_PER_PRODUCT)
            return
        except httpx.HTTPError as err:
            if time.monotonic() > deadline:
                raise SystemExit(f"Restock never worked: {err}")
            time.sleep(10)


def _metrics(subscription: str, resource_group: str, app: str, start: datetime, end: datetime) -> dict:
    resource = f"/subscriptions/{subscription}/resourceGroups/{resource_group}/providers/Microsoft.App/containerApps/{app}"
    query = ["monitor", "metrics", "list", "--resource", resource, "--metrics", "Replicas", "Requests",
             "--interval", "PT1M", "--aggregation", "Average", "Maximum", "Total",
             "--start-time", start.isoformat(), "--end-time", end.isoformat()]
    try:  # one series per revision, so revisions running side by side are added up
        return json.loads(_az([*query, "--filter", "revisionName eq '*'"]))
    except subprocess.CalledProcessError:
        return json.loads(_az(query))  # the metric has no revision split: Azure adds them up itself


def _usage(subscription: str, resource_group: str, start: datetime, end: datetime, cooldown_end: datetime) -> dict:
    usage = {}
    for svc in AZURE_SERVICES:
        sale = replica_usage(_metrics(subscription, resource_group, svc.name, start, end))
        cooldown = replica_usage(_metrics(subscription, resource_group, svc.name, end, cooldown_end))
        usage[svc.name] = {**sale, "cooldown_replica_seconds": cooldown["replica_seconds"],
                           "requests": sale["requests"] + cooldown["requests"]}
    return usage


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo 15: one flash sale under a replica cap.")
    parser.add_argument("--cap", type=int, required=True, help="max replicas per service, e.g. 3 or 8")
    parser.add_argument("--buyers", type=int, default=80, help="buyers checking out at the same time")
    parser.add_argument("--seconds", type=float, default=240)
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    args = parser.parse_args()
    if not STATE_FILE.exists():
        print("No infra/.state.json: run make provision first.")
        return 1
    state = json.loads(STATE_FILE.read_text())
    resource_group, subscription = state["resource_group"], state["subscription_id"]
    gateway = f"https://{state['outputs']['gatewayFqdn']}"

    estimate = estimate_max_usd(args.cap, args.seconds)
    print(f"Cap {args.cap}, {args.buyers} buyers for {args.seconds:.0f} s. This run costs at most ${estimate:.2f} "
          f"(every service at {args.cap} replicas the whole time, plus MySQL).")
    if not args.yes and input("Go ahead? [y/N] ").strip().lower() != "y":
        return 1

    try:
        _set_cap(resource_group, args.cap)
        _inventory_switches(resource_group, on=True)
        try:
            _wait_until_ready(resource_group)
            _top_up_when_ready(gateway)
            buyers = flash_sale.sign_up(gateway, args.buyers)  # not timed, not measured
            start = datetime.now(timezone.utc)
            summary = flash_sale.sell(gateway, buyers, args.seconds)
            end = datetime.now(timezone.utc)
        finally:
            _inventory_switches(resource_group, on=False)
        print(json.dumps(summary, indent=2))

        # The replicas still running through the cooldown are billed too: wait them out, then read.
        cooldown_end = end + timedelta(seconds=COOLDOWN_SECONDS)
        wait = (cooldown_end - datetime.now(timezone.utc)).total_seconds() + METRICS_DELAY_SECONDS
        print(f"Waiting {wait / 60:.0f} min for the cooldown and for Azure Monitor to catch up...")
        time.sleep(max(0.0, wait))
        usage = _usage(subscription, resource_group, start, end, cooldown_end)
    finally:
        if args.cap != DEFAULT_CAP:
            _set_cap(resource_group, DEFAULT_CAP)  # always, so a failed run never leaves the higher cap

    cost = cost_usd(usage, mysql_seconds=(cooldown_end - start).total_seconds())
    run = {"cap": args.cap, "buyers": args.buyers, "seconds": args.seconds, "region": state["location"],
           "ran_at": start.isoformat(timespec="seconds"), **summary, "usage": usage,
           "cost_usd": {k: round(v, 4) for k, v in cost.items()},
           "cost_per_1k_usd": per_thousand(cost["total"], summary["completed"])}
    results = json.loads(RESULTS_FILE.read_text()) if RESULTS_FILE.exists() else {}
    RESULTS_FILE.write_text(json.dumps(merge_run({**results, "prices": PRICES}, run), indent=2) + "\n")
    per_1k = "no completed orders" if run["cost_per_1k_usd"] is None else f"${run['cost_per_1k_usd']} per 1,000 orders"
    print(f"Cap {args.cap}: {summary['completed']} orders, {summary['success_rate']:.0%} succeeded, "
          f"${cost['total']:.4f}, {per_1k}. Saved to {RESULTS_FILE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
