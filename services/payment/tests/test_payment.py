def test_charge_records_an_approved_payment(client):
    r = client.post("/api/payment/charge", data={"order_id": 7, "amount_cents": 3798})
    assert r.status_code == 200
    assert r.get_json()["result"]["status"] == "APPROVED"
    assert client.get("/api/payments").get_json()["results"][0]["order_id"] == 7


def test_charge_rejects_bad_input(client):
    assert client.post("/api/payment/charge", data={"order_id": 0, "amount_cents": 10}).status_code == 400
    assert client.post("/api/payment/charge", data={"order_id": 1}).status_code == 400


def test_health_db_reports_only_own_tables(client):
    body = client.get("/health/db").get_json()
    assert body["service"] == "payment"
    assert body["tables"] == ["payment"]


def test_charge_accepts_json(client):
    r = client.post("/api/payment/charge", json={"order_id": 3, "amount_cents": 500})
    assert r.get_json()["result"]["amount_cents"] == 500


def test_failing_mode_returns_500_until_healed(client, monkeypatch):
    monkeypatch.setenv("CHAOS_ENABLED", "1")
    assert client.post("/api/payment/chaos", json={"mode": "failing"}).get_json()["mode"] == "failing"
    assert client.get("/api/payment/ping").status_code == 500
    client.post("/api/payment/chaos", json={"mode": "healthy"})
    assert client.get("/api/payment/ping").status_code == 200


def test_chaos_switch_is_off_unless_enabled(client, monkeypatch):
    monkeypatch.delenv("CHAOS_ENABLED", raising=False)
    assert client.post("/api/payment/chaos", json={"mode": "failing"}).status_code == 403
