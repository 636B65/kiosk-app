"""Per-customer statistics computed over that customer's orders."""

from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from kiosk_common.money import money
from order_service.models import Order, OrderItem
from order_service.schemas import CustomerStats, MonthAgg, WeekdayAgg

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
FAVORITES_LIMIT = 5


def totals_for(db: Session, username: str, status: str) -> float:
    total = (
        db.query(func.coalesce(func.sum(Order.total), 0.0))
        .filter(Order.customer_username == username, Order.status == status)
        .scalar()
    )
    return money(total)


def stats_for(db: Session, username: str, next_due_date) -> CustomerStats:
    orders = (
        db.query(Order)
        .filter(Order.customer_username == username)
        .order_by(Order.created_at.asc(), Order.id.asc())
        .all()
    )
    return stats_from_orders(db, username, orders, next_due_date)


def stats_from_orders(db: Session, username: str, orders: list, next_due_date) -> CustomerStats:
    paid = sum(o.total for o in orders if o.status == "paid")
    pending = sum(o.total for o in orders if o.status == "pending")
    total = sum(o.total for o in orders)
    paid_orders = [o for o in orders if o.status == "paid"]
    count = len(orders)

    items_qty = (
        db.query(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.customer_username == username)
        .scalar()
    )
    top = (
        db.query(OrderItem.product_name, func.sum(OrderItem.quantity).label("qty"))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.customer_username == username)
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .first()
    )

    per_month = defaultdict(int)
    month_spent = defaultdict(float)
    per_weekday = defaultdict(int)
    weekday_spent = defaultdict(float)
    for o in orders:
        key = o.created_at.strftime("%Y-%m")
        per_month[key] += 1
        month_spent[key] += o.total
        per_weekday[o.created_at.weekday()] += 1
        weekday_spent[o.created_at.weekday()] += o.total

    busiest = max(per_weekday, key=per_weekday.get) if per_weekday else None
    month_count = len(per_month) or 1

    return CustomerStats(
        orders=count,
        paid_orders=len(paid_orders),
        pending_orders=sum(o.status == "pending" for o in orders),
        cancelled_orders=sum(o.status == "cancelled" for o in orders),
        total_spent=money(total),
        total_paid=money(paid),
        balance=money(pending),
        avg_order=money(total / count) if count else 0.0,
        items_bought=int(items_qty or 0),
        first_order_at=orders[0].created_at if orders else None,
        last_order_at=orders[-1].created_at if orders else None,
        last_paid_at=max((o.completed_at or o.created_at for o in paid_orders), default=None),
        last_paid_amount=(
            max(paid_orders, key=lambda o: (o.completed_at or o.created_at, o.id)).total
            if paid_orders
            else 0.0
        ),
        top_item=top[0] if top else None,
        top_item_qty=int(top[1]) if top else 0,
        avg_orders_per_month=round(count / month_count, 2),
        busiest_day=WEEKDAY_NAMES[busiest] if busiest is not None else None,
        orders_per_month=[
            MonthAgg(month=k, orders=v, spent=money(month_spent[k])) for k, v in sorted(per_month.items())
        ],
        orders_by_weekday=[
            WeekdayAgg(day=WEEKDAY_NAMES[w], orders=per_weekday[w], spent=money(weekday_spent[w]))
            for w in range(7)
            if w in per_weekday
        ],
        next_due_date=next_due_date,
    )


def favorite_candidates(db: Session, username: str, limit: int = 20) -> list[tuple[int, int]]:
    """(product_id, quantity) over non-cancelled orders, most bought first."""
    rows = (
        db.query(OrderItem.product_id, func.sum(OrderItem.quantity).label("qty"))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.customer_username == username,
            Order.status != "cancelled",
            OrderItem.product_id.isnot(None),
        )
        .group_by(OrderItem.product_id)
        .order_by(func.sum(OrderItem.quantity).desc(), OrderItem.product_id.asc())
        .limit(limit)
        .all()
    )
    return [(int(r.product_id), int(r.qty or 0)) for r in rows]
