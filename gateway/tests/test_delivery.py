"""Pattern 3 page: which commit each service runs, compared with main the way Deploy decides, plus
the latest CI and Deploy runs. GitHub is faked at the HTTP layer: no network in unit tests."""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import delivery

client = TestClient(app)
MAIN = "abc123def4567890abc123def4567890abc12345"
REPO = delivery.GITHUB_REPO


def github_reply(request: httpx.Request) -> httpx.Response:
    """A fake api.github.com: main's head, a compare per old commit, the latest workflow runs."""
    path = request.url.path
    if path.endswith("/commits/main"):
        return httpx.Response(200, json={"sha": MAIN, "html_url": "https://github.com/x/commit/abc"})
    if "/compare/" in path:
        old = path.split("/compare/")[1].split("...")[0]
        files = {"0ld0ld0ld0ld": ["services/order/application/saga.py"],      # order changed since
                 "5ame5ame5ame": ["README.md", "services/order/run.py"]}[old]  # nothing of payment's
        return httpx.Response(200, json={"files": [{"filename": f} for f in files]})
    workflow = path.split("/workflows/")[1].split("/")[0]
    return httpx.Response(200, json={"workflow_runs": [{
        "status": "completed", "conclusion": "success", "head_sha": MAIN,
        "html_url": f"https://github.com/{REPO}/actions/runs/{workflow}", "created_at": "2026-11-15T20:00:00Z"}]})


@pytest.fixture(autouse=True)
def _fake_github_and_services(monkeypatch):
    delivery._cache.clear()
    monkeypatch.setattr(delivery, "TRANSPORT", httpx.MockTransport(github_reply))

    async def runtimes(request):
        return [
            {"service": "gateway", "instance": "gateway", "git_sha": "abc123def456"},
            {"service": "order", "instance": "order-1", "git_sha": "0ld0ld0ld0ld"},
            {"service": "payment", "instance": "payment-1", "git_sha": "5ame5ame5ame"},
            {"service": "user", "instance": "user-5101", "git_sha": "local"},
            {"service": "catalog", "instance": "catalog-1", "unreachable": True},
        ]

    monkeypatch.setattr(delivery, "collect_runtimes", runtimes)


def test_behind_means_what_deploy_means():
    """Deploy rebuilds only services whose code changed, so the page must not call the rest 'behind'."""
    status = {s["instance"]: s["status"] for s in client.get("/api/patterns/delivery").json()["services"]}
    assert status == {"gateway": "current", "order-1": "behind", "payment-1": "unchanged",
                      "user-5101": "local", "catalog-1": "unknown"}


def test_latest_ci_and_deploy_runs_are_linked():
    runs = client.get("/api/patterns/delivery").json()["runs"]
    assert runs["ci"]["conclusion"] == "success" and runs["ci"]["url"].endswith("/runs/ci.yml")
    assert runs["deploy"]["url"].endswith("/runs/deploy.yml")


def test_github_answers_are_reused_for_five_minutes(monkeypatch):
    calls = []
    monkeypatch.setattr(delivery, "TRANSPORT", httpx.MockTransport(lambda r: calls.append(r) or github_reply(r)))
    client.get("/api/patterns/delivery")
    first = len(calls)
    client.get("/api/patterns/delivery")
    assert len(calls) == first


def test_after_five_minutes_an_unchanged_answer_costs_no_rate_limit(monkeypatch):
    """GitHub does not count a 304 Not Modified against the 60-per-hour limit."""
    seen = []

    def reply(request):
        seen.append(request.headers.get("if-none-match"))
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, json={"sha": MAIN, "html_url": "u"}, headers={"ETag": '"v1"'})

    monkeypatch.setattr(delivery, "TRANSPORT", httpx.MockTransport(reply))
    assert asyncio.run(delivery.github_get("/x"))["sha"] == MAIN
    delivery._cache["/x"]["fetched_at"] -= delivery.CACHE_SECONDS + 1
    assert asyncio.run(delivery.github_get("/x"))["sha"] == MAIN
    assert seen == [None, '"v1"']


def test_a_rate_limited_github_keeps_the_last_good_answer(monkeypatch):
    monkeypatch.setattr(delivery, "TRANSPORT", httpx.MockTransport(github_reply))
    assert asyncio.run(delivery.github_get(f"/repos/{REPO}/commits/main"))["sha"] == MAIN
    delivery._cache[f"/repos/{REPO}/commits/main"]["fetched_at"] -= delivery.CACHE_SECONDS + 1
    monkeypatch.setattr(delivery, "TRANSPORT", httpx.MockTransport(lambda r: httpx.Response(403)))
    assert asyncio.run(delivery.github_get(f"/repos/{REPO}/commits/main"))["sha"] == MAIN


def test_github_down_or_odd_still_shows_the_services(monkeypatch):
    for transport in [httpx.MockTransport(lambda r: httpx.Response(503)),
                      httpx.MockTransport(lambda r: httpx.Response(200, json={"unexpected": True})),
                      httpx.MockTransport(lambda r: httpx.Response(200, text="not json"))]:
        delivery._cache.clear()
        monkeypatch.setattr(delivery, "TRANSPORT", transport)
        r = client.get("/api/patterns/delivery")
        assert r.status_code == 200
        body = r.json()
        assert body["main"] is None and body["runs"] == {"ci": None, "deploy": None}
        assert {s["status"] for s in body["services"]} <= {"unknown", "local"}
