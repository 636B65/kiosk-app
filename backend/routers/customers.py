import unicodedata
from collections import defaultdict
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import audit
import pins
from database import get_db
from due_dates import get_due_date
from models import Customer, Order, OrderItem, Product, Setting, User
from schemas import (
    CustomerHistoryOut,
    CustomerOut,
    CustomerStats,
    CustomerWithBalance,
    FavoriteOut,
    MonthAgg,
    PinChangeIn,
    WeekdayAgg,
)
from security import get_current_user, get_optional_user
from timeutil import utcnow

router = APIRouter(prefix="/api/customers", tags=["customers"])

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
FAVORITES_LIMIT = 5


MAX_USERNAME_LENGTH = 64


def normalize_username(username: str | None) -> str:
    """Canonical form used for storing and looking up customer usernames."""
    return unicodedata.normalize("NFC", (username or "").strip().lower())


def validate_new_username(name: str) -> None:
    """Rules for creating a customer at the public kiosk.

    Control and format characters (e.g. zero-width spaces) are rejected so a new
    name cannot look identical to an existing one in the admin panel.
    """
    if len(name) > MAX_USERNAME_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Username must be at most {MAX_USERNAME_LENGTH} characters",
        )
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        raise HTTPException(
            status_code=422, detail="Username contains characters that are not allowed"
        )


