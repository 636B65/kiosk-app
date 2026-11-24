from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import audit
from database import get_db
from models import Purchase, User
from schemas import PurchaseIn, PurchaseOut, PurchaseUpdate
from security import get_current_user
from timeutil import utcnow

router = APIRouter(prefix="/api/purchases", tags=["purchases"])


def _check_date(day) -> None:
    # A batch can be entered long after it was bought, never before it exists.
    # One day of slack covers a clock that is ahead of UTC.
    if day is not None and day > (utcnow() + timedelta(days=1)).date():
        raise HTTPException(status_code=422, detail="The purchase date cannot be in the future")


def _describe(p: Purchase) -> str:
    who = f" from {p.supplier}" if p.supplier else ""
    return f"{p.amount:.2f} on {p.purchased_on.isoformat()}{who}"


@router.get("", response_model=List[PurchaseOut])
def list_purchases(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Newest purchase date first."""
    return (
        db.query(Purchase)
        .order_by(Purchase.purchased_on.desc(), Purchase.id.desc())
        .limit(limit)
        .all()
    )


@router.post("", response_model=PurchaseOut, status_code=201)
def create_purchase(
    data: PurchaseIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_date(data.purchased_on)
    purchase = Purchase(
        purchased_on=data.purchased_on or utcnow().date(),
        amount=round(data.amount, 2),
        supplier=data.supplier.strip(),
        note=data.note.strip(),
        created_by=user.username,
    )
    db.add(purchase)
    db.flush()
    audit.record(db, user.username, "purchase.create", "purchase", purchase.id, _describe(purchase))
    db.commit()
    db.refresh(purchase)
    return purchase


@router.put("/{purchase_id}", response_model=PurchaseOut)
def update_purchase(
    purchase_id: int,
    data: PurchaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    purchase = db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    values = data.model_dump(exclude_unset=True)
    _check_date(values.get("purchased_on"))
    before = {
        "amount": purchase.amount,
        "date": purchase.purchased_on,
        "supplier": purchase.supplier,
        "note": purchase.note,
    }
    if values.get("amount") is not None:
        purchase.amount = round(values["amount"], 2)
    if values.get("purchased_on") is not None:
        purchase.purchased_on = values["purchased_on"]
    if values.get("supplier") is not None:
        purchase.supplier = values["supplier"].strip()
    if values.get("note") is not None:
        purchase.note = values["note"].strip()
    after = {
        "amount": purchase.amount,
        "date": purchase.purchased_on,
        "supplier": purchase.supplier,
        "note": purchase.note,
    }
    changes = audit.describe_changes(before, after)
    if changes:
        audit.record(db, user.username, "purchase.update", "purchase", purchase.id, changes)
    db.commit()
    db.refresh(purchase)
    return purchase


@router.delete("/{purchase_id}", status_code=204)
def delete_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    purchase = db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    audit.record(db, user.username, "purchase.delete", "purchase", purchase.id, _describe(purchase))
    db.delete(purchase)
    db.commit()
