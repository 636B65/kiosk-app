"""Endpoints for the other services (never exposed through the gateway)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload

from catalog_service.models import Product, StockAdjustment
from catalog_service.schemas import ProductInternalOut, ReserveResult, StockAdjustmentOut, StockRequest
from kiosk_common.db import get_db
from kiosk_common.internal import require_internal
from kiosk_common.timeutil import parse_dt

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal)])


def _internal_out(product: Product) -> ProductInternalOut:
    out = ProductInternalOut.model_validate(product)
    return out.model_copy(
        update={
            "effective_price": product.effective_price,
            "is_low_stock": product.is_low_stock,
            "category_name": product.category.name if product.category else "",
        }
    )


@router.post("/stock/reserve", response_model=ReserveResult)
def reserve_stock(data: StockRequest, db: Session = Depends(get_db)):
    """Take stock for an order, all lines or none, and return the price snapshot.

    Each line is one SQL statement (``stock = stock - q WHERE stock >= q``) so
    simultaneous orders never overwrite each other; a line that cannot be
    fulfilled rolls back every line before it.
    """
    lines = []
    with db.begin():
        for item in data.items:
            product = db.get(Product, item.product_id)
            if not product or not product.is_active:
                raise HTTPException(status_code=400, detail=f"Product {item.product_id} not available")
            result = db.execute(
                text("UPDATE products SET stock = stock - :quantity WHERE id = :product_id AND stock >= :quantity"),
                {"product_id": product.id, "quantity": item.quantity},
            )
            if result.rowcount != 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for '{product.name}' ({product.stock} left)",
                )
            lines.append({
                "product_id": product.id,
                "product_name": product.name,
                "quantity": item.quantity,
                "unit_price": product.effective_price,
                "unit_cost": product.cost_price,
            })
    return {"items": lines}


@router.post("/stock/release")
def release_stock(data: StockRequest, db: Session = Depends(get_db)):
    """Give stock back (a cancelled order, or an order that failed after reserving)."""
    with db.begin():
        for item in data.items:
            db.execute(
                text("UPDATE products SET stock = stock + :quantity WHERE id = :product_id"),
                {"product_id": item.product_id, "quantity": item.quantity},
            )
    return {"released": len(data.items)}


@router.get("/products", response_model=List[ProductInternalOut])
def list_all_products(
    ids: Optional[str] = Query(default=None, description="comma-separated product ids"),
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Product).options(joinedload(Product.category))
    if ids:
        wanted = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        query = query.filter(Product.id.in_(wanted or [-1]))
    if active_only:
        query = query.filter(Product.is_active.is_(True))
    return [_internal_out(p) for p in query.order_by(Product.name, Product.id).all()]


@router.get("/adjustments", response_model=List[StockAdjustmentOut])
def list_adjustments(start: Optional[str] = None, end: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(StockAdjustment)
    if start:
        query = query.filter(StockAdjustment.created_at >= parse_dt(start))
    if end:
        query = query.filter(StockAdjustment.created_at < parse_dt(end))
    return query.order_by(StockAdjustment.id).all()


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    return {
        "products": db.query(Product).count(),
        "active_products": db.query(Product).filter(Product.is_active).count(),
        "low_stock_products": (
            db.query(Product)
            .filter(Product.is_active, Product.stock <= func.coalesce(Product.low_stock_threshold, 0))
            .count()
        ),
    }
