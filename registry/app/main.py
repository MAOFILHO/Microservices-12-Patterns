"""Service registry (pattern 12): who is running, and where.

Instances POST /register every couple of seconds (a heartbeat). An instance that misses
heartbeats for longer than TTL_SECONDS is dropped, so a crashed replica disappears by itself.
State is in memory on purpose: after a registry restart, every live instance re-registers
within one heartbeat.

Locally only. In Azure, Container Apps' built-in DNS does this job (DISCOVERY=dns, see docs).
"""
import os
import threading
import time
from collections import deque

from fastapi import FastAPI
from pydantic import BaseModel, Field

TTL_SECONDS = float(os.environ.get("REGISTRY_TTL_SECONDS", "10"))

app = FastAPI(title="Microservices 12 Patterns — Service Registry", version="0.1.0")

_lock = threading.Lock()
_instances: dict[tuple[str, str], dict] = {}
_events: deque = deque(maxlen=50)


class Registration(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    instance_id: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=200)


def _event(kind: str, name: str, instance_id: str) -> None:
    _events.appendleft({"at": time.time(), "event": kind, "service": name, "instance_id": instance_id})


def _expire(now: float) -> None:
    for key, inst in list(_instances.items()):
        if now - inst["last_seen"] > TTL_SECONDS:
            del _instances[key]
            _event("expired", *key)


@app.get("/health")
def health():
    return {"status": "ok", "service": "registry"}


@app.post("/register")
def register(reg: Registration):
    now = time.monotonic()
    with _lock:
        key = (reg.name, reg.instance_id)
        if key not in _instances:
            _instances[key] = {"registered_at": now}
            _event("registered", *key)
        _instances[key].update(url=reg.url, last_seen=now)
    return {"registered": reg.instance_id, "ttl_seconds": TTL_SECONDS}


@app.delete("/register/{name}/{instance_id}")
def deregister(name: str, instance_id: str):
    with _lock:
        if _instances.pop((name, instance_id), None) is not None:
            _event("deregistered", name, instance_id)
            return {"deregistered": instance_id}
    return {"deregistered": None}


@app.get("/services")
def services():
    now = time.monotonic()
    with _lock:
        _expire(now)
        result: dict[str, list[dict]] = {}
        for (name, instance_id), inst in sorted(_instances.items()):
            result.setdefault(name, []).append({
                "instance_id": instance_id,
                "url": inst["url"],
                "last_heartbeat_s": round(now - inst["last_seen"], 1),
                "up_for_s": round(now - inst["registered_at"], 1),
            })
        return {"ttl_seconds": TTL_SECONDS, "services": result, "events": list(_events)}
