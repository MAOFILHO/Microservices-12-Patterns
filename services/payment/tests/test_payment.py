def test_charge_records_an_approved_payment(client):
    r = client.post("/api/payment/charge", data={"order_id": 7, "amount_cents": 3798, "idempotency_key": "k7"})
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
    r = client.post("/api/payment/charge", json={"order_id": 3, "amount_cents": 500, "idempotency_key": "k3"})
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


def test_a_simulated_decline_is_a_normal_answer(client):
    r = client.post("/api/payment/charge", json={"order_id": 4, "amount_cents": 900, "simulate": "decline", "idempotency_key": "k4"})
    assert r.status_code == 200
    assert r.get_json()["result"]["status"] == "DECLINED"


# --- Demo 13: a slow payment mid-checkout. Idempotency key and void. ------------------------------

def _charge(client, key, **body):
    return client.post("/api/payment/charge", json={"order_id": 5, "amount_cents": 700, "idempotency_key": key, **body})


def test_a_retry_with_the_same_key_charges_once(client):
    first = _charge(client, "saga-1").get_json()["result"]
    again = _charge(client, "saga-1").get_json()["result"]
    assert again["id"] == first["id"]
    assert len(client.get("/api/payments").get_json()["results"]) == 1


def test_a_new_key_is_a_new_charge(client):
    _charge(client, "saga-1")
    _charge(client, "saga-2")
    assert len(client.get("/api/payments").get_json()["results"]) == 2


def test_a_charge_needs_an_idempotency_key(client):
    assert client.post("/api/payment/charge", json={"order_id": 5, "amount_cents": 700}).status_code == 400


def _void(client, key, order_id=5, amount_cents=700):
    return client.post(f"/api/payment/charges/{key}/void", json={"order_id": order_id, "amount_cents": amount_cents})


def _slow(client, monkeypatch, on_sleep):
    from application import routes

    monkeypatch.setattr(routes.time, "sleep", on_sleep)
    monkeypatch.setenv("CHAOS_ENABLED", "1")
    client.post("/api/payment/chaos", json={"mode": "slow"})


def test_a_reused_key_with_a_different_charge_is_refused(client):
    _charge(client, "saga-1")
    r = client.post("/api/payment/charge", json={"order_id": 5, "amount_cents": 999, "idempotency_key": "saga-1"})
    assert r.status_code == 409
    assert len(client.get("/api/payments").get_json()["results"]) == 1


def test_void_reports_a_charge_that_went_through_and_leaves_it(client):
    _charge(client, "saga-1")
    assert _void(client, "saga-1").get_json()["result"]["status"] == "APPROVED"


def test_a_voided_key_can_never_be_charged_later(client):
    assert _void(client, "saga-1").get_json()["result"]["status"] == "VOIDED"
    assert _charge(client, "saga-1").get_json()["result"]["status"] == "VOIDED"  # the late charge
    assert [p["status"] for p in client.get("/api/payments").get_json()["results"]] == ["VOIDED"]


def test_void_leaves_a_charge_in_flight_alone_until_it_is_too_old(client):
    from datetime import timedelta

    from application import db, routes
    from application.models import Payment

    db.session.add(Payment(order_id=5, amount_cents=700, status="PROCESSING", idempotency_key="saga-1"))
    db.session.commit()
    assert _void(client, "saga-1").get_json()["result"]["status"] == "PROCESSING"
    row = Payment.query.one()
    row.created_at = row.created_at - timedelta(seconds=routes.PROCESSING_LIMIT_SECONDS + 1)
    db.session.commit()
    assert _void(client, "saga-1").get_json()["result"]["status"] == "VOIDED"  # its process died


def test_a_charge_voided_while_it_ran_does_not_approve_when_it_finishes(client, monkeypatch):
    from application import routes

    _slow(client, monkeypatch, lambda s: _force_void("saga-1"))
    try:
        assert _charge(client, "saga-1").get_json()["result"]["status"] == "VOIDED"
    finally:
        routes.SWITCH.value = "healthy"


def _force_void(key):
    from application import db
    from application.models import Payment

    Payment.query.filter_by(idempotency_key=key).update({"status": "VOIDED"})
    db.session.commit()


def test_a_slow_retry_does_not_wait_again(client, monkeypatch):
    from application import routes

    sleeps = []
    _slow(client, monkeypatch, sleeps.append)
    try:
        _charge(client, "saga-1")
        _charge(client, "saga-1")
    finally:
        routes.SWITCH.value = "healthy"
    assert len(sleeps) == 1


def test_a_slow_charge_is_recorded_as_processing_before_the_slow_part(client, monkeypatch):
    from application import routes
    from application.models import Payment

    seen_while_slow = []
    monkeypatch.setattr(routes.time, "sleep", lambda s: seen_while_slow.append(Payment.query.one().status))
    monkeypatch.setenv("CHAOS_ENABLED", "1")
    client.post("/api/payment/chaos", json={"mode": "slow"})
    try:
        assert _charge(client, "saga-1").get_json()["result"]["status"] == "APPROVED"
    finally:
        routes.SWITCH.value = "healthy"
    assert seen_while_slow == ["PROCESSING"]  # a void during the slow part sees it in flight


def test_void_answers_while_charges_fail(client, monkeypatch):
    _charge(client, "saga-1")
    monkeypatch.setenv("CHAOS_ENABLED", "1")
    client.post("/api/payment/chaos", json={"mode": "failing"})
    try:
        assert _charge(client, "saga-2").status_code == 500
        assert _void(client, "saga-1").status_code == 200
    finally:
        client.post("/api/payment/chaos", json={"mode": "healthy"})


def test_a_database_from_before_demo_13_gains_the_key_column_at_startup(app):
    from sqlalchemy import inspect, text

    from application import create_app, db

    db.drop_all()
    db.session.execute(text("CREATE TABLE payment (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, "
                            "amount_cents INTEGER NOT NULL, status VARCHAR(20) NOT NULL, created_at DATETIME)"))
    db.session.commit()
    create_app("development")
    assert "idempotency_key" in {c["name"] for c in inspect(db.engine).get_columns("payment")}


def test_two_processes_upgrading_the_same_database_at_once_both_start(app, monkeypatch):
    """The other process added the column after this one looked: the upgrade must not crash."""
    import sqlalchemy

    from application import db
    from shop_common.db_setup import add_missing_columns

    real = sqlalchemy.inspect

    class Stale:
        def __init__(self, engine):
            self._real = real(engine)

        def has_table(self, name):
            return self._real.has_table(name)

        def get_columns(self, name):
            return [c for c in self._real.get_columns(name) if c["name"] != "idempotency_key"]

    monkeypatch.setattr(sqlalchemy, "inspect", Stale)
    add_missing_columns(db)  # sees the column as missing, but it is already there
