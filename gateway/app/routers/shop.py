"""Reverse proxy: /api/shop/<path> -> /api/<path> on the service that owns <path>.

The owner is picked from the first path segment (config.ROUTE_OWNERS), e.g.
/api/shop/products -> catalog, /api/shop/order/checkout -> order. Only GET and POST are exposed;
nothing in the shop needs PUT or DELETE from the browser.

Paths owned by a login-required service are rejected with 401 here, at the edge, when the token is
missing or invalid, so the service is never called (pattern 10).
"""
import json

import httpx
from fastapi import APIRouter, Request, Response

from .. import config
from ..auth import TOKENS
from ..observability import upstream_headers

router = APIRouter(prefix="/api/shop", tags=["shop"])


def owner_of(path: str) -> str | None:
    return config.ROUTE_OWNERS.get(path.split("/", 1)[0])


def _error(status: int, message: str) -> Response:
    return Response(content=json.dumps({"message": message}), status_code=status, media_type="application/json")


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request) -> Response:
    owner = owner_of(path)
    if owner is None:
        return _error(404, f"No service owns path '{path}'")

    if owner in config.LOGIN_REQUIRED_OWNERS and TOKENS.verify(request.headers.get("authorization")) is None:
        return _error(401, "Not logged in (checked at the gateway)")

    body = await request.body()
    upstream = None
    async with httpx.AsyncClient(timeout=config.UPSTREAM_TIMEOUT_SECONDS) as client:
        # A replica that crashed stays in the registry until its heartbeat expires (about 10 s).
        # A refused connection means the request never arrived, so the next replica can safely
        # take it, even a POST (patterns 10 and 12).
        for base in config.candidates(owner):
            try:
                upstream = await client.request(
                    request.method, f"{base}/api/{path}", headers=upstream_headers(request),
                    params=request.query_params, content=body,
                )
                break
            except httpx.ConnectError as exc:
                error = exc
            except httpx.HTTPError as exc:
                error = exc
                break
    if upstream is None:
        return _error(503, f"'{owner}' service is unreachable: {error.__class__.__name__}")
    passthrough = {k: v for k, v in upstream.headers.items() if k.lower() == "x-instance-id"}
    return Response(content=upstream.content, status_code=upstream.status_code,
                    media_type=upstream.headers.get("content-type"), headers=passthrough)
