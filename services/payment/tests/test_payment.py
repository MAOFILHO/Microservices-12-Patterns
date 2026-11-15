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
