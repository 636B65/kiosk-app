from contextlib import asynccontextmanager

from fastapi import FastAPI

from customer_service.config import Config
from customer_service.models import Base, Outbox
from customer_service.pins import PinHasher
from customer_service.routers import internal, router
from kiosk_common.app import create_base_app
from kiosk_common.audit import audit_sink
from kiosk_common.auth import AuthVerifier, introspect_resolver
from kiosk_common.db import Database
from kiosk_common.http import ServiceClient
from kiosk_common.outbox import OutboxRelay


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    database = Database(config.database_url)
    token, timeout = config.internal_token, config.upstream_timeout_seconds
    clients = {
        "auth": ServiceClient("auth service", config.auth_service_url, token, timeout),
        "audit": ServiceClient("audit service", config.audit_service_url, token, timeout),
        "orders": ServiceClient("order service", config.order_service_url, token, timeout),
        "settings": ServiceClient("settings service", config.settings_service_url, token, timeout),
    }
    relay = OutboxRelay(database, Outbox, {"audit": audit_sink(clients["audit"])}, config.outbox_interval_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_schema(Base.metadata)
        relay.start()
        yield
        relay.stop()
        database.dispose()

    app = create_base_app(config, "Kiosk Customer Service", lifespan)
    app.state.database = database
    app.state.auth = AuthVerifier(
        config.secret_key, config.algorithm, introspect_resolver(clients["auth"]), config.auth_cache_seconds
    )
    app.state.clients = clients
    app.state.relay = relay
    app.state.pins = PinHasher(config.pin_pepper, config.data_dir)
    app.include_router(router)
    app.include_router(internal)
    return app
