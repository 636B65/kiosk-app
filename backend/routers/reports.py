from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from due_dates import get_due_date
from models import Customer, Order, OrderItem, Product
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


def top_customers_for_period(
    db: Session, start: datetime, limit: int
) -> list[dict]:
    rows = (
        db.query(
            Customer.username,
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total), 0.0).label("spent"),
        )
        .join(Order, Order.customer_id == Customer.id)
        .filter(Order.status == "paid", Order.created_at >= start)
        .group_by(Customer.id, Customer.username)
        .order_by(
            func.sum(Order.total).desc(),
            func.count(Order.id).desc(),
            Customer.username.asc(),
        )
        .limit(limit)
        .all()
    )
    return [
        {
            "username": row.username,
            "orders": row.orders,
            "spent": round(row.spent or 0.0, 2),
        }
        for row in rows
    ]


def top_products_for_period(
    db: Session, start: datetime, limit: int
) -> list[dict]:
    rows = (
        db.query(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("quantity"),
            func.coalesce(
                func.sum(OrderItem.unit_price * OrderItem.quantity), 0.0
            ).label("revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status == "paid", Order.created_at >= start)
        .group_by(OrderItem.product_name)
        .order_by(
            func.sum(OrderItem.quantity).desc(),
            func.sum(OrderItem.unit_price * OrderItem.quantity).desc(),
            OrderItem.product_name.asc(),
        )
        .limit(limit)
        .all()
    )
    return [
        {
            "product": row.product_name,
            "quantity": row.quantity,
            "revenue": round(row.revenue or 0.0, 2),
        }
        for row in rows
    ]


@router.get("/customer-insights")
def customer_insights(
    limit: int = Query(default=5, ge=1, le=20),
    _: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    last_paid = (
        db.query(
            Customer.username,
            Order.id,
            Order.total,
            func.coalesce(Order.completed_at, Order.created_at).label("paid_at"),
        )
        .join(Order, Order.customer_id == Customer.id)
        .filter(Order.status == "paid")
        .order_by(
            func.coalesce(Order.completed_at, Order.created_at).desc(),
            Order.id.desc(),
        )
        .first()
    )
    return {
        "today": top_customers_for_period(db, today, limit),
        "week": top_customers_for_period(db, week, limit),
        "month": top_customers_for_period(db, month, limit),
        "products_today": top_products_for_period(db, today, limit),
        "products_week": top_products_for_period(db, week, limit),
        "products_month": top_products_for_period(db, month, limit),
        "last_paid": (
            {
                "username": last_paid.username,
                "order_id": last_paid.id,
                "amount": round(last_paid.total, 2),
                "paid_at": last_paid.paid_at,
            }
            if last_paid
            else None
        ),
    }


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
        "next_due_date": get_due_date(db),
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
