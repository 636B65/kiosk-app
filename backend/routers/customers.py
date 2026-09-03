from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import Customer, Order, OrderItem
from schemas import CustomerHistoryOut, CustomerOut, CustomerStats, CustomerWithBalance
from security import get_current_user

router = APIRouter(prefix="/api/customers", tags=["customers"])


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
        order.completed_at = datetime.utcnow()
    db.commit()
    return {
        "username": customer.username,
        "settled": len(orders),
        "amount": round(sum(o.total for o in orders), 2),
    }