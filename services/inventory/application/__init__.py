"""inventory service — owns stock levels and its own database.

Bounded context (pattern 2): Inventory does not know a product's name or price. It knows a
StockItem keyed by the catalog's product_id, with how many are on hand and how many are reserved.
Catalog owns "what we sell"; Inventory owns "how many we have".

M3: holds stock for the checkout saga (pattern 8) and finishes the sale when an OrderConfirmed
event arrives from the bus (pattern 7).
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
        from .routes import inventory_api

        app.register_blueprint(inventory_api)
        db.create_all()
        from shop_common.db_setup import add_missing_columns

        add_missing_columns(db)  # demo 14: reservation.releases_received
        from .seed import seed_missing_stock

        seed_missing_stock()
        install_observability(app, "inventory", db)

        # Pattern 7: act on OrderConfirmed events from the bus (no-op without REDIS_URL).
        from shop_common.flask_support import instance_id

        from .consumer import start as start_consumer

        start_consumer(app, instance_id("inventory"))
        return app
