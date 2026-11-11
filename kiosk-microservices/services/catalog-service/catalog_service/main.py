import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from catalog_service.config import Config
from catalog_service.models import Base, Outbox
from catalog_service.routers import categories, internal, inventory, products
from catalog_service.seed import seed
from kiosk_common.app import create_base_app
from kiosk_common.audit import audit_sink
from kiosk_common.auth import AuthVerifier, introspect_resolver
from kiosk_common.db import Database
from kiosk_common.http import ServiceClient
from kiosk_common.outbox import OutboxRelay


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    database = Database(config.database_url)
    clients = {
        "auth": ServiceClient("auth service", config.auth_service_url, config.internal_token, config.upstream_timeout_seconds),
        "audit": ServiceClient("audit service", config.audit_service_url, config.internal_token, config.upstream_timeout_seconds),
    }
    relay = OutboxRelay(database, Outbox, {"audit": audit_sink(clients["audit"])}, config.outbox_interval_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_schema(Base.metadata)
        if config.seed_demo_data:
            with database.session() as db:
                seed(db)
        relay.start()
        yield
        relay.stop()
        database.dispose()

    app = create_base_app(config, "Kiosk Catalog Service", lifespan)
    app.state.database = database
    app.state.auth = AuthVerifier(
        config.secret_key, config.algorithm, introspect_resolver(clients["auth"]), config.auth_cache_seconds
    )
    app.state.clients = clients
    app.state.relay = relay
    app.include_router(categories.router)
    app.include_router(products.router)
    app.include_router(inventory.router)
    app.include_router(inventory.restocks)
    app.include_router(internal.router)
    os.makedirs(config.images_path, exist_ok=True)
    app.mount("/api/images", StaticFiles(directory=config.images_path), name="product-images")
    return app
