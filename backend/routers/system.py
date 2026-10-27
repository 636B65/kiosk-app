import json
import os
import platform

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import audit
import backups
from database import engine, get_db
from models import AuditLog, Customer, Order, Product, User
from security import get_current_user
from timeutil import utcnow

router = APIRouter(prefix="/api/system", tags=["system"])

STARTED_AT = utcnow()
# Written at image build time by scripts/release-info.sh (see backend/Dockerfile).
RELEASE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "release.json")


def release_info() -> dict:
    """Version and commit: APP_VERSION/GIT_COMMIT env first, then the build's file."""
    info = {"version": "", "commit": ""}
    try:
        with open(RELEASE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        info.update({k: str(data.get(k) or "") for k in info})
    except (OSError, ValueError):
        pass
    return {
        "version": os.environ.get("APP_VERSION") or info["version"] or "dev",
        "commit": os.environ.get("GIT_COMMIT") or info["commit"],
    }


def _database_size(path: str) -> int:
    # SQLite in WAL mode keeps recent writes in side files.
    return sum(
        os.path.getsize(p)
        for p in (path, path + "-wal", path + "-shm")
        if os.path.isfile(p)
    )


def _backup_info(db: Session) -> dict:
    items = backups.list_backups(engine)
    return {
        "supported": backups.supported(engine),
        "interval_hours": backups.interval_hours(db),
        "keep": backups.keep_count(db),
        "count": len(items),
        "total_bytes": sum(item["size_bytes"] for item in items),
        "last_backup_at": items[0]["created_at"] if items else None,
        "items": items,
    }


@router.get("/status")
def status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    now = utcnow()
    database = {"engine": engine.dialect.name, "size_bytes": None}
    if backups.supported(engine):
        path = os.path.abspath(engine.url.database or "")
        database["size_bytes"] = _database_size(path)
    last_audit = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    return {
        **release_info(),
        "python": platform.python_version(),
        "server_time": now,
        "started_at": STARTED_AT,
        "uptime_seconds": int((now - STARTED_AT).total_seconds()),
        "database": database,
        "counts": {
            "products": db.query(Product).count(),
            "active_products": db.query(Product).filter(Product.is_active).count(),
            "low_stock_products": sum(p.is_low_stock for p in db.query(Product).all()),
            "customers": db.query(Customer).count(),
            "orders": db.query(Order).count(),
            "pending_orders": db.query(Order).filter(Order.status == "pending").count(),
            "users": db.query(User).count(),
        },
        "last_activity": (
            {
                "at": last_audit.created_at,
                "actor": last_audit.actor,
                "action": last_audit.action,
            }
            if last_audit
            else None
        ),
        "backups": _backup_info(db),
    }


@router.get("/backups")
def list_backups(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _backup_info(db)


@router.post("/backups", status_code=201)
def create_backup(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not backups.supported(engine):
        raise HTTPException(
            status_code=400,
            detail="Backups need a SQLite database file",
        )
    result = backups.create_backup(engine, backups.keep_count(db))
    pruned = f"; pruned {len(result['pruned'])}" if result["pruned"] else ""
    audit.record(
        db, user.username, "backup.create", "backup", result["name"],
        f"{result['size_bytes']} bytes{pruned}",
    )
    db.commit()
    return result


@router.get("/backups/{name}")
def download_backup(
    name: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    path = backups.backup_path(engine, name)
    if not path:
        raise HTTPException(status_code=404, detail="Backup not found")
    audit.record(db, user.username, "backup.download", "backup", name)
    db.commit()
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=name)
