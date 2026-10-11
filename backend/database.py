import os

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

database_url = settings.database_url or f"sqlite:///{settings.database_path}"
url = make_url(database_url)
connect_args = {}
if url.get_backend_name() == "sqlite":
    connect_args["check_same_thread"] = False
    database_file = url.database
    if database_file and database_file != ":memory:":
        os.makedirs(os.path.dirname(database_file) or ".", exist_ok=True)

engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
