"""inventory service — owns stock levels and its own database.

Bounded context (pattern 2): Inventory does not know a product's name or price. It knows a
StockItem keyed by the catalog's product_id, with how many are on hand and how many are reserved.
Catalog owns "what we sell"; Inventory owns "how many we have".
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
        from .seed import seed_stock_if_empty

        seed_stock_if_empty()
        install_observability(app, "inventory", db)
        return app
