from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from catalog_service.models import Outbox, Product, Restock, StockAdjustment
from catalog_service.schemas import RestockOut, StockAdjustmentOut, StockCountIn, StockCountResult
from kiosk_common import audit
from kiosk_common.auth import Principal, get_current_user
from kiosk_common.db import get_db

router = APIRouter(prefix="/api/inventory", tags=["inventory"])
restocks = APIRouter(prefix="/api/restocks", tags=["restocks"])


@restocks.get("", response_model=List[RestockOut])
def list_restocks(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Principal = Depends(get_current_user),
):
    """Most recent deliveries across all products."""
    return db.query(Restock).order_by(Restock.created_at.desc(), Restock.id.desc()).limit(limit).all()


@router.post("/counts", response_model=StockCountResult)
def record_counts(
    data: StockCountIn, db: Session = Depends(get_db), user: Principal = Depends(get_current_user)
):
    """Record a shelf count: set each product's stock to what was counted.

    Each line is compare-and-set against the stock the count sheet showed. A line
    whose stock moved since is returned as a conflict and left alone.
    """
    applied = []
    conflicts = []
    for item in data.items:
        product = db.get(Product, item.product_id)
        if product is None:
            conflicts.append({
                "product_id": item.product_id, "product_name": "(deleted)",
                "expected_stock": item.expected_stock, "current_stock": None,
            })
            continue
        claimed = (
            db.query(Product)
            .filter(Product.id == item.product_id, Product.stock == item.expected_stock)
            .update({"stock": item.counted}, synchronize_session=False)
        )
        if claimed != 1:
            db.refresh(product)
            conflicts.append({
                "product_id": product.id, "product_name": product.name,
                "expected_stock": item.expected_stock, "current_stock": product.stock,
            })
            continue
        difference = item.counted - item.expected_stock
        reason = item.reason or ("match" if difference == 0 else "shrinkage" if difference < 0 else "miscount")
        adjustment = StockAdjustment(
            product_id=product.id,
            product_name=product.name,
            expected=item.expected_stock,
            counted=item.counted,
            difference=difference,
            reason=reason,
            unit_cost=product.cost_price,
            note=item.note.strip(),
            created_by=user.username,
        )
        db.add(adjustment)
        audit.record(
            db, Outbox, user.username, "product.count", "product", product.id,
            f"{product.name}: counted {item.counted}, system {item.expected_stock} ({difference:+d}, {reason})",
        )
        applied.append(adjustment)
    db.commit()
    for adjustment in applied:
        db.refresh(adjustment)
    return {"applied": applied, "conflicts": conflicts}


@router.get("/adjustments", response_model=List[StockAdjustmentOut])
def list_adjustments(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: Principal = Depends(get_current_user),
):
    return (
        db.query(StockAdjustment)
        .order_by(StockAdjustment.created_at.desc(), StockAdjustment.id.desc())
        .limit(limit)
        .all()
    )
