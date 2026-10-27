import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import models  # noqa: F401
from config import settings as app_settings
from backups import BackupScheduler
from database import Base, SessionLocal, engine
from migrations import migrate
from routers import (
    audit as audit_routes,
    auth,
    categories,
    customers,
    orders,
    products,
    reports,
    restocks,
    settings,
    system,
    users,
)
from seed import seed

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate(engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    scheduler = BackupScheduler(engine, SessionLocal)
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="Kiosk API", lifespan=lifespan)


_cors_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins
    or [
        "https://localhost",
        "http://localhost",
        "https://127.0.0.1",
        "http://127.0.0.1",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(customers.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(reports.router)
app.include_router(settings.router)
app.include_router(users.router)
app.include_router(restocks.router)
app.include_router(audit_routes.router)
app.include_router(system.router)

_image_dir = os.path.join(
    os.path.dirname(os.path.abspath(app_settings.database_path)) or ".",
    "product_images",
)
os.makedirs(_image_dir, exist_ok=True)
app.mount("/api/images", StaticFiles(directory=_image_dir), name="product-images")


@app.get("/api/health")
def health():
    return {"status": "ok"}
