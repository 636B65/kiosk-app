from collections import defaultdict
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from database import get_db
from due_dates import get_due_date
from models import Customer, Order, OrderItem
from schemas import (
    CustomerHistoryOut,
    CustomerOut,
    CustomerStats,
    CustomerWithBalance,
    MonthAgg,
    WeekdayAgg,
)
from security import get_current_user
from timeutil import utcnow

router = APIRouter(prefix="/api/customers", tags=["customers"])

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def find_customer(db: Session, username: str) -> Customer:
    customer = (
        db.query(Customer)
        .filter(Customer.username == (username or "").strip().lower())
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


def totals_for(db: Session, customer_id: int, status: str) -> float:
    total = (
        db.query(func.coalesce(func.sum(Order.total), 0.0))
        .filter(Order.customer_id == customer_id, Order.status == status)
        .scalar()
    )
    return round(total or 0.0, 2)


def stats_for(db: Session, customer_id: int) -> CustomerStats:
    orders = (
        db.query(Order)
        .filter(Order.customer_id == customer_id)
        .order_by(Order.created_at.asc())
        .all()
    )
    paid = sum(o.total for o in orders if o.status == "paid")
    pending = sum(o.total for o in orders if o.status == "pending")
    total = sum(o.total for o in orders)
    count = len(orders)

    items_qty = (
        db.query(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.customer_id == customer_id)
        .scalar()
    )

    top = (
        db.query(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("qty"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.customer_id == customer_id)
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .first()
    )

    per_month = defaultdict(int)
    month_spent = defaultdict(float)
    per_weekday = defaultdict(int)
    weekday_spent = defaultdict(float)
    for o in orders:
        per_month[o.created_at.strftime("%Y-%m")] += 1
        month_spent[o.created_at.strftime("%Y-%m")] += o.total
        per_weekday[o.created_at.weekday()] += 1
        weekday_spent[o.created_at.weekday()] += o.total

    busiest = max(per_weekday, key=per_weekday.get) if per_weekday else None
    month_count = len(per_month) or 1

    return CustomerStats(
        orders=count,
        total_spent=round(total, 2),
        total_paid=round(paid, 2),
        balance=round(pending, 2),
        avg_order=round(total / count, 2) if count else 0.0,
        items_bought=int(items_qty or 0),
        first_order_at=orders[0].created_at if orders else None,
        last_order_at=orders[-1].created_at if orders else None,
        top_item=top[0] if top else None,
        top_item_qty=int(top[1]) if top else 0,
        avg_orders_per_month=round(count / month_count, 2),
        busiest_day=WEEKDAY_NAMES[busiest] if busiest is not None else None,
        orders_per_month=[
            MonthAgg(month=k, orders=v, spent=round(month_spent[k], 2))
            for k, v in sorted(per_month.items())
        ],
        orders_by_weekday=[
            WeekdayAgg(
                day=WEEKDAY_NAMES[w],
                orders=per_weekday[w],
                spent=round(weekday_spent[w], 2),
            )
            for w in range(7)
            if w in per_weekday
        ],
        next_due_date=get_due_date(db),
    )


@router.get("", response_model=List[CustomerWithBalance])
def list_customers(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    customers = db.query(Customer).order_by(Customer.created_at.desc()).all()
    result = []
    for c in customers:
        result.append(
            CustomerWithBalance(
                id=c.id,
                username=c.username,
                created_at=c.created_at,
                balance=totals_for(db, c.id, "pending"),
                total_paid=totals_for(db, c.id, "paid"),
                order_count=db.query(Order)
                .filter(Order.customer_id == c.id)
                .count(),
                stats=stats_for(db, c.id),
            )
        )
    return result


@router.get("/suggest", response_model=List[str])
def suggest_customers(
    q: str = "",
    limit: int = 8,
    db: Session = Depends(get_db),
):
    """Autocomplete for the kiosk user lookup: return existing usernames that
    start with the typed prefix (public, matching the public lookup itself).

    Deliberately returns only usernames - never balances or history - and is
    capped so the kiosk cannot be used to dump the full customer list.
    """
    prefix = (q or "").strip().lower()
    if not prefix:
        return []
    limit = max(1, min(limit, 20))
    rows = (
        db.query(Customer.username)
        .filter(Customer.username.like(f"{prefix}%"))
        .order_by(Customer.username)
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows]


@router.get("/{username}", response_model=CustomerHistoryOut)
def customer_lookup(username: str, db: Session = Depends(get_db)):
    customer = find_customer(db, username)
    orders = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.customer_id == customer.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return CustomerHistoryOut(
        customer=CustomerOut.model_validate(customer),
        balance=totals_for(db, customer.id, "pending"),
        total_paid=totals_for(db, customer.id, "paid"),
        orders=orders,
        stats=stats_for(db, customer.id),
    )


@router.post("/{username}/reset-payment")
def reset_payment(
    username: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    customer = find_customer(db, username)
    orders = (
        db.query(Order)
        .filter(Order.customer_id == customer.id, Order.status == "pending")
        .all()
    )
    for order in orders:
        order.status = "paid"
        order.completed_at = utcnow()
    db.commit()
    return {
        "username": customer.username,
        "settled": len(orders),
        "amount": round(sum(o.total for o in orders), 2),
    }
