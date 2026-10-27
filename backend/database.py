import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

database_file = settings.database_path
if database_file != ":memory:":
    os.makedirs(os.path.dirname(os.path.abspath(database_file)) or ".", exist_ok=True)

engine = create_engine(
    f"sqlite:///{database_file}",
    connect_args={"check_same_thread": False},
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
