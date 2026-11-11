import logging
import platform

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from kiosk_common.app import _release_info
from kiosk_common.auth import Principal, get_current_user
from kiosk_common.http import UpstreamError
from kiosk_common.timeutil import utcnow
from system_service import backups

router = APIRouter(prefix="/api/system", tags=["system"])
health = APIRouter(tags=["health"])

STARTED_AT = utcnow()
SERVICES = ("auth", "catalog", "customers", "orders", "settings", "audit", "reports")


def _clients(request: Request):
    return request.app.state.clients


def _settings(request: Request) -> dict:
    return _clients(request)["settings"].get("/api/settings") or {}


def _backup_info(request: Request, settings: dict) -> dict:
    config = request.app.state.config
    items = backups.list_backups(config.backup_path)
    return {
        "supported": backups.supported(config.databases),
        "interval_hours": backups.interval_hours(settings),
        "keep": backups.keep_count(settings),
        "count": len(items),
        "total_bytes": sum(item["size_bytes"] for item in items),
        "last_backup_at": items[0]["created_at"] if items else None,
        "items": items,
    }


def _safe(client, path: str, default):
    try:
        return client.get(path) or default
    except UpstreamError:
        return default


@health.get("/api/health")
def api_health(request: Request):
    """Aggregated health: ok when every service answers its readiness probe."""
    services = {}
    for name in SERVICES:
        client = _clients(request).get(name)
        if client is None:
            continue
        try:
            client.get("/readyz")
            services[name] = "ok"
        except UpstreamError:
            services[name] = "down"
    status = "ok" if all(v == "ok" for v in services.values()) else "degraded"
    return {"status": status, "services": services}


@router.get("/status")
def status(request: Request, _: Principal = Depends(get_current_user)):
    now = utcnow()
    clients = _clients(request)
    settings = _settings(request)
    catalog = _safe(clients["catalog"], "/internal/stats", {})
    customers = _safe(clients["customers"], "/internal/customers/stats", {})
    orders = _safe(clients["orders"], "/internal/orders/stats", {})
    users = _safe(clients["auth"], "/internal/auth/stats", {})
    last_audit = _safe(clients["audit"], "/internal/audit/latest", None)
    sizes = request.app.state.database_sizes()
    return {
        **_release_info(),
        "python": platform.python_version(),
        "server_time": now,
        "started_at": STARTED_AT,
        "uptime_seconds": int((now - STARTED_AT).total_seconds()),
        "database": {
            "engine": request.app.state.database_engine,
            "size_bytes": sum(v for v in sizes.values() if v is not None) if sizes else None,
            "databases": sizes,
        },
        "counts": {
            "products": catalog.get("products", 0),
            "active_products": catalog.get("active_products", 0),
            "low_stock_products": catalog.get("low_stock_products", 0),
            "customers": customers.get("customers", 0),
            "orders": orders.get("orders", 0),
            "pending_orders": orders.get("pending_orders", 0),
            "users": users.get("users", 0),
        },
        "last_activity": (
            {"at": last_audit["created_at"], "actor": last_audit["actor"], "action": last_audit["action"]}
            if last_audit else None
        ),
        "backups": _backup_info(request, settings),
    }


@router.get("/backups")
def list_backups(request: Request, _: Principal = Depends(get_current_user)):
    return _backup_info(request, _settings(request))


@router.post("/backups", status_code=201)
def create_backup(request: Request, user: Principal = Depends(get_current_user)):
    config = request.app.state.config
    if not backups.supported(config.databases):
        raise HTTPException(status_code=400, detail="Backups are not configured (BACKUP_DATABASE_URLS / pg_dump)")
    result = backups.create_backup(config.backup_path, config.databases, backups.keep_count(_settings(request)))
    pruned = f"; pruned {len(result['pruned'])}" if result["pruned"] else ""
    request.app.state.audit_direct(
        user.username, "backup.create", "backup", result["name"], f"{result['size_bytes']} bytes{pruned}"
    )
    return result


@router.get("/backups/{name}")
def download_backup(name: str, request: Request, user: Principal = Depends(get_current_user)):
    path = backups.backup_path(request.app.state.config.backup_path, name)
    if not path:
        raise HTTPException(status_code=404, detail="Backup not found")
    request.app.state.audit_direct(user.username, "backup.download", "backup", name)
    return FileResponse(path, media_type="application/gzip", filename=name)


def audit_direct(audit_client):
    """The system service has no database (and so no outbox): send audit entries directly."""

    def send(actor: str, action: str, entity: str = "", entity_id: object = "", details: str = "") -> None:
        try:
            audit_client.post(
                "/internal/audit/events",
                json={"events": [{
                    "created_at": utcnow().isoformat(), "actor": actor, "action": action,
                    "entity": entity, "entity_id": str(entity_id), "details": details,
                }]},
            )
        except UpstreamError:
            logging.getLogger(__name__).warning("audit entry %s for %s not delivered", action, entity_id)

    return send

