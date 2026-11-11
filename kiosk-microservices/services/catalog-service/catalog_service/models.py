import os

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

from kiosk_common.outbox import make_outbox_model
from kiosk_common.timeutil import utcnow

Base = declarative_base()


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, default="")
    sort_order = Column(Integer, default=0)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    price = Column(Float, nullable=False, default=0.0)
    special_price = Column(Float, nullable=True)
    is_weekly_special = Column(Boolean, default=False)
    # Optional schedule for the special (inclusive UTC dates); None = open-ended.
    special_starts_on = Column(Date, nullable=True)
    special_ends_on = Column(Date, nullable=True)
    # Latest purchase price per unit, snapshotted onto order lines for margins.
    cost_price = Column(Float, nullable=True)
    stock = Column(Integer, default=0)
    low_stock_threshold = Column(Integer, default=5)
    image_path = Column(String, default="")
    is_active = Column(Boolean, default=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    category = relationship("Category", back_populates="products")
    barcode_entries = relationship(
        "ProductBarcode",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductBarcode.code",
    )

    @property
    def barcodes(self):
        return [entry.code for entry in self.barcode_entries]

    @property
    def image_url(self):
        if self.image_path:
            return f"/api/images/{os.path.basename(self.image_path)}"
        return None

    @property
    def special_active(self):
        if not self.is_weekly_special or self.special_price is None:
            return False
        today = utcnow().date()
        if self.special_starts_on and today < self.special_starts_on:
            return False
        if self.special_ends_on and today > self.special_ends_on:
            return False
        return True

    @property
    def effective_price(self):
        return self.special_price if self.special_active else self.price

    @property
    def is_low_stock(self):
        return bool(self.is_active) and (self.stock or 0) <= (self.low_stock_threshold or 0)


class ProductBarcode(Base):
    __tablename__ = "product_barcodes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(128), unique=True, index=True, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    product = relationship("Product", back_populates="barcode_entries")


class Restock(Base):
    __tablename__ = "restocks"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_cost = Column(Float, nullable=True)
    stock_after = Column(Integer, nullable=False)
    note = Column(String, default="")
    created_by = Column(String, default="")
    created_at = Column(DateTime, default=utcnow, index=True)


class StockAdjustment(Base):
    """An inventory count: the shelf held `counted` where the system said `expected`."""

    __tablename__ = "stock_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    product_name = Column(String, nullable=False)
    expected = Column(Integer, nullable=False)
    counted = Column(Integer, nullable=False)
    difference = Column(Integer, nullable=False)
    reason = Column(String, nullable=False)
    unit_cost = Column(Float, nullable=True)
    note = Column(String, default="")
    created_by = Column(String, default="")
    created_at = Column(DateTime, default=utcnow, index=True)


Outbox = make_outbox_model(Base)
