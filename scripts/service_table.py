"""The one place that lists every locally-run process, its folder and its port.

setup.py, run_local.py, _procutil.py and the smoke tests all read from here, so adding a
service (payment, inventory, registry in later milestones) is a one-line change.
Ports are offset from the parent project (5001-5003, 8000, 5173) so both can run at once.
"""
import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Service:
    name: str          # short name, also the gateway route owner and the Azure Container App name
    path: Path         # folder holding run.py (Flask) or app/ (FastAPI) and its own .venv
    port: int          # default local port
    port_env: str      # env var the process reads its port from
    kind: str          # "flask" or "fastapi"

    @property
    def local_port(self) -> int:
        return int(os.environ.get(self.port_env, self.port))

    @property
    def local_url(self) -> str:
        return f"http://127.0.0.1:{self.local_port}"


FLASK_SERVICES = [
    Service("user", REPO_ROOT / "services" / "user", 5101, "USER_SERVICE_PORT", "flask"),
    Service("catalog", REPO_ROOT / "services" / "catalog", 5102, "CATALOG_SERVICE_PORT", "flask"),
    Service("order", REPO_ROOT / "services" / "order", 5103, "ORDER_SERVICE_PORT", "flask"),
    Service("payment", REPO_ROOT / "services" / "payment", 5104, "PAYMENT_SERVICE_PORT", "flask"),
    Service("inventory", REPO_ROOT / "services" / "inventory", 5105, "INVENTORY_SERVICE_PORT", "flask"),
]
GATEWAY = Service("gateway", REPO_ROOT / "gateway", 8100, "GATEWAY_PORT", "fastapi")
REGISTRY = Service("registry", REPO_ROOT / "registry", 8500, "REGISTRY_PORT", "fastapi")

PYTHON_SERVICES = FLASK_SERVICES + [GATEWAY, REGISTRY]

# The event bus (patterns 7 and 8): a Homebrew redis-server, no Docker. Offset from Redis' default
# 6379 so a Redis the owner already runs is never touched.
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6390))
REDIS_URL = f"redis://127.0.0.1:{REDIS_PORT}/0"

# Extra local replicas (pattern 10): service name -> extra ports. Each runs as its own process
# from the same folder, and registers with the registry under its own instance id.
REPLICA_PORTS: dict[str, list[int]] = {"order": [5113]}

# Suites whose tests need pact-python (pattern 11): order is the consumer; payment, catalog and inventory
# verify they still honour its contracts.
CONTRACT_SUITES = {"order", "payment", "catalog", "inventory"}
CONTRACTS_DIR = REPO_ROOT / "contracts"

# shop_common (shared/), installed into every Python venv by setup.py.
SHARED_DIR = REPO_ROOT / "shared"
FRONTEND_DIR = REPO_ROOT / "frontend"
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", 5273))
