from contextlib import asynccontextmanager

from fastapi import FastAPI

from auth_service.config import Config
from auth_service.models import Base, Outbox
from auth_service.routers import auth, internal, users
from auth_service.routers.internal import resolve_user
from auth_service.seed import seed
from kiosk_common.app import create_base_app
from kiosk_common.audit import audit_sink
from kiosk_common.auth import AuthVerifier, Principal
from kiosk_common.db import Database
from kiosk_common.http import ServiceClient
from kiosk_common.outbox import OutboxRelay


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    database = Database(config.database_url)
    audit_client = ServiceClient(
        "audit service", config.audit_service_url, config.internal_token, config.upstream_timeout_seconds
    )
    relay = OutboxRelay(database, Outbox, {"audit": audit_sink(audit_client)}, config.outbox_interval_seconds)

    def resolver(token: str, payload: dict) -> Principal | None:
        with database.session() as db:
            user = resolve_user(db, payload)
            if user is None:
                return None
            return Principal(username=user.username, user_id=user.id, full_name=user.full_name or "")

    # The auth service checks its own user table on every call (no cache).
    verifier = AuthVerifier(config.secret_key, config.algorithm, resolver, cache_seconds=0)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_schema(Base.metadata)
        with database.session() as db:
            seed(db, config.admin_password)
        relay.start()
        yield
        relay.stop()
        database.dispose()

    app = create_base_app(config, "Kiosk Auth Service", lifespan)
    app.state.database = database
    app.state.auth = verifier
    app.state.clients = {"audit": audit_client}
    app.state.relay = relay
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(internal.router)
    return app
