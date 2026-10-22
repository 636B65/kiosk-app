import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import models  # noqa: F401
from database import Base
from migrate_database import copy_database
from models import Category, Product


def test_database_copy_preserves_ids_and_requires_explicit_replace(tmp_path):
    source = create_engine(f"sqlite:///{tmp_path / 'source.db'}")
    target = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(source)

    with Session(source) as db:
        category = Category(id=17, name="Drinks", description="Cold")
        db.add(category)
        db.flush()
        db.add(
            Product(
                id=29,
                name="Water",
                price=1.5,
                stock=10,
                category_id=category.id,
            )
        )
        db.commit()

    assert copy_database(source, target) == 2
    with Session(target) as db:
        product = db.get(Product, 29)
        assert product is not None
        assert product.category_id == 17
        assert product.category.name == "Drinks"

    with pytest.raises(ValueError, match="already contains data"):
        copy_database(source, target)

    assert copy_database(source, target, replace_target=True) == 2
    with Session(target) as db:
        assert db.query(Product).count() == 1
        assert db.query(Category).count() == 1

    source.dispose()
    target.dispose()


def test_add_missing_columns_upgrades_existing_tables(tmp_path):
    from sqlalchemy import inspect, text

    from migrations import add_missing_columns

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR, "
                "price FLOAT, stock INTEGER)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER, "
                "product_name VARCHAR, quantity INTEGER, unit_price FLOAT)"
            )
        )
        conn.execute(text("INSERT INTO products VALUES (1, 'Old', 2.0, 3)"))

    add_missing_columns(engine)
    add_missing_columns(engine)  # idempotent

    inspector = inspect(engine)
    product_columns = {c["name"] for c in inspector.get_columns("products")}
    assert {
        "special_starts_on",
        "special_ends_on",
        "cost_price",
        "low_stock_threshold",
    } <= product_columns
    assert "unit_cost" in {c["name"] for c in inspector.get_columns("order_items")}
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT low_stock_threshold, cost_price FROM products WHERE id = 1")
        ).one()
    assert row == (5, None)
    engine.dispose()
