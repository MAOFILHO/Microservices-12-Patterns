from flask import Blueprint, jsonify, make_response

from . import db
from .models import StockItem

inventory_api = Blueprint("inventory_api", __name__)


@inventory_api.get("/api/inventory")
def list_stock():
    return jsonify({"results": [s.to_json() for s in StockItem.query.order_by(StockItem.product_id)]})


@inventory_api.get("/api/inventory/<int:product_id>")
def get_stock(product_id: int):
    item = db.session.get(StockItem, product_id)
    if item is None:
        return make_response(jsonify({"message": f"No stock record for product {product_id}"}), 404)
    return jsonify({"result": item.to_json()})
