from contextlib import asynccontextmanager

from fastapi import FastAPI

from kiosk_common.app import create_base_app
from kiosk_common.audit import audit_sink
from kiosk_common.auth import AuthVerifier, introspect_resolver
from kiosk_common.db import Database
from kiosk_common.http import ServiceClient
from kiosk_common.outbox import OutboxRelay
from settings_service.config import Config
from settings_service.models import DEFAULTS, Base, Outbox, Setting
from settings_service.routers import router


def seed(database: Database) -> None:
    with database.session() as db:
        for key, value in DEFAULTS.items():
            if not db.get(Setting, key):
                db.add(Setting(key=key, value=value))
        db.commit()


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
        seed(database)
        relay.start()
        yield
        relay.stop()
        database.dispose()

    app = create_base_app(config, "Kiosk Settings Service", lifespan)
    app.state.database = database
    app.state.auth = AuthVerifier(
        config.secret_key, config.algorithm, introspect_resolver(clients["auth"]), config.auth_cache_seconds
    )
    app.state.clients = clients
    app.state.relay = relay
    app.include_router(router)
    return app
