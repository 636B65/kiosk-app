from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from audit_service.models import AuditLog
from kiosk_common.auth import Principal, get_current_user
from kiosk_common.db import get_db
from kiosk_common.internal import require_internal
from kiosk_common.timeutil import parse_dt, utcnow

router = APIRouter(prefix="/api/audit", tags=["audit"])
internal = APIRouter(prefix="/internal/audit", tags=["internal"], dependencies=[Depends(require_internal)])


class AuditOut(BaseModel):
    id: int
    created_at: Optional[datetime] = None
    actor: str
    action: str
    entity: str = ""
    entity_id: str = ""
    details: str = ""

    model_config = ConfigDict(from_attributes=True)


class EventIn(BaseModel):
    created_at: Optional[str] = None
    actor: str = Field(max_length=200)
    action: str = Field(max_length=200)
    entity: str = ""
    entity_id: str = ""
    details: str = ""


class EventsIn(BaseModel):
    events: List[EventIn] = Field(max_length=1000)


@router.get("", response_model=List[AuditOut])
def list_audit(
    action: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: Principal = Depends(get_current_user),
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


@internal.post("/events", status_code=202)
def receive_events(data: EventsIn, db: Session = Depends(get_db)):
    for event in data.events:
        db.add(
            AuditLog(
                created_at=parse_dt(event.created_at) or utcnow(),
                actor=event.actor,
                action=event.action,
                entity=event.entity,
                entity_id=event.entity_id,
                details=event.details,
            )
        )
    db.commit()
    return {"accepted": len(data.events)}


@internal.get("/latest", response_model=Optional[AuditOut])
def latest(db: Session = Depends(get_db)):
    return db.query(AuditLog).order_by(AuditLog.id.desc()).first()