def find_customer(db: Session, username: str) -> Customer:
    customer = (
        db.query(Customer)
        .filter(Customer.username == normalize_username(username))
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


PIN_HEADER = "X-Customer-PIN"


def check_customer_pin(db: Session, customer: Customer, pin: Optional[str]) -> None:
    """Enforce a customer's PIN, if they set one. Commits attempt counters.

    428 = PIN required, 403 = wrong PIN, 429 = locked after too many wrong PINs.
    """
    if not customer.has_pin:
        return
    now = utcnow()
    if customer.pin_locked_until and customer.pin_locked_until > now:
        minutes = max(1, int((customer.pin_locked_until - now).total_seconds() // 60) + 1)
        raise HTTPException(
            status_code=429,
            detail=f"Too many wrong PINs. Try again in {minutes} minute(s).",
        )
    if not pin:
        raise HTTPException(status_code=428, detail="PIN required")
    if not pins.verify_pin(customer.pin_hash, pin):
        customer.pin_failed_attempts = (customer.pin_failed_attempts or 0) + 1
        if customer.pin_failed_attempts >= pins.MAX_FAILED_ATTEMPTS:
            customer.pin_failed_attempts = 0
            customer.pin_locked_until = now + timedelta(minutes=pins.LOCK_MINUTES)
            audit.record(
                db, audit.KIOSK_ACTOR, "customer.pin_locked", "customer", customer.username,
                f"{pins.MAX_FAILED_ATTEMPTS} wrong PINs; locked for {pins.LOCK_MINUTES} min",
            )
        db.commit()
        raise HTTPException(status_code=403, detail="Wrong PIN")
    if customer.pin_failed_attempts or customer.pin_locked_until:
        customer.pin_failed_attempts = 0
        customer.pin_locked_until = None
        db.commit()


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
    paid_orders = [o for o in orders if o.status == "paid"]
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
        paid_orders=len(paid_orders),
        pending_orders=sum(o.status == "pending" for o in orders),
        cancelled_orders=sum(o.status == "cancelled" for o in orders),
        total_spent=round(total, 2),
        total_paid=round(paid, 2),
        balance=round(pending, 2),
        avg_order=round(total / count, 2) if count else 0.0,
        items_bought=int(items_qty or 0),
        first_order_at=orders[0].created_at if orders else None,
        last_order_at=orders[-1].created_at if orders else None,
        last_paid_at=(
            max(
                (o.completed_at or o.created_at for o in paid_orders),
                default=None,
            )
        ),
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


def favorites_for(db: Session, customer_id: int) -> List[FavoriteOut]:
    """Most-bought products (non-cancelled orders) that can still be bought."""
    rows = (
        db.query(
            Product.id,
            Product.name,
            func.sum(OrderItem.quantity).label("qty"),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.customer_id == customer_id,
            Order.status != "cancelled",
            Product.is_active,
        )
        .group_by(Product.id, Product.name)
        .order_by(func.sum(OrderItem.quantity).desc(), Product.name.asc())
        .limit(FAVORITES_LIMIT)
        .all()
    )
    return [
        FavoriteOut(product_id=row.id, name=row.name, quantity=int(row.qty or 0))
        for row in rows
    ]


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
                has_pin=c.has_pin,
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
    prefix = normalize_username(q)
    if not prefix:
        return []
    limit = max(1, min(limit, 20))
    # Escape LIKE wildcards so "%" or "_" cannot list names without a real prefix.
    pattern = (
        prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    )
    rows = (
        db.query(Customer.username)
        .filter(Customer.username.like(pattern, escape="\\"))
        .order_by(Customer.username)
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows]


@router.get("/{username}", response_model=CustomerHistoryOut)
def customer_lookup(
    username: str,
    as_admin: bool = False,
    pin: Optional[str] = Header(default=None, alias=PIN_HEADER),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    customer = find_customer(db, username)
    # Staff skip the PIN only when they ask for it explicitly (the admin panel
    # does), so an admin token left in a kiosk browser does not unlock lookups.
    if not (as_admin and user is not None):
        check_customer_pin(db, customer, pin)
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
        favorites=favorites_for(db, customer.id),
    )


def settle_pending(db: Session, customer: Customer, actor: str, action: str) -> dict:
    orders = (
        db.query(Order)
        .filter(Order.customer_id == customer.id, Order.status == "pending")
        .all()
    )
    for order in orders:
        order.status = "paid"
        order.completed_at = utcnow()
    amount = round(sum(o.total for o in orders), 2)
    if orders:
        audit.record(
            db, actor, action, "customer", customer.username,
            f"{len(orders)} order(s) marked paid: "
            + ", ".join(f"#{o.id}" for o in orders)
            + f"; amount {amount}",
        )
    db.commit()
    return {
        "username": customer.username,
        "settled": len(orders),
        "amount": amount,
    }


@router.post("/{username}/self-mark-paid")
def self_mark_paid(
    username: str,
    pin: Optional[str] = Header(default=None, alias=PIN_HEADER),
    db: Session = Depends(get_db),
):
    setting = db.get(Setting, "customer_self_service_payment")
    if not setting or setting.value != "true":
        raise HTTPException(
            status_code=403, detail="Customer self-service payment is disabled"
        )
    customer = find_customer(db, username)
    check_customer_pin(db, customer, pin)
    return settle_pending(db, customer, audit.KIOSK_ACTOR, "customer.self_mark_paid")


@router.post("/{username}/pin")
def set_pin(username: str, data: PinChangeIn, db: Session = Depends(get_db)):
    """A customer sets a PIN, or changes it (then the current PIN is required)."""
    customer = find_customer(db, username)
    if not pins.is_valid_pin(data.pin):
        raise HTTPException(status_code=422, detail="The PIN must be 4 to 8 digits")
    changing = customer.has_pin
    if changing:
        check_customer_pin(db, customer, data.current_pin)
    customer.pin_hash = pins.hash_pin(data.pin)
    customer.pin_failed_attempts = 0
    customer.pin_locked_until = None
    audit.record(
        db, audit.KIOSK_ACTOR, "customer.pin_changed" if changing else "customer.pin_set",
        "customer", customer.username,
    )
    db.commit()
    return {"username": customer.username, "has_pin": True}


@router.post("/{username}/reset-pin")
def reset_pin(
    username: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Staff remove a forgotten PIN - only once the customer owes nothing."""
    customer = find_customer(db, username)
    if not customer.has_pin:
        return {"username": customer.username, "has_pin": False}
    if totals_for(db, customer.id, "pending") > 0:
        raise HTTPException(
            status_code=409,
            detail="The customer has unpaid orders. Settle the balance before resetting the PIN.",
        )
    customer.pin_hash = None
    customer.pin_failed_attempts = 0
    customer.pin_locked_until = None
    audit.record(db, user.username, "customer.pin_reset", "customer", customer.username)
    db.commit()
    return {"username": customer.username, "has_pin": False}


@router.post("/{username}/reset-payment")
def reset_payment(
    username: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return settle_pending(
        db, find_customer(db, username), user.username, "customer.reset_payment"
    )
