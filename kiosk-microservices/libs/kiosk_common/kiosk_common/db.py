"""Database access: one engine per service, SQLite locally and Postgres in Kubernetes."""

import os
from contextlib import contextmanager
from typing import Iterator

from fastapi import Request
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Advisory lock key so replicas starting at the same time do not race create_all().
_SCHEMA_LOCK_KEY = 726_143


class Database:
    def __init__(self, url: str):
        self.url = url
        if url.startswith("sqlite"):
            path = url.removeprefix("sqlite:///")
            if path and path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
            self.engine = create_engine(
                url, connect_args={"check_same_thread": False}, pool_pre_ping=True
            )
        else:
            self.engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    @property
    def is_sqlite(self) -> bool:
        return self.dialect == "sqlite"

    def create_schema(self, metadata: MetaData) -> None:
        """Create missing tables; serialised across replicas on Postgres."""
        if self.dialect == "postgresql":
            with self.engine.begin() as conn:
                conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SCHEMA_LOCK_KEY})
                metadata.create_all(bind=conn)
        else:
            metadata.create_all(bind=self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def ping(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def size_bytes(self) -> int | None:
        try:
            if self.dialect == "postgresql":
                with self.engine.connect() as conn:
                    return int(conn.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0)
            if self.is_sqlite:
                path = self.engine.url.database or ""
                if path and path != ":memory:":
                    return sum(
                        os.path.getsize(p)
                        for p in (path, path + "-wal", path + "-shm")
                        if os.path.isfile(p)
                    )
        except Exception:
            return None
        return None

    def dispose(self) -> None:
        self.engine.dispose()


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency: a session from the app's ``Database`` (``app.state.database``)."""
    database: Database = request.app.state.database
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()
