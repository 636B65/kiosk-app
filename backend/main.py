import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.responses import Response
from starlette.concurrency import iterate_in_threadpool

import models  # noqa: F401
from config import settings as app_settings
from database import Base, SessionLocal, engine
from migrations import migrate
from routers import auth, categories, customers, orders, products, reports, settings, users
from seed import seed

logger = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 30
CACHEABLE_PATHS = {"/api/products", "/api/categories", "/api/settings"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        migrate(engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    app.state.redis = (
        Redis.from_url(app_settings.redis_url, decode_responses=False)
        if app_settings.redis_url
        else None
    )
    yield
    if app.state.redis:
        await app.state.redis.aclose()


app = FastAPI(title="Kiosk API", lifespan=lifespan)


@app.middleware("http")
async def redis_cache(request, call_next):
    redis = getattr(request.app.state, "redis", None)
    cacheable = request.method == "GET" and request.url.path in CACHEABLE_PATHS
    cache_key = None
    version_key = "kiosk:api-cache:version"

    if redis and cacheable:
        try:
            version = await redis.get(version_key) or b"0"
            cache_key = (
                b"kiosk:api-cache:"
                + version
                + b":"
                + request.url.path.encode()
                + b":"
                + request.url.query.encode()
            )
            cached = await redis.get(cache_key)
            if cached:
                status, content_type, body = cached.split(b"\n", 2)
                return Response(
                    content=body,
                    status_code=int(status),
                    media_type=content_type.decode(),
                )
        except RedisError:
            logger.warning("Redis cache read failed; serving request without cache")
            cache_key = None

    response = await call_next(request)
    body = b"".join([chunk async for chunk in response.body_iterator])

    if redis and request.method not in ("GET", "HEAD", "OPTIONS") and response.status_code < 400:
        try:
            await redis.incr(version_key)
        except RedisError:
            logger.warning("Redis cache invalidation failed; cached data may expire by TTL")
    elif redis and cacheable and cache_key and response.status_code == 200:
        try:
            content_type = response.headers.get("content-type", "application/json")
            cached = f"{response.status_code}\n{content_type}\n".encode() + body
            await redis.set(cache_key, cached, ex=CACHE_TTL_SECONDS)
        except RedisError:
            logger.warning("Redis cache write failed; serving uncached response")

    response.body_iterator = iterate_in_threadpool(iter([body]))
    return response


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

_image_dir = os.path.join(
    os.path.dirname(os.path.abspath(app_settings.database_path)) or ".",
    "product_images",
)
os.makedirs(_image_dir, exist_ok=True)
app.mount("/api/images", StaticFiles(directory=_image_dir), name="product-images")


@app.get("/api/health")
def health():
    return {"status": "ok"}
