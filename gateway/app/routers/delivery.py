"""Live demo endpoint for pattern 3 (CI-CD).

Which commit each running service was built from, compared with the latest commit on main, and
the latest CI and Deploy runs. GitHub data comes from its public REST API (this repo is public, so
no token), cached for 60 s to stay far below the 60-requests-per-hour anonymous limit.
"""
import os
import time

import httpx
from fastapi import APIRouter, Request

from .resilience import runtime as runtime_endpoint

router = APIRouter(prefix="/api/patterns", tags=["patterns"])

GITHUB_REPO = os.environ.get("GITHUB_REPO", "MAOFILHO/Microservices-12-Patterns")
CACHE_SECONDS = 60
WORKFLOWS = {"ci": "ci.yml", "deploy": "deploy.yml"}
_cache: dict[str, tuple[float, object]] = {}


async def github_get(path: str):
    """GET api.github.com<path>, cached; None when GitHub is unreachable or says no."""
    hit = _cache.get(path)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"https://api.github.com{path}",
                                        headers={"Accept": "application/vnd.github+json"})
        body = response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        body = None
    _cache[path] = (time.monotonic(), body)
    return body


async def process_runtimes(request: Request) -> list[dict]:
    return (await runtime_endpoint(request))["processes"]


def _status(process: dict, main_sha: str | None) -> str:
    commit = process.get("git_sha")
    if process.get("unreachable") or not commit or commit == "unknown":
        return "unknown"
    if commit == "local":
        return "local"
    if main_sha is None:
        return "unknown"
    return "current" if main_sha.startswith(commit) else "behind"


async def _latest_run(name: str, file: str) -> dict | None:
    body = await github_get(f"/repos/{GITHUB_REPO}/actions/workflows/{file}/runs?branch=main&per_page=1")
    runs = (body or {}).get("workflow_runs") or []
    if not runs:
        return None
    run = runs[0]
    return {"workflow": name, "status": run["status"], "conclusion": run["conclusion"],
            "commit": run["head_sha"][:12], "url": run["html_url"], "created_at": run["created_at"]}


@router.get("/delivery")
async def delivery(request: Request):
    head = await github_get(f"/repos/{GITHUB_REPO}/commits/main")
    main = {"sha": head["sha"], "short": head["sha"][:12], "url": head["html_url"]} if head else None
    services = [{"service": p["service"], "instance": p["instance"], "git_sha": p.get("git_sha"),
                 "status": _status(p, main["sha"] if main else None)} for p in await process_runtimes(request)]
    runs = {name: await _latest_run(name, file) for name, file in WORKFLOWS.items()}
    return {"repo": GITHUB_REPO, "main": main, "services": services, "runs": runs}
