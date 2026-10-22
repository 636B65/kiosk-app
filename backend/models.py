import os

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base
from timeutil import utcnow


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)


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
    order_items = relationship("OrderItem", back_populates="product")
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


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    orders = relationship("Order", back_populates="customer")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="pending")  # pending, paid, cancelled
    subtotal = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    notes = Column(Text, default="")
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    @property
    def customer_username(self):
        return self.customer.username if self.customer else None


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, default=0.0)
    unit_cost = Column(Float, nullable=True)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(String, default="")


class Restock(Base):
    __tablename__ = "restocks"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_cost = Column(Float, nullable=True)
    stock_after = Column(Integer, nullable=False)
    note = Column(String, default="")
    created_by = Column(String, default="")
    created_at = Column(DateTime, default=utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False, index=True)
    entity = Column(String, default="")
    entity_id = Column(String, default="")
    details = Column(Text, default="")
