from sqlalchemy import create_engine


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
