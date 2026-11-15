from fastapi.testclient import TestClient

from app.main import app
from app.routers.shop import owner_of

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "gateway"}


def test_routes_each_path_to_its_owning_service():
    assert owner_of("products") == "catalog"
    assert owner_of("product/create") == "catalog"
    assert owner_of("user/login") == "user"
    assert owner_of("order/checkout") == "order"
    assert owner_of("payments/charge") is None


def test_unknown_path_returns_404():
    r = client.get("/api/shop/nothing-here")
    assert r.status_code == 404


def test_unreachable_service_returns_503(monkeypatch):
    from app import config

    monkeypatch.setitem(config.SERVICE_BASE_URLS, "catalog", "http://127.0.0.1:9")  # nothing listens on :9
    r = client.get("/api/shop/products")
    assert r.status_code == 503
    assert "catalog" in r.json()["message"]


def test_services_lists_all_three():
    r = client.get("/api/services")
    assert r.status_code == 200
    assert set(r.json()) == {"user", "catalog", "order"}
