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
]
GATEWAY = Service("gateway", REPO_ROOT / "gateway", 8100, "GATEWAY_PORT", "fastapi")

PYTHON_SERVICES = FLASK_SERVICES + [GATEWAY]

FRONTEND_DIR = REPO_ROOT / "frontend"
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", 5273))
