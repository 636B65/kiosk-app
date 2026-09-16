from sqlalchemy import text
from sqlalchemy.engine import Engine

from due_dates import DUE_DATE_SETTING, compute_due_time, parse_due_date


def _drop_column(conn, table: str, column: str):
    """Drop a column using a table rebuild (works on all SQLite versions).

    Preserves the integer primary key so ORM autoincrement keeps working.
    """
    info = [
        (row[1], row[2], row[5])
        for row in conn.execute(text(f"PRAGMA table_info({table})"))
    ]
    if column not in {c for c, _, _ in info}:
        return
    parts = []
    for name, typ, is_pk in info:
        if name == column:
            continue
        if is_pk:
            parts.append(f'"{name}" INTEGER PRIMARY KEY AUTOINCREMENT')
        elif typ:
            parts.append(f'"{name}" {typ}')
        else:
            parts.append(f'"{name}"')
    cols_sql = ", ".join(name for name, _, _ in info if name != column)
    conn.execute(text(f"ALTER TABLE {table} RENAME TO {table}__old"))
    conn.execute(text(f"CREATE TABLE {table} ({', '.join(parts)})"))
    conn.execute(
        text(
            f"INSERT INTO {table} ({cols_sql}) "
            f"SELECT {cols_sql} FROM {table}__old"
        )
    )
    conn.execute(text(f"DROP TABLE {table}__old"))


def migrate(engine: Engine) -> None:
    """Bring databases created by an earlier version of the app up to date."""
    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }

        if "products" in tables:
            cols = [
                row[1]
                for row in conn.execute(text("PRAGMA table_info(products)"))
            ]
            # Backfill string columns that older rows left NULL (Python-side
            # defaults only apply to new ORM inserts, not existing rows).
            for col in ("description", "name"):
                if col in cols:
                    conn.execute(
                        text(
                            f"UPDATE products SET {col}='' WHERE "
                            f"{col} IS NULL"
                        )
                    )
            # Drop the image URL column, screens no longer use it.
            _drop_column(conn, "products", "image_url")

            # Product uploads are stored as files; keep a reference path.
            if "image_path" not in cols:
                conn.execute(
                    text("ALTER TABLE products ADD COLUMN image_path VARCHAR DEFAULT ''")
                )

            # Weekly specials: flag + optional lower special price.
            if "is_weekly_special" not in cols:
                conn.execute(
                    text("ALTER TABLE products ADD COLUMN is_weekly_special BOOLEAN DEFAULT 0")
                )
            if "special_price" not in cols:
                conn.execute(
                    text("ALTER TABLE products ADD COLUMN special_price FLOAT")
                )

        if "orders" in tables:
            columns = [row[1] for row in conn.execute(text("PRAGMA table_info(orders)"))]

            if "customer_id" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE orders "
                        "ADD COLUMN customer_id INTEGER REFERENCES customers(id)"
                    )
                )

            if "due_date" not in columns:
                conn.execute(text("ALTER TABLE orders ADD COLUMN due_date DATETIME"))

            # Backfill due dates for orders created before the column existed:
            # apply the configured payment due date if any, otherwise leave
            # NULL (no end date is the default).
            due_row = conn.execute(
                text(f"SELECT value FROM settings WHERE key = '{DUE_DATE_SETTING}'")
            ).first()
            due = compute_due_time(parse_due_date(due_row[0] if due_row else None))
            if due is not None:
                stale = conn.execute(
                    text("SELECT id FROM orders WHERE due_date IS NULL")
                ).fetchall()
                for (order_id,) in stale:
                    conn.execute(
                        text("UPDATE orders SET due_date = :due WHERE id = :oid"),
                        {"due": due.isoformat(), "oid": order_id},
                    )

            # Old statuses: 'completed' meant the order was paid.
            conn.execute(text("UPDATE orders SET status='paid' WHERE status='completed'"))
