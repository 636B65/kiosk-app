from fastapi import FastAPI

from kiosk_common.app import create_base_app
from kiosk_common.auth import AuthVerifier, introspect_resolver
from kiosk_common.http import ServiceClient
from report_service.config import Config
from report_service.routers import router


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    token, timeout = config.internal_token, config.upstream_timeout_seconds
    clients = {
        "auth": ServiceClient("auth service", config.auth_service_url, token, timeout),
        "orders": ServiceClient("order service", config.order_service_url, token, timeout),
        "catalog": ServiceClient("catalog service", config.catalog_service_url, token, timeout),
        "customers": ServiceClient("customer service", config.customer_service_url, token, timeout),
        "settings": ServiceClient("settings service", config.settings_service_url, token, timeout),
    }
    app = create_base_app(config, "Kiosk Report Service")
    app.state.auth = AuthVerifier(
        config.secret_key, config.algorithm, introspect_resolver(clients["auth"]), config.auth_cache_seconds
    )
    app.state.clients = clients
    app.include_router(router)
    return app
