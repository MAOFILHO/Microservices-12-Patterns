"""Reverse proxy: /api/shop/<path> -> /api/<path> on the service that owns <path>.

The owner is picked from the first path segment (config.ROUTE_OWNERS), e.g.
/api/shop/products -> catalog, /api/shop/order/checkout -> order.
"""
import json

import httpx
from fastapi import APIRouter, Request, Response

from .. import config

router = APIRouter(prefix="/api/shop", tags=["shop"])


def owner_of(path: str) -> str | None:
    return config.ROUTE_OWNERS.get(path.split("/", 1)[0])


def _error(status: int, message: str) -> Response:
    return Response(content=json.dumps({"message": message}), status_code=status, media_type="application/json")


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request) -> Response:
    owner = owner_of(path)
    if owner is None:
        return _error(404, f"No service owns path '{path}'")

    url = f"{config.SERVICE_BASE_URLS[owner]}/api/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            upstream = await client.request(
                request.method, url, headers=headers, params=request.query_params, content=await request.body()
            )
    except httpx.HTTPError as exc:
        return _error(503, f"'{owner}' service is unreachable: {exc.__class__.__name__}")
    return Response(content=upstream.content, status_code=upstream.status_code,
                    media_type=upstream.headers.get("content-type"))
