"""Run every service in one process, wired together exactly as in the cluster.

Each service gets its own SQLite database and talks to the others through
``InProcessTransport`` instead of the network. ``gateway`` routes ``/api/*`` to
the right service the way the nginx gateway does, so the tests read like calls
against the single API the frontend sees.
"""

import contextlib
import json
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from audit_service.config import Config as AuditConfig
from audit_service.main import create_app as audit_app
from auth_service.config import Config as AuthConfig
from auth_service.main import create_app as auth_app
from catalog_service.config import Config as CatalogConfig
from catalog_service.main import create_app as catalog_app
from customer_service.config import Config as CustomerConfig
from customer_service.main import create_app as customer_app
from kiosk_common.testing import wire
from order_service.config import Config as OrderConfig
from order_service.main import create_app as order_app
from report_service.config import Config as ReportConfig
from report_service.main import create_app as report_app
from settings_service.config import Config as SettingsConfig
from settings_service.main import create_app as settings_app
from system_service.config import Config as SystemConfig
from system_service.main import create_app as system_app

SECRET_KEY = "integration-test-secret-key-that-is-long-enough-0001"
INTERNAL_TOKEN = "integration-test-internal-token-that-is-long-enough"
PIN_PEPPER = "integration-test-pin-pepper-with-at-least-32-chars"
ADMIN_PASSWORD = "test-admin-password"

# Same table as the nginx gateway (frontend/nginx/default.conf.template).
ROUTES = [
    ("/api/health", "system"),
    ("/api/auth", "auth"),
    ("/api/users", "auth"),
    ("/api/categories", "catalog"),
    ("/api/products", "catalog"),
    ("/api/restocks", "catalog"),
    ("/api/inventory", "catalog"),
    ("/api/images", "catalog"),
    ("/api/customers", "customers"),
    ("/api/orders", "orders"),
    ("/api/settings", "settings"),
    ("/api/audit", "audit"),
    ("/api/reports", "reports"),
    ("/api/system", "system"),
]


class Gateway:
    """ASGI app that forwards each request to the service owning its path prefix."""

    def __init__(self, apps: dict):
        self.apps = apps

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                await send({"type": message["type"] + ".complete"})
                if message["type"] == "lifespan.shutdown":
                    return
        path = scope.get("path", "")
        for prefix, name in ROUTES:
            if path == prefix or path.startswith(prefix + "/"):
                await self.apps[name](scope, receive, send)
                return
        body = json.dumps({"detail": "Not Found"}).encode()
        await send({"type": "http.response.start", "status": 404,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})


@dataclass
class Stack:
    apps: dict
    client: TestClient
    data_dir: str

    def flush_outboxes(self) -> int:
        """Deliver queued audit events / stock releases (the relay threads do this in production)."""
        delivered = 0
        for app in self.apps.values():
            relay = getattr(app.state, "relay", None)
            if relay is not None:
                delivered += relay.flush()
        return delivered

    def service(self, name: str) -> TestClient:
        return TestClient(self.apps[name])


@pytest.fixture(scope="session")
def stack(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("stack")
    common = dict(
        secret_key=SECRET_KEY,
        internal_token=INTERNAL_TOKEN,
        auth_cache_seconds=0,
        outbox_interval_seconds=3600,
        data_dir=str(data_dir),
        trusted_proxies=1,
    )

    def url(name: str) -> str:
        return f"sqlite:///{data_dir}/{name}.db"

    apps = {
        "auth": auth_app(AuthConfig(database_url=url("auth"), admin_password=ADMIN_PASSWORD, **common)),
        "catalog": catalog_app(CatalogConfig(database_url=url("catalog"), **common)),
        "customers": customer_app(CustomerConfig(database_url=url("customers"), pin_pepper=PIN_PEPPER, **common)),
        "orders": order_app(OrderConfig(database_url=url("orders"), **common)),
        "settings": settings_app(SettingsConfig(database_url=url("settings"), **common)),
        "audit": audit_app(AuditConfig(database_url=url("audit"), **common)),
        "reports": report_app(ReportConfig(**common)),
        "system": system_app(SystemConfig(
            backup_database_urls=",".join(f"{n}={url(n)}" for n in ("auth", "catalog", "customers", "orders", "settings", "audit")),
            **common,
        )),
    }
    for app in apps.values():
        wire(app, apps)

    with contextlib.ExitStack() as lifespans:
        for app in apps.values():
            lifespans.enter_context(TestClient(app))
        yield Stack(apps=apps, client=TestClient(Gateway(apps)), data_dir=str(data_dir))


@pytest.fixture(scope="session")
def client(stack):
    return stack.client


@pytest.fixture(scope="session")
def admin_token(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def internal_headers():
    return {"X-Internal-Token": INTERNAL_TOKEN}
