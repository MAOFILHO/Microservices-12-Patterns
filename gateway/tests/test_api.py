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
    assert owner_of("payment/charge") == "payment"
    assert owner_of("inventory/3") == "inventory"
    assert owner_of("admin/secrets") is None


def test_unknown_path_returns_404():
    r = client.get("/api/shop/nothing-here")
    assert r.status_code == 404


def test_unreachable_service_returns_503(monkeypatch):
    from app import config

    monkeypatch.setitem(config.SERVICE_BASE_URLS, "catalog", "http://127.0.0.1:9")  # nothing listens on :9
    r = client.get("/api/shop/products")
    assert r.status_code == 503
    assert "catalog" in r.json()["message"]


def test_services_lists_all_five():
    r = client.get("/api/services")
    assert r.status_code == 200
    assert set(r.json()) == {"user", "catalog", "order", "payment", "inventory"}


def test_every_response_carries_a_request_id_and_echoes_the_clients():
    assert len(client.get("/api/services").headers["X-Request-Id"]) == 16
    assert client.get("/api/services", headers={"X-Request-Id": "abc123"}).headers["X-Request-Id"] == "abc123"


def test_traced_responses_carry_a_trace_id():
    assert len(client.get("/api/services").headers["X-Trace-Id"]) == 32


def test_delete_is_not_proxied():
    assert client.delete("/api/shop/product/contoso-mug").status_code == 405


def test_order_summary_requires_login(monkeypatch):
    from app import config

    for name in config.SERVICE_BASE_URLS:
        monkeypatch.setitem(config.SERVICE_BASE_URLS, name, "http://127.0.0.1:9")
    r = client.get("/api/order-summary")
    assert r.status_code == 401
    assert {c["service"] for c in r.json()["calls"]} == {"user", "order"}


def test_order_paths_need_a_valid_token_at_the_edge(monkeypatch):
    from app import config

    called = []
    monkeypatch.setitem(config.SERVICE_BASE_URLS, "order", "http://127.0.0.1:9")
    monkeypatch.setattr("app.routers.shop.httpx.AsyncClient.request", lambda *a, **k: called.append(1))
    r = client.get("/api/shop/order", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
    assert "gateway" in r.json()["message"]
    assert called == []  # the order service was never called


def test_registry_view_falls_back_to_the_static_map():
    body = client.get("/api/patterns/registry").json()
    assert body["mode"] == "static"
    assert set(body["services"]) == {"user", "catalog", "order", "payment", "inventory"}


def test_chaos_switches_are_off_by_default():
    assert client.post("/api/patterns/replicas/order-5103/stop").status_code == 403
    assert client.post("/api/patterns/breaker/payment-mode", json={"mode": "failing"}).status_code == 403


def test_url_for_round_robins_across_registered_replicas(monkeypatch):
    from app import config
    from shop_common.discovery import DISCOVERY

    monkeypatch.setattr(DISCOVERY, "_snapshot", {"order": [{"url": "http://a"}, {"url": "http://b"}]})
    assert {config.url_for("order") for _ in range(4)} == {"http://a", "http://b"}
    assert config.urls_for("order") == ["http://a", "http://b"]
    assert config.url_for("user") == config.SERVICE_BASE_URLS["user"]


def test_proxy_fails_over_when_a_replica_refuses_the_connection(monkeypatch):
    import httpx

    from app import config
    from shop_common.discovery import DISCOVERY

    monkeypatch.setattr(DISCOVERY, "_snapshot", {"catalog": [{"url": "http://dead"}, {"url": "http://alive"}]})
    tried = []

    async def fake_request(self, method, url, **kwargs):
        tried.append(url)
        if url.startswith("http://dead"):
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"results": []}, headers={"X-Instance-Id": "catalog-alive"})

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    for _ in range(2):  # whichever replica round-robin picks first, the call succeeds
        r = client.get("/api/shop/products")
        assert r.status_code == 200
        assert r.headers["X-Instance-Id"] == "catalog-alive"
    assert "http://dead/api/products" in tried


def test_events_view_reports_unreachable_services_as_none(monkeypatch):
    from app import config

    for name in config.SERVICE_BASE_URLS:
        monkeypatch.setitem(config.SERVICE_BASE_URLS, name, "http://127.0.0.1:9")
    body = client.get("/api/patterns/events").json()
    assert body["outbox"] is None and body["stock"] is None
    assert client.post("/api/patterns/events/bus", json={"connected": False}).status_code == 403


def test_runtime_reports_the_gateway_without_a_user_name():
    gateway = client.get("/api/patterns/runtime").json()["processes"][0]
    assert gateway["service"] == "gateway"
    assert set(gateway) >= {"uid", "root", "in_container", "arch", "git_sha"}
    assert "user" not in gateway


def test_runtime_reports_the_image_size_the_deploy_recorded(monkeypatch):
    monkeypatch.setenv("IMAGE_SIZE_MB", "61")
    assert client.get("/api/patterns/runtime").json()["processes"][0]["image_size_mb"] == 61
    monkeypatch.delenv("IMAGE_SIZE_MB")
    assert client.get("/api/patterns/runtime").json()["processes"][0]["image_size_mb"] is None
