#!/usr/bin/env python3
"""make run — launches the full local stack as plain Python/Node processes.

No Docker Desktop, no containers. Starts every Flask service, then the gateway, then the
frontend, each gated on its /health endpoint. The list comes from scripts/service_table.py.
"""
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _procutil import ensure_port_free  # noqa: E402
from service_table import FLASK_SERVICES, FRONTEND_DIR, FRONTEND_PORT, GATEWAY, Service  # noqa: E402

processes: list[subprocess.Popen] = []


def _venv_python(service_dir: Path) -> str:
    venv_python = service_dir / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else sys.executable


def _wait_for_health(url: str, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.5)
    return False


def _service_url_env() -> dict[str, str]:
    """Every process gets every service's local URL (e.g. USER_SERVICE_BASE_URL)."""
    return {f"{s.name.upper()}_SERVICE_BASE_URL": s.local_url for s in FLASK_SERVICES}


def start_flask_service(svc: Service) -> subprocess.Popen:
    ensure_port_free(svc.local_port, svc.name)
    env = {**os.environ, **_service_url_env(), "RUN_MODE": "local", "FLASK_ENV": "development",
           svc.port_env: str(svc.local_port)}
    proc = subprocess.Popen([_venv_python(svc.path), "run.py"], cwd=str(svc.path), env=env)
    processes.append(proc)
    print(f"  {svc.name} starting on :{svc.local_port} (pid {proc.pid})…")
    return proc


def start_gateway() -> subprocess.Popen:
    ensure_port_free(GATEWAY.local_port, GATEWAY.name)
    env = {**os.environ, **_service_url_env(), "RUN_MODE": "local",
           "FRONTEND_ORIGIN_PORT": str(FRONTEND_PORT)}
    proc = subprocess.Popen(
        [_venv_python(GATEWAY.path), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0",
         "--port", str(GATEWAY.local_port)],
        cwd=str(GATEWAY.path),
        env=env,
    )
    processes.append(proc)
    print(f"  gateway starting on :{GATEWAY.local_port} (pid {proc.pid})…")
    return proc


def start_frontend() -> subprocess.Popen:
    ensure_port_free(FRONTEND_PORT, "frontend")
    env = {**os.environ, "FRONTEND_PORT": str(FRONTEND_PORT), "VITE_GATEWAY_BASE_URL": GATEWAY.local_url}
    proc = subprocess.Popen(["npm", "run", "dev", "--", "--port", str(FRONTEND_PORT)], cwd=str(FRONTEND_DIR), env=env)
    processes.append(proc)
    print(f"  frontend starting on :{FRONTEND_PORT} (pid {proc.pid})…")
    return proc


def shutdown(*_args):
    print("\nShutting down local stack…")
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    for proc in processes:
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    sys.exit(0)


def main() -> int:
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("=== Starting local stack (no Docker) ===")
    for svc in FLASK_SERVICES:
        start_flask_service(svc)
    for svc in FLASK_SERVICES:
        if not _wait_for_health(f"{svc.local_url}/health"):
            print(f"{svc.name} failed to become healthy — aborting.")
            shutdown()
            return 1

    start_gateway()
    if not _wait_for_health(f"{GATEWAY.local_url}/health"):
        print("gateway failed to become healthy — aborting.")
        shutdown()
        return 1

    start_frontend()

    services = "\n".join(f"  {s.name:<9} {s.local_url}" for s in FLASK_SERVICES)
    print(f"""
Local stack is up:
  Frontend  http://127.0.0.1:{FRONTEND_PORT}
  Gateway   {GATEWAY.local_url}
{services}

Press Ctrl+C to stop everything.
""")

    try:
        while True:
            time.sleep(1)
            for proc in processes:
                if proc.poll() is not None:
                    print(f"Process {proc.pid} exited unexpectedly (code {proc.returncode}).")
    except KeyboardInterrupt:
        shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
