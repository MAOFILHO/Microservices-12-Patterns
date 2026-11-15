"""order-service — owns orders/order items and its own database.

This service has no access to the user table at all.
To validate a caller's identity it makes a real HTTP call to user-service
(see order_api/api/UserClient.py) — this is the Anti-Corruption-Layer-style
boundary between the Order and User bounded contexts (pattern 2).
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
        db.create_all()

        # /health, /health/db, /debug/spans, /metrics, tracing and JSON logs (patterns 1 and 6).
        install_observability(app, "order", db)

        return app
