"""Service discovery client (pattern 12).

With REGISTRY_URL set, a process can:
  - register itself: it re-announces its name, instance id and URL every HEARTBEAT_SECONDS, and
    the registry forgets it once heartbeats stop for longer than the registry's TTL;
  - look others up: it keeps a snapshot of the registry, refreshed every HEARTBEAT_SECONDS, and
    url_for() round-robins across the live instances of a service.

Without REGISTRY_URL (unit tests, Azure where Container Apps DNS does the job), url_for() returns
the static fallback URL, so callers need no special case.

Uses urllib on purpose: these background calls are not instrumented, so they do not flood the
trace store with a span every 2 seconds.
"""
import itertools
import json
import os
import threading
import time
import urllib.request

HEARTBEAT_SECONDS = 2.0


def _registry_url() -> str | None:
    return os.environ.get("REGISTRY_URL") or None


class Discovery:
    def __init__(self) -> None:
        self._snapshot: dict[str, list[dict]] = {}
        self._registration: dict | None = None
        self._counters: dict[str, itertools.count] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return _registry_url() is not None

    def register(self, name: str, instance_id: str, url: str) -> None:
        self._registration = {"name": name, "instance_id": instance_id, "url": url}
        self.start()

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="discovery", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            self.tick()
            time.sleep(HEARTBEAT_SECONDS)

    def tick(self) -> None:
        """One heartbeat plus one snapshot refresh. Failures are ignored; the next tick retries."""
        base = _registry_url()
        if base is None:
            return
        if self._registration:
            try:
                req = urllib.request.Request(
                    f"{base}/register", data=json.dumps(self._registration).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                urllib.request.urlopen(req, timeout=2).close()
            except OSError:
                pass
        try:
            with urllib.request.urlopen(f"{base}/services", timeout=2) as resp:
                services = json.load(resp)["services"]
            with self._lock:
                self._snapshot = services
        except (OSError, ValueError, KeyError):
            pass

    def instances(self, name: str) -> list[dict]:
        with self._lock:
            return list(self._snapshot.get(name, []))

    def url_for(self, name: str, fallback: str) -> str:
        """A live instance's URL (round-robin), or the static fallback if none is known."""
        live = self.instances(name)
        if not live:
            return fallback
        counter = self._counters.setdefault(name, itertools.count())
        return live[next(counter) % len(live)]["url"]


DISCOVERY = Discovery()
