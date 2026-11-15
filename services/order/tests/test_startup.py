"""Two order replicas start at the same moment and share one database (pattern 10)."""
import pytest
from sqlalchemy.exc import OperationalError


def test_replica_survives_another_replica_creating_the_tables_first(app, monkeypatch):
    from application import db
    from shop_common.db_setup import create_tables

    real_create_all = db.create_all
    calls = []

    def racing_create_all():
        calls.append(1)
        if len(calls) == 1:  # the other replica won the race between "check" and "create"
            raise OperationalError("CREATE TABLE saga_step", {}, Exception("table saga_step already exists"))
        real_create_all()

    monkeypatch.setattr(db, "create_all", racing_create_all)
    create_tables(db)
    assert len(calls) == 2


def test_other_database_errors_still_stop_startup(app, monkeypatch):
    from application import db
    from shop_common.db_setup import create_tables

    def broken():
        raise OperationalError("CREATE TABLE x", {}, Exception("disk I/O error"))

    monkeypatch.setattr(db, "create_all", broken)
    with pytest.raises(OperationalError):
        create_tables(db)


def _relay_threads():
    import threading

    return [t for t in threading.enumerate() if t.name == "outbox-relay"]


def test_reloader_watcher_process_does_not_publish_events(app, monkeypatch):
    """With app.run(debug=True), Flask runs a watcher process plus a worker process, and both build
    the app. Only the worker serves requests, so only it may publish, or the bus switch (which
    reaches the worker) would not stop publishing."""
    from application import outbox

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    app.debug = True
    before = len(_relay_threads())
    outbox.start(app, "order-test")
    assert len(_relay_threads()) == before


def test_worker_process_publishes_events(app, monkeypatch):
    from application import outbox

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    app.debug = True
    before = len(_relay_threads())
    outbox.start(app, "order-test")
    assert len(_relay_threads()) == before + 1
