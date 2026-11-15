"""Environment-driven settings for the API gateway. No secrets required."""
import os

from shop_common.discovery import DISCOVERY

RUN_MODE = os.environ.get("RUN_MODE", "local")

# Where each service lives when there is no registry: fixed local ports, or the Container Apps URLs
# in Azure. With REGISTRY_URL set (make run), url_for() asks the registry instead (pattern 12).
SERVICE_BASE_URLS: dict[str, str] = {
    "user": os.environ.get("USER_SERVICE_BASE_URL", "http://127.0.0.1:5101"),
    "catalog": os.environ.get("CATALOG_SERVICE_BASE_URL", "http://127.0.0.1:5102"),
    "order": os.environ.get("ORDER_SERVICE_BASE_URL", "http://127.0.0.1:5103"),
    "payment": os.environ.get("PAYMENT_SERVICE_BASE_URL", "http://127.0.0.1:5104"),
    "inventory": os.environ.get("INVENTORY_SERVICE_BASE_URL", "http://127.0.0.1:5105"),
}



def url_for(service: str) -> str:
    """A live instance of the service (round-robin across replicas), or its static URL."""
    return DISCOVERY.url_for(service, SERVICE_BASE_URLS[service])


def candidates(service: str) -> list[str]:
    """The round-robin pick first, then every other live instance, for failover."""
    first = url_for(service)
    return [first] + [u for u in urls_for(service) if u != first]


def urls_for(service: str) -> list[str]:
    """Every live instance of the service, e.g. both order replicas, for fan-out reads."""
    return [i["url"] for i in DISCOVERY.instances(service)] or [SERVICE_BASE_URLS[service]]


# Services whose every route needs a signed-in user. The gateway checks the token once, at the
# edge, before any call is made (pattern 10). The service still verifies it too.
LOGIN_REQUIRED_OWNERS = {"order"}

# The demo pages can stop a replica (patterns 10, 12) and break payment (pattern 4) only when on.
CHAOS_ENABLED = os.environ.get("CHAOS_ENABLED") == "1"

# The service registry (pattern 12). Unset in unit tests and in Azure (Container Apps DNS).
REGISTRY_URL = os.environ.get("REGISTRY_URL") or None

# First path segment of /api/shop/<path> -> owning service (its bounded context).
ROUTE_OWNERS: dict[str, str] = {
    "user": "user",
    "product": "catalog",
    "products": "catalog",
    "order": "order",
    "payment": "payment",
    "payments": "payment",
    "inventory": "inventory",
}

UPSTREAM_TIMEOUT_SECONDS = float(os.environ.get("UPSTREAM_TIMEOUT_SECONDS", "10"))

# Browsers treat 'localhost' and '127.0.0.1' as different CORS origins, and Vite binds to both,
# so allow both locally. If FRONTEND_ORIGIN is set (e.g. the Static Web App hostname in Azure),
# only that exact origin is allowed.
if os.environ.get("FRONTEND_ORIGIN"):
    FRONTEND_ORIGINS = [os.environ["FRONTEND_ORIGIN"]]
else:
    _port = os.environ.get("FRONTEND_ORIGIN_PORT", "5273")
    FRONTEND_ORIGINS = [f"http://127.0.0.1:{_port}", f"http://localhost:{_port}"]
