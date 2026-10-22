"""Copy kiosk data between SQLite and PostgreSQL before switching deployment modes."""

import argparse
import logging

from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import Engine, make_url

import models  # noqa: F401
from database import Base
from migrations import add_missing_columns, migrate

logger = logging.getLogger("migrate_database")


def _has_data(engine: Engine) -> bool:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in tables:
                continue
            reflected = Table(table.name, MetaData(), autoload_with=engine)
            if connection.execute(select(1).select_from(reflected).limit(1)).first():
                return True
    return False


def copy_database(source: Engine, target: Engine, replace_target: bool = False) -> int:
    """Copy all modeled rows, preserving primary keys and refusing accidental overwrite."""
    if source.url == target.url:
        raise ValueError("Source and target databases must be different")

    Base.metadata.create_all(target)
    if source.dialect.name == "sqlite":
        Base.metadata.create_all(source)
        migrate(source)
    if target.dialect.name == "sqlite":
        migrate(target)
    else:
        add_missing_columns(target)

    if _has_data(target) and not replace_target:
        raise ValueError(
            "Target database already contains data. Back it up, then pass "
            "--replace-target to explicitly replace it."
        )

    copied = 0
    with target.begin() as target_connection:
        if replace_target:
            for table in reversed(Base.metadata.sorted_tables):
                target_connection.execute(table.delete())

        source_inspector = inspect(source)
        source_tables = source_inspector.get_table_names()
        with source.connect() as source_connection:
            for table in Base.metadata.sorted_tables:
                if table.name not in source_tables:
                    continue
                source_table = Table(table.name, MetaData(), autoload_with=source)
                available_columns = {column.name for column in source_table.columns}
                columns = [
                    column.name
                    for column in table.columns
                    if column.name in available_columns
                ]
                rows = source_connection.execute(
                    select(*(source_table.c[name] for name in columns))
                ).mappings()
                batch = []
                for row in rows:
                    batch.append({name: row[name] for name in columns})
                    if len(batch) == 500:
                        target_connection.execute(table.insert().values(batch))
                        copied += len(batch)
                        batch.clear()
                if batch:
                    target_connection.execute(table.insert().values(batch))
                    copied += len(batch)

        if target.dialect.name == "postgresql":
            for table in Base.metadata.sorted_tables:
                primary_key = list(table.primary_key.columns)
                if len(primary_key) == 1 and primary_key[0].name == "id":
                    target_connection.execute(
                        text(
                            "SELECT setval(pg_get_serial_sequence(:table_name, "
                            ":column_name), GREATEST(COALESCE(MAX(id), 1), 1), "
                            "COUNT(*) > 0) FROM "
                            f'"{table.name}"'
                        ),
                        {"table_name": table.name, "column_name": "id"},
                    )
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="SQLAlchemy database URL")
    parser.add_argument("--target", required=True, help="SQLAlchemy database URL")
    parser.add_argument(
        "--replace-target",
        action="store_true",
        help="Delete existing target rows before copying (make a backup first)",
    )
    args = parser.parse_args()

    source_url = make_url(args.source)
    target_url = make_url(args.target)
    source = create_engine(args.source, pool_pre_ping=True)
    target = create_engine(args.target, pool_pre_ping=True)
    try:
        copied = copy_database(source, target, args.replace_target)
        logger.info("Copied %d rows from %s to %s", copied, source_url, target_url)
    finally:
        source.dispose()
        target.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
