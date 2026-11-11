from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from customer_service import pins
from customer_service.models import Customer, Outbox
from customer_service.schemas import (
    CustomerHistoryOut,
    CustomerOut,
    CustomerStats,
    CustomerWithBalance,
    PinChangeIn,
    ResolveIn,
    ResolveOut,
)
from kiosk_common import audit
from kiosk_common.auth import Principal, get_current_user, get_optional_user
from kiosk_common.db import get_db
from kiosk_common.http import ServiceClient
from kiosk_common.internal import require_internal
from kiosk_common.timeutil import utcnow
from kiosk_common.usernames import normalize_username, validate_new_username

router = APIRouter(prefix="/api/customers", tags=["customers"])
internal = APIRouter(prefix="/internal/customers", tags=["internal"], dependencies=[Depends(require_internal)])

PIN_HEADER = "X-Customer-PIN"


def orders_client(request: Request) -> ServiceClient:
    return request.app.state.clients["orders"]


def settings_client(request: Request) -> ServiceClient:
    return request.app.state.clients["settings"]


def hasher(request: Request) -> pins.PinHasher:
    return request.app.state.pins


def find_customer(db: Session, username: str) -> Customer:
    customer = db.query(Customer).filter(Customer.username == normalize_username(username)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


def check_customer_pin(db: Session, pin_hasher: pins.PinHasher, customer: Customer, pin: Optional[str]) -> None:
    """Enforce a customer's PIN, if they set one. Commits attempt counters.

    428 = PIN required, 403 = wrong PIN, 429 = locked after too many wrong PINs.
    """
    if not customer.has_pin:
        return
    now = utcnow()
    if customer.pin_locked_until and customer.pin_locked_until > now:
        minutes = max(1, int((customer.pin_locked_until - now).total_seconds() // 60) + 1)
        raise HTTPException(status_code=429, detail=f"Too many wrong PINs. Try again in {minutes} minute(s).")
    if not pin:
        raise HTTPException(status_code=428, detail="PIN required")
    if not pin_hasher.verify_pin(customer.pin_hash, pin):
        customer.pin_failed_attempts = (customer.pin_failed_attempts or 0) + 1
        if customer.pin_failed_attempts >= pins.MAX_FAILED_ATTEMPTS:
            customer.pin_failed_attempts = 0
            customer.pin_locked_until = now + timedelta(minutes=pins.LOCK_MINUTES)
            audit.record(
                db, Outbox, audit.KIOSK_ACTOR, "customer.pin_locked", "customer", customer.username,
                f"{pins.MAX_FAILED_ATTEMPTS} wrong PINs; locked for {pins.LOCK_MINUTES} min",
            )
        db.commit()
        raise HTTPException(status_code=403, detail="Wrong PIN")
    if customer.pin_failed_attempts or customer.pin_locked_until:
        customer.pin_failed_attempts = 0
        customer.pin_locked_until = None
        db.commit()


# ---- public / admin API ---------------------------------------------------


@router.get("", response_model=List[CustomerWithBalance])
def list_customers(
    request: Request, db: Session = Depends(get_db), _: Principal = Depends(get_current_user)
):
    customers = db.query(Customer).order_by(Customer.created_at.desc()).all()
    summary = orders_client(request).get("/internal/orders/customers/stats")
    by_user = summary.get("customers", {})
    empty = CustomerStats(next_due_date=summary.get("next_due_date"))
    result = []
    for c in customers:
        entry = by_user.get(c.username) or {}
        result.append(
            CustomerWithBalance(
                id=c.id,
                username=c.username,
                created_at=c.created_at,
                has_pin=c.has_pin,
                balance=entry.get("balance", 0.0),
                total_paid=entry.get("total_paid", 0.0),
                order_count=entry.get("order_count", 0),
                stats=entry.get("stats") or empty,
            )
        )
    return result


@router.get("/suggest", response_model=List[str])
def suggest_customers(q: str = "", limit: int = 8, db: Session = Depends(get_db)):
    """Autocomplete for the kiosk user lookup: usernames only, never balances."""
    prefix = normalize_username(q)
    if not prefix:
        return []
    limit = max(1, min(limit, 20))
    pattern = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
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
    request: Request,
    as_admin: bool = False,
    pin: Optional[str] = Header(default=None, alias=PIN_HEADER),
    db: Session = Depends(get_db),
    user: Optional[Principal] = Depends(get_optional_user),
):
    customer = find_customer(db, username)
    # Staff skip the PIN only when they ask for it explicitly (the admin panel does).
    if not (as_admin and user is not None):
        check_customer_pin(db, hasher(request), customer, pin)
    history = orders_client(request).get(f"/internal/orders/customers/{customer.username}/history")
    return CustomerHistoryOut(
        customer=CustomerOut.model_validate(customer),
        balance=history["balance"],
        total_paid=history["total_paid"],
        orders=history["orders"],
        stats=history["stats"],
        favorites=history["favorites"],
    )


def settle_pending(request: Request, customer: Customer, actor: str, action: str) -> dict:
    """Mark every pending order paid (the order service does the compare-and-set)."""
    return orders_client(request).post(
        f"/internal/orders/customers/{customer.username}/settle",
        json={"actor": actor, "action": action},
    )


@router.post("/{username}/self-mark-paid")
def self_mark_paid(
    username: str,
    request: Request,
    pin: Optional[str] = Header(default=None, alias=PIN_HEADER),
    db: Session = Depends(get_db),
):
    settings = settings_client(request).get("/api/settings")
    if settings.get("customer_self_service_payment") != "true":
        raise HTTPException(status_code=403, detail="Customer self-service payment is disabled")
    customer = find_customer(db, username)
    check_customer_pin(db, hasher(request), customer, pin)
    return settle_pending(request, customer, audit.KIOSK_ACTOR, "customer.self_mark_paid")


@router.post("/{username}/pin")
def set_pin(username: str, data: PinChangeIn, request: Request, db: Session = Depends(get_db)):
    """A customer sets a PIN, or changes it (then the current PIN is required)."""
    customer = find_customer(db, username)
    if not pins.is_valid_pin(data.pin):
        raise HTTPException(status_code=422, detail="The PIN must be 4 to 8 digits")
    changing = customer.has_pin
    if changing:
        check_customer_pin(db, hasher(request), customer, data.current_pin)
    customer.pin_hash = hasher(request).hash_pin(data.pin)
    customer.pin_failed_attempts = 0
    customer.pin_locked_until = None
    audit.record(
        db, Outbox, audit.KIOSK_ACTOR, "customer.pin_changed" if changing else "customer.pin_set",
        "customer", customer.username,
    )
    db.commit()
    return {"username": customer.username, "has_pin": True}


@router.post("/{username}/reset-pin")
def reset_pin(
    username: str, request: Request, db: Session = Depends(get_db), user: Principal = Depends(get_current_user)
):
    """Staff remove a forgotten PIN - only once the customer owes nothing."""
    customer = find_customer(db, username)
    if not customer.has_pin:
        return {"username": customer.username, "has_pin": False}
    balance = orders_client(request).get(f"/internal/orders/customers/{customer.username}/balance")
    if balance["balance"] > 0:
        raise HTTPException(
            status_code=409,
            detail="The customer has unpaid orders. Settle the balance before resetting the PIN.",
        )
    customer.pin_hash = None
    customer.pin_failed_attempts = 0
    customer.pin_locked_until = None
    audit.record(db, Outbox, user.username, "customer.pin_reset", "customer", customer.username)
    db.commit()
    return {"username": customer.username, "has_pin": False}


@router.post("/{username}/reset-payment")
def reset_payment(
    username: str, request: Request, db: Session = Depends(get_db), user: Principal = Depends(get_current_user)
):
    return settle_pending(request, find_customer(db, username), user.username, "customer.reset_payment")


# ---- internal API (order service) ----------------------------------------


@internal.post("/resolve", response_model=ResolveOut)
def resolve_customer(data: ResolveIn, request: Request, db: Session = Depends(get_db)):
    """Find or create the customer placing an order and enforce their PIN.

    Failed PIN attempts are committed (and count toward the lockout) even
    though the order is then rejected. An admin token never bypasses this.
    """
    name = normalize_username(data.username)
    if not name:
        raise HTTPException(status_code=400, detail="A username is required")
    customer = db.query(Customer).filter(Customer.username == name).first()
    created = False
    if customer is None:
        validate_new_username(name)
        customer = Customer(username=name)
        db.add(customer)
        try:
            db.commit()
            created = True
        except IntegrityError:
            # Two first purchases for the same new username raced; use the winner's row.
            db.rollback()
            customer = db.query(Customer).filter(Customer.username == name).first()
    check_customer_pin(db, hasher(request), customer, data.pin)
    return ResolveOut(id=customer.id, username=customer.username, created=created)


@internal.get("", response_model=List[CustomerOut])
def list_all(db: Session = Depends(get_db)):
    return db.query(Customer).order_by(Customer.username).all()


@internal.get("/stats")
def stats(db: Session = Depends(get_db)):
    return {"customers": db.query(Customer).count()}
