from contextlib import asynccontextmanager

from fastapi import FastAPI

from kiosk_common.app import create_base_app
from kiosk_common.auth import AuthVerifier, introspect_resolver
from kiosk_common.db import Database
from kiosk_common.http import ServiceClient
from system_service.backups import BackupScheduler
from system_service.config import Config
from system_service.routers import audit_direct, health, router


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    token, timeout = config.internal_token, config.upstream_timeout_seconds
    clients = {
        "auth": ServiceClient("auth service", config.auth_service_url, token, timeout),
        "audit": ServiceClient("audit service", config.audit_service_url, token, timeout),
        "catalog": ServiceClient("catalog service", config.catalog_service_url, token, timeout),
        "customers": ServiceClient("customer service", config.customer_service_url, token, timeout),
        "orders": ServiceClient("order service", config.order_service_url, token, timeout),
        "settings": ServiceClient("settings service", config.settings_service_url, token, timeout),
        "reports": ServiceClient("report service", config.report_service_url, token, timeout),
    }
    scheduler = BackupScheduler(config.backup_path, config.databases, clients["settings"])

    def database_sizes() -> dict[str, int | None]:
        sizes = {}
        for name, url in config.databases.items():
            database = Database(url)
            try:
                sizes[name] = database.size_bytes()
            finally:
                database.dispose()
        return sizes

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler.start()
        yield
        scheduler.stop()

    app = create_base_app(config, "Kiosk System Service", lifespan)
    app.state.auth = AuthVerifier(
        config.secret_key, config.algorithm, introspect_resolver(clients["auth"]), config.auth_cache_seconds
    )
    app.state.clients = clients
    app.state.scheduler = scheduler
    app.state.database_sizes = database_sizes
    app.state.database_engine = (
        "postgresql" if any(u.startswith("postgresql") for u in config.databases.values())
        else "sqlite" if config.databases else "none"
    )
    app.state.audit_direct = audit_direct(clients["audit"])
    app.include_router(health)
    app.include_router(router)
    return app
