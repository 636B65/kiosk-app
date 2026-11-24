from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import audit
from database import get_db
from models import ExtraPayment, User
from schemas import ExtraPaymentOut
from security import get_current_user

router = APIRouter(prefix="/api/extra-payments", tags=["extra-payments"])


@router.get("", response_model=List[ExtraPaymentOut])
def list_extra_payments(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """What customers paid on top of their debt, newest first."""
    return (
        db.query(ExtraPayment)
        .order_by(ExtraPayment.created_at.desc(), ExtraPayment.id.desc())
        .limit(limit)
        .all()
    )


@router.delete("/{extra_id}", status_code=204)
def delete_extra_payment(
    extra_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove an entry made by mistake."""
    extra = db.get(ExtraPayment, extra_id)
    if not extra:
        raise HTTPException(status_code=404, detail="Extra payment not found")
    audit.record(
        db, user.username, "customer.extra_payment_delete", "customer", extra.username,
        f"extra payment #{extra.id} of {extra.amount:.2f} removed",
    )
    db.delete(extra)
    db.commit()
