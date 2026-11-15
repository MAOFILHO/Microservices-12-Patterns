"""payment service — owns payment records and its own database.

Bounded context (pattern 2): Payment knows an order only by its id and an amount in cents. It
never sees products, carts or users. M3 makes it the step of the checkout saga that can fail.
"""
import os

from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from shop_common.flask_support import install as install_observability

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
        from .routes import payment_api

        app.register_blueprint(payment_api)
        db.create_all()
        install_observability(app, "payment", db)
        return app
