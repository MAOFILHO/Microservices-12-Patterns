import time

from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def _register(name="order", instance_id="order-5103", url="http://127.0.0.1:5103"):
    return client.post("/register", json={"name": name, "instance_id": instance_id, "url": url})


def setup_function():
    main._instances.clear()
    main._events.clear()


def test_registered_instances_are_listed_by_service():
    _register()
    _register(instance_id="order-5113", url="http://127.0.0.1:5113")
    body = client.get("/services").json()
    assert [i["instance_id"] for i in body["services"]["order"]] == ["order-5103", "order-5113"]
    assert [e["event"] for e in body["events"]] == ["registered", "registered"]


def test_heartbeat_keeps_one_entry_per_instance():
    _register()
    _register()
    assert len(client.get("/services").json()["services"]["order"]) == 1


def test_silent_instances_expire_after_the_ttl(monkeypatch):
    _register()
    later = time.monotonic() + main.TTL_SECONDS + 1
    monkeypatch.setattr(main.time, "monotonic", lambda: later)
    body = client.get("/services").json()
    assert body["services"] == {}
    assert body["events"][0]["event"] == "expired"


def test_deregister_removes_the_instance():
    _register()
    assert client.delete("/register/order/order-5103").json() == {"deregistered": "order-5103"}
    assert client.get("/services").json()["services"] == {}


def test_bad_registration_is_rejected():
    assert client.post("/register", json={"name": "", "instance_id": "x", "url": "u"}).status_code == 422
