"""#10: the CI-CD page. Which commit each service runs, compared with the latest commit on main,
plus the latest CI and Deploy runs. GitHub is stubbed: no network in unit tests."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import delivery

client = TestClient(app)
MAIN = "abc123def4567890abc123def4567890abc12345"


@pytest.fixture(autouse=True)
def _stub(monkeypatch):
    delivery._cache.clear()

    async def runtime(request):
        return [
            {"service": "gateway", "instance": "gateway", "git_sha": "abc123def456"},
            {"service": "order", "instance": "order-1", "git_sha": "0ld0ld0ld0ld"},
            {"service": "user", "instance": "user-5101", "git_sha": "local"},
            {"service": "payment", "instance": "payment-1", "unreachable": True},
        ]

    async def github(path):
        if path.endswith("/commits/main"):
            return {"sha": MAIN, "html_url": "https://github.com/x/commit/abc"}
        return {"workflow_runs": [{"status": "completed", "conclusion": "success", "head_sha": MAIN,
                                   "html_url": f"https://github.com/x/runs/{path.split('/')[-2]}",
                                   "created_at": "2026-11-15T20:00:00Z"}]}

    monkeypatch.setattr(delivery, "process_runtimes", runtime)
    monkeypatch.setattr(delivery, "github_get", github)


def test_each_service_is_marked_current_behind_local_or_unknown():
    body = client.get("/api/patterns/delivery").json()
    status = {s["instance"]: s["status"] for s in body["services"]}
    assert status == {"gateway": "current", "order-1": "behind", "user-5101": "local", "payment-1": "unknown"}
    assert body["main"]["short"] == MAIN[:12]


def test_latest_ci_and_deploy_runs_are_linked():
    runs = client.get("/api/patterns/delivery").json()["runs"]
    assert runs["ci"]["conclusion"] == "success" and runs["ci"]["url"].endswith("ci.yml")
    assert runs["deploy"]["url"].endswith("deploy.yml")


def test_github_unreachable_still_shows_the_services(monkeypatch):
    async def down(path):
        return None

    monkeypatch.setattr(delivery, "github_get", down)
    body = client.get("/api/patterns/delivery").json()
    assert body["main"] is None and body["runs"] == {"ci": None, "deploy": None}
    assert {s["status"] for s in body["services"]} <= {"unknown", "local"}
