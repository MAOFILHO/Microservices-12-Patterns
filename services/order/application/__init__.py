"""order-service — owns orders/order items and its own database.

This service has no access to the user table at all. It learns who the caller is from the
signed login token (pattern 10), prices orders by asking the catalog, and charges through the
payment service behind a circuit breaker (pattern 4). See order_api/api/clients.py.
Checkout is a saga (pattern 8, saga.py) whose events leave through an outbox (pattern 7, outbox.py).
"""
import os

from flask import Flask
from shop_common.flask_support import install as install_observability
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name: str | None = None) -> Flask:
    from config import CONFIG_BY_NAME

    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(CONFIG_BY_NAME[config_name])

    db.init_app(app)
    migrate.init_app(app, db)

    with app.app_context():
        from . import models  # noqa: F401
        from .order_api import order_api_blueprint

        app.register_blueprint(order_api_blueprint)

        # db.create_all() runs regardless of RUN_MODE (migrations/ has no actual Alembic revisions, so gating
        # this to local-only left Azure MySQL with no schema at all).
        # Two order replicas share one database and start together (pattern 10).
        from shop_common.db_setup import create_tables

        create_tables(db)

        # /health, /health/db, /debug/spans, /metrics, tracing and JSON logs (patterns 1 and 6).
        install_observability(app, "order", db)

        # Pattern 7: publish outbox events to the bus in the background (no-op without REDIS_URL).
        from shop_common.flask_support import instance_id

        from .outbox import start as start_outbox_relay

        start_outbox_relay(app, instance_id("order"))

        # Demo 13: settle checkouts left pending by a slow payment.
        from .reconcile import start as start_reconciler

        start_reconciler(app)
        return app
