#!/usr/bin/env python3
"""make run — launches the full local stack as plain Python/Node processes.

No Docker Desktop, no containers. Starts the registry, every Flask service (order twice), then
the gateway, then the frontend, each gated on its /health endpoint. The list comes from
scripts/service_table.py.

A service process that exits (for example one stopped from the Stateless or Service Discovery
demo) is restarted after RESTART_DELAY_SECONDS, so the registry shows it leave and come back.
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
from service_table import (  # noqa: E402
    FLASK_SERVICES, FRONTEND_DIR, FRONTEND_PORT, GATEWAY, REGISTRY, REPLICA_PORTS, Service,
)

RESTART_DELAY_SECONDS = 20
processes: list[subprocess.Popen] = []
# pid -> how to start that process again (Flask services only)
restartable: dict[int, tuple[str, object]] = {}


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
    """Every process gets every service's static URL (the fallback), the registry, and the demo switches."""
    env = {f"{s.name.upper()}_SERVICE_BASE_URL": s.local_url for s in FLASK_SERVICES}
    env.update(REGISTRY_URL=REGISTRY.local_url, CHAOS_ENABLED="1")
    return env


def start_registry() -> subprocess.Popen:
    ensure_port_free(REGISTRY.local_port, REGISTRY.name)
    proc = subprocess.Popen(
        [_venv_python(REGISTRY.path), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(REGISTRY.local_port), "--log-level", "warning"],
        cwd=str(REGISTRY.path), env={**os.environ},
    )
    processes.append(proc)
    print(f"  registry starting on :{REGISTRY.local_port} (pid {proc.pid})…")
    return proc


def start_flask_service(svc: Service, port: int | None = None) -> subprocess.Popen:
    port = port or svc.local_port
    ensure_port_free(port, svc.name)
    url = f"http://127.0.0.1:{port}"
    env = {**os.environ, **_service_url_env(), "RUN_MODE": "local", "FLASK_ENV": "development",
           svc.port_env: str(port), "INSTANCE_ID": f"{svc.name}-{port}", "SERVICE_PUBLIC_URL": url}
    proc = subprocess.Popen([_venv_python(svc.path), "run.py"], cwd=str(svc.path), env=env)
    processes.append(proc)
    restartable[proc.pid] = (svc, port)
    print(f"  {svc.name}-{port} starting on :{port} (pid {proc.pid})…")
    return proc


def _flask_instances() -> list[tuple[Service, int]]:
    return [(svc, port) for svc in FLASK_SERVICES for port in [svc.local_port, *REPLICA_PORTS.get(svc.name, [])]]


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
    start_registry()
    if not _wait_for_health(f"{REGISTRY.local_url}/health"):
        print("registry failed to become healthy — aborting.")
        shutdown()
        return 1
    for svc, port in _flask_instances():
        start_flask_service(svc, port)
    for svc, port in _flask_instances():
        if not _wait_for_health(f"http://127.0.0.1:{port}/health"):
            print(f"{svc.name}-{port} failed to become healthy — aborting.")
            shutdown()
            return 1

    start_gateway()
    if not _wait_for_health(f"{GATEWAY.local_url}/health"):
        print("gateway failed to become healthy — aborting.")
        shutdown()
        return 1

    start_frontend()

    services = "\n".join(f"  {svc.name:<9} http://127.0.0.1:{port}" for svc, port in _flask_instances())
    print(f"""
Local stack is up:
  Frontend  http://127.0.0.1:{FRONTEND_PORT}
  Gateway   {GATEWAY.local_url}
  Registry  {REGISTRY.local_url}
{services}

Press Ctrl+C to stop everything.
""")

    pending: dict[int, float] = {}  # pid of an exited service -> when to restart it
    try:
        while True:
            time.sleep(1)
            for proc in list(processes):
                if proc.poll() is None or proc.pid in pending:
                    continue
                if proc.pid in restartable:
                    svc, port = restartable[proc.pid]
                    print(f"{svc.name}-{port} exited (code {proc.returncode}); restarting in {RESTART_DELAY_SECONDS} s.")
                    pending[proc.pid] = time.monotonic() + RESTART_DELAY_SECONDS
                else:
                    print(f"Process {proc.pid} exited unexpectedly (code {proc.returncode}).")
                    pending[proc.pid] = float("inf")
            for pid, when in list(pending.items()):
                if time.monotonic() >= when:
                    del pending[pid]
                    svc, port = restartable.pop(pid)
                    processes[:] = [p for p in processes if p.pid != pid]
                    start_flask_service(svc, port)
    except KeyboardInterrupt:
        shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
