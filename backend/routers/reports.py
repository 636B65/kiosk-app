from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Order, OrderItem, Product
from security import get_current_user
from timeutil import utcnow

router = APIRouter(prefix="/api/reports", tags=["reports"])


def revenue_for_period(db: Session, start: datetime = None, end: datetime = None):
    query = db.query(
        func.count(Order.id),
        func.coalesce(func.sum(Order.total), 0.0),
    ).filter(Order.status == "paid")
    if start:
        query = query.filter(Order.created_at >= start)
    if end:
        query = query.filter(Order.created_at < end)
    count, total = query.first()
    return {"order_count": count, "revenue": round(total or 0.0, 2)}


def outstanding_total(db: Session) -> float:
    total = (
        db.query(func.coalesce(func.sum(Order.total), 0.0))
        .filter(Order.status == "pending")
        .scalar()
    )
    return round(total or 0.0, 2)


@router.get("/summary")
def summary(_: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    now = utcnow()
    return {
        "today": revenue_for_period(db, start=now.replace(hour=0, minute=0, second=0)),
        "yesterday": revenue_for_period(
            db,
            start=(now - timedelta(days=1)).replace(hour=0, minute=0, second=0),
            end=now.replace(hour=0, minute=0, second=0),
        ),
        "week": revenue_for_period(db, start=now - timedelta(days=7)),
        "month": revenue_for_period(db, start=now - timedelta(days=30)),
        "all_time": revenue_for_period(db),
        "outstanding": outstanding_total(db),
        "pending_orders": db.query(Order).filter(Order.status == "pending").count(),
        "low_stock_products": (
            db.query(Product)
            .filter(Product.is_active, Product.stock <= 5)
            .all()
        ),
    }


@router.get("/top-products")
def top_products(
    limit: int = 10,
    _: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("total_qty"),
            func.sum(OrderItem.unit_price * OrderItem.quantity).label("total_rev"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status == "paid")
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "product": r.product_name,
            "quantity": r.total_qty,
            "revenue": round(r.total_rev or 0.0, 2),
        }
        for r in rows
    ]


@router.get("/sales-by-day")
def sales_by_day(
    days: int = 14,
    _: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start = utcnow() - timedelta(days=days)
    rows = (
        db.query(
            func.date(Order.created_at).label("day"),
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), 0.0),
        )
        .filter(Order.status == "paid", Order.created_at >= start)
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
        .all()
    )
    return [
        {"day": r.day, "orders": r[1], "revenue": round(r[2], 2)} for r in rows
    ]
