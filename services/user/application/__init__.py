"""user-service — owns User accounts, auth, and its own database.

An independently deployable process with its own schema (pattern 1, Database per Service).
"""
import os

from flask import Flask
from shop_common.flask_support import install as install_observability
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app(config_name: str | None = None) -> Flask:
    from config import CONFIG_BY_NAME

    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(CONFIG_BY_NAME[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    with app.app_context():
        from . import models  # noqa: F401
        from .user_api import user_api_blueprint

        app.register_blueprint(user_api_blueprint)

        # db.create_all() runs regardless of RUN_MODE (migrations/ has no actual Alembic revisions, so gating
        # this to local-only left Azure MySQL with no schema at all).
        db.create_all()

        # /health, /health/db, /debug/spans, /metrics, tracing and JSON logs (patterns 1 and 6).
        install_observability(app, "user", db)

        return app
