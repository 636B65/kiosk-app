from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import AuditLog
from schemas import AuditOut
from security import get_current_user

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=List[AuditOut])
def list_audit(
    action: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    """Newest first. `action` filters by prefix, e.g. "order." or "product.restock"."""
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action.like(f"{action}%"))
    return (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
