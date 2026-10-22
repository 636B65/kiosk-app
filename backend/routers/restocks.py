from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Restock
from schemas import RestockOut
from security import get_current_user

router = APIRouter(prefix="/api/restocks", tags=["restocks"])


@router.get("", response_model=List[RestockOut])
def list_restocks(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    """Most recent deliveries across all products."""
    return (
        db.query(Restock)
        .order_by(Restock.created_at.desc(), Restock.id.desc())
        .limit(limit)
        .all()
    )
