"""Environment-driven settings for the API gateway. No secrets required."""
import os

RUN_MODE = os.environ.get("RUN_MODE", "local")

# Where each service lives. Locally these are fixed ports (scripts/service_table.py passes them
# in); in Azure, provision sets them to the Container Apps URLs. Pattern 12 (Service Discovery,
# milestone M2) replaces this static map with registry lookups.
SERVICE_BASE_URLS: dict[str, str] = {
    "user": os.environ.get("USER_SERVICE_BASE_URL", "http://127.0.0.1:5101"),
    "catalog": os.environ.get("CATALOG_SERVICE_BASE_URL", "http://127.0.0.1:5102"),
    "order": os.environ.get("ORDER_SERVICE_BASE_URL", "http://127.0.0.1:5103"),
    "payment": os.environ.get("PAYMENT_SERVICE_BASE_URL", "http://127.0.0.1:5104"),
    "inventory": os.environ.get("INVENTORY_SERVICE_BASE_URL", "http://127.0.0.1:5105"),
}

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
