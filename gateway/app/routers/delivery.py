"""Live demo endpoint for pattern 3 (CI-CD).

Which commit each running service was built from, compared with the latest commit on main, and
the latest CI and Deploy runs. GitHub data comes from its public REST API (this repo is public, so
no token). Anonymous callers get 60 requests an hour, so every answer is reused for 5 minutes and
then re-checked with its ETag: an unchanged answer (304) does not count against that limit. If
GitHub refuses or fails, the last good answer is kept.
"""
import asyncio
import os
import time

import httpx
from fastapi import APIRouter, Request

from .resilience import collect_runtimes

router = APIRouter(prefix="/api/patterns", tags=["patterns"])

GITHUB_REPO = os.environ.get("GITHUB_REPO", "MAOFILHO/Microservices-12-Patterns")
CACHE_SECONDS = 300
WORKFLOWS = {"ci": "ci.yml", "deploy": "deploy.yml"}
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests swap in a fake GitHub
_cache: dict[str, dict] = {}  # path -> {"body", "etag", "fetched_at"}; a handful of fixed paths

# The same rule the Deploy workflow uses (scripts/ci_changes.py, not shipped in this image): a
# service needs a new build when a change touches its folder or code every service shares.
EVERY_SERVICE = ("shared/", "scripts/service_table.py")


def _folder(service: str) -> str:
    return "gateway/" if service == "gateway" else f"services/{service}/"


async def github_get(path: str):
    """GET api.github.com<path>, reused for CACHE_SECONDS, then revalidated with its ETag."""
    entry = _cache.get(path)
    if entry and time.monotonic() - entry["fetched_at"] < CACHE_SECONDS:
        return entry["body"]
    headers = {"Accept": "application/vnd.github+json"}
    if entry and entry.get("etag"):
        headers["If-None-Match"] = entry["etag"]
    try:
        async with httpx.AsyncClient(timeout=5, transport=TRANSPORT) as client:
            response = await client.get(f"https://api.github.com{path}", headers=headers)
        if response.status_code == 304 and entry:
            body, etag = entry["body"], entry.get("etag")
        elif response.status_code == 200:
            body, etag = response.json(), response.headers.get("ETag")
        else:  # rate limited or down: keep the last good answer, if any
            body, etag = (entry or {}).get("body"), (entry or {}).get("etag")
    except (httpx.HTTPError, ValueError):
        body, etag = (entry or {}).get("body"), (entry or {}).get("etag")
    _cache[path] = {"body": body, "etag": etag, "fetched_at": time.monotonic()}
    return body


async def _latest_run(name: str, file: str) -> dict | None:
    body = await github_get(f"/repos/{GITHUB_REPO}/actions/workflows/{file}/runs?branch=main&per_page=1")
    runs = body.get("workflow_runs") if isinstance(body, dict) else None
    run = runs[0] if runs else None
    if not isinstance(run, dict) or not run.get("html_url"):
        return None
    return {"workflow": name, "status": run.get("status"), "conclusion": run.get("conclusion"),
            "commit": (run.get("head_sha") or "")[:12], "url": run["html_url"], "created_at": run.get("created_at")}


async def _changed_files(commit: str, main_sha: str) -> list[str] | None:
    body = await github_get(f"/repos/{GITHUB_REPO}/compare/{commit}...{main_sha}")
    files = body.get("files") if isinstance(body, dict) else None
    return [f.get("filename", "") for f in files] if isinstance(files, list) else None


def _status(process: dict, main_sha: str | None, changed: dict[str, list[str] | None]) -> str:
    """current: built from main. behind: main has changes for it (Deploy would rebuild it).
    unchanged: built from an older commit, but nothing of its code changed since. local / unknown."""
    commit = process.get("git_sha")
    if process.get("unreachable") or not commit or commit == "unknown":
        return "unknown"
    if commit == "local":
        return "local"
    if main_sha is None:
        return "unknown"
    if main_sha.startswith(commit):
        return "current"
    files = changed.get(commit)
    if files is None:
        return "unknown"
    touches = (_folder(process["service"]), *EVERY_SERVICE)
    return "behind" if any(f.startswith(touches) for f in files) else "unchanged"


@router.get("/delivery")
async def delivery(request: Request):
    head, ci, deploy, processes = await asyncio.gather(
        github_get(f"/repos/{GITHUB_REPO}/commits/main"),
        _latest_run("ci", WORKFLOWS["ci"]),
        _latest_run("deploy", WORKFLOWS["deploy"]),
        collect_runtimes(request),
    )
    main_sha = head.get("sha") if isinstance(head, dict) else None
    main = {"sha": main_sha, "short": main_sha[:12], "url": head.get("html_url")} if main_sha else None

    older = sorted({p.get("git_sha") for p in processes
                    if p.get("git_sha") and p.get("git_sha") not in ("local", "unknown")
                    and not (main_sha or "").startswith(p.get("git_sha"))})
    compared = await asyncio.gather(*(_changed_files(c, main_sha) for c in older)) if main_sha else []
    changed = dict(zip(older, compared))

    services = [{"service": p["service"], "instance": p["instance"], "git_sha": p.get("git_sha"),
                 "status": _status(p, main_sha, changed)} for p in processes]
    return {"repo": GITHUB_REPO, "main": main, "services": services, "runs": {"ci": ci, "deploy": deploy}}
