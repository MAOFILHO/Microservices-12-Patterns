from . import db


class StockItem(db.Model):
    __tablename__ = "stock_item"

    # The catalog's product id. Not a foreign key: the product table lives in another service's
    # database, so referential integrity across services is a business rule, not a DB constraint.
    product_id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    on_hand = db.Column(db.Integer, nullable=False, default=0)
    reserved = db.Column(db.Integer, nullable=False, default=0)

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved

    def to_json(self):
        return {
            "product_id": self.product_id,
            "on_hand": self.on_hand,
            "reserved": self.reserved,
            "available": self.available,
        }
