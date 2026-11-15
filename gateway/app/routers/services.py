"""Lists the services the gateway routes to and where it thinks they live."""
from fastapi import APIRouter

from .. import config

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("")
async def list_services() -> dict[str, str]:
    return dict(config.SERVICE_BASE_URLS)
