from contextlib import asynccontextmanager

from fastapi import FastAPI

from audit_service.config import Config
from audit_service.models import Base
from audit_service.routers import internal, router
from kiosk_common.app import create_base_app
from kiosk_common.auth import AuthVerifier, introspect_resolver
from kiosk_common.db import Database
from kiosk_common.http import ServiceClient


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    database = Database(config.database_url)
    clients = {
        "auth": ServiceClient("auth service", config.auth_service_url, config.internal_token, config.upstream_timeout_seconds),
    }

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_schema(Base.metadata)
        yield
        database.dispose()

    app = create_base_app(config, "Kiosk Audit Service", lifespan)
    app.state.database = database
    app.state.auth = AuthVerifier(
        config.secret_key, config.algorithm, introspect_resolver(clients["auth"]), config.auth_cache_seconds
    )
    app.state.clients = clients
    app.include_router(router)
    app.include_router(internal)
    return app
