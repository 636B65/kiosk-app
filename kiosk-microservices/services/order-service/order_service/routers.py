import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from kiosk_common import audit
from kiosk_common.auth import Principal, get_current_user
from kiosk_common.db import get_db
from kiosk_common.http import ServiceClient, UpstreamError
from kiosk_common.internal import require_internal
from kiosk_common.money import money
from kiosk_common.outbox import publish
from kiosk_common.timeutil import parse_dt, utcnow
from kiosk_common.usernames import normalize_username
from order_service.due_dates import due_time_from_settings
from order_service.models import Order, OrderItem, Outbox
from order_service.schemas import (
    CustomerHistoryOut,
    CustomersStatsOut,
    CustomerSummary,
    FavoriteOut,
    OrderCreate,
    OrderExportOut,
    OrderItemOut,
    OrderOut,
    SettleIn,
)
from order_service.stats import favorite_candidates, stats_for, stats_from_orders, totals_for

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])
internal = APIRouter(prefix="/internal/orders", tags=["internal"], dependencies=[Depends(require_internal)])

VALID_STATUSES = ("pending", "paid", "cancelled")
# A cancelled order has already given its stock back, so it can never become
# pending or paid again (that would count its items as sold and in stock at once).
ALLOWED_TRANSITIONS = {
    "pending": {"paid", "cancelled"},
    "paid": {"pending", "cancelled"},
    "cancelled": set(),
}
STOCK_RELEASE_TOPIC = "stock.release"

OVERDUE_DETAIL = (
    "The payment due date has passed and your previous order is still unpaid. "
    "Ask the staff to mark it as paid before you can buy again."
)


def _clients(request: Request) -> dict[str, ServiceClient]:
    return request.app.state.clients


def _due_date(request: Request):
    settings = _clients(request)["settings"].get("/api/settings") or {}
    return due_time_from_settings(settings)


def _release_stock(request: Request, db: Session, items: list[dict], reason: str) -> None:
    """Give reserved stock back; if the catalog is down, retry via the outbox."""
    try:
        _clients(request)["catalog"].post("/internal/stock/release", json={"items": items})
    except UpstreamError as exc:
        logger.warning("stock release (%s) deferred to the outbox: %s", reason, exc)
        publish(db, Outbox, STOCK_RELEASE_TOPIC, {"items": items, "reason": reason})
        db.commit()


# ---- admin API --------------------------------------------------------------


@router.get("", response_model=List[OrderOut])
def list_orders(
    status_: Optional[str] = None, db: Session = Depends(get_db), _: Principal = Depends(get_current_user)
):
    query = db.query(Order)
    if status_:
        query = query.filter(Order.status == status_)
    return query.order_by(Order.created_at.desc(), Order.id.desc()).all()


@router.get("/{order_id}/items", response_model=List[OrderItemOut])
def get_order_items(order_id: int, db: Session = Depends(get_db), _: Principal = Depends(get_current_user)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order.items


# ---- kiosk checkout (public) ------------------------------------------------


@router.post("", response_model=OrderOut, status_code=201)
def create_order(data: OrderCreate, request: Request, db: Session = Depends(get_db)):
    """Tab checkout.

    1. The customer service finds/creates the customer and checks their PIN
       (428/403/429 are passed through unchanged).
    2. An OVERDUE balance blocks the purchase (403); with no due date, or one
       still in the future, orders stack freely on the tab.
    3. The catalog reserves the stock for every line, all or nothing (400 when
       a product is unavailable or short), and returns the price snapshot.
    4. The order is written here; if that fails the reserved stock is released.
    """
    if not data.items:
        raise HTTPException(status_code=400, detail="Order must contain items")
    clients = _clients(request)
    customer = clients["customers"].post(
        "/internal/customers/resolve",
        json={"username": data.customer_username, "pin": data.customer_pin},
    )
    username = customer["username"]

    due = _due_date(request)
    if due is not None and due < utcnow():
        has_unpaid = (
            db.query(Order).filter(Order.customer_username == username, Order.status == "pending").count()
        )
        if has_unpaid:
            raise HTTPException(status_code=403, detail=OVERDUE_DETAIL)

    reserved = clients["catalog"].post(
        "/internal/stock/reserve",
        json={"items": [item.model_dump() for item in data.items]},
    )
    lines = reserved["items"]
    try:
        order = Order(
            status="pending",
            notes=data.notes,
            customer_id=customer["id"],
            customer_username=username,
            due_date=due,
        )
        subtotal = 0.0
        for line in lines:
            subtotal += line["unit_price"] * line["quantity"]
            order.items.append(
                OrderItem(
                    product_id=line["product_id"],
                    product_name=line["product_name"],
                    quantity=line["quantity"],
                    unit_price=line["unit_price"],
                    unit_cost=line.get("unit_cost"),
                )
            )
        order.subtotal = money(subtotal)
        order.total = money(subtotal)
        db.add(order)
        db.commit()
    except Exception:
        db.rollback()
        _release_stock(
            request, db,
            [{"product_id": line["product_id"], "quantity": line["quantity"]} for line in lines],
            "order write failed",
        )
        raise
    db.refresh(order)
    return order


@router.patch("/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: int,
    new_status: str,
    request: Request,
    expected_status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Principal = Depends(get_current_user),
):
    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    order = db.query(Order).options(joinedload(Order.items)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    previous = order.status
    # The admin buttons send the status they were shown: a "Cancel" meant for a
    # pending order must not turn into paid -> cancelled (no stock restored)
    # because Reset payment marked it paid a moment earlier.
    if expected_status is not None and previous != expected_status:
        raise HTTPException(status_code=409, detail=f"Order #{order.id} is already {previous}; nothing was changed.")
    if new_status == previous:
        return order
    if new_status not in ALLOWED_TRANSITIONS[previous]:
        raise HTTPException(
            status_code=409,
            detail="A cancelled order cannot be reopened or paid; place a new order instead.",
        )
    values = {"status": new_status}
    if new_status != "pending":
        values["completed_at"] = utcnow()
    # Compare-and-set: of two simultaneous changes only one may win.
    claimed = (
        db.query(Order)
        .filter(Order.id == order_id, Order.status == previous)
        .update(values, synchronize_session=False)
    )
    if claimed != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The order was changed at the same time by someone else. Reload and try again.",
        )
    restored = ""
    items = [{"product_id": i.product_id, "quantity": i.quantity} for i in order.items if i.product_id]
    if previous == "pending" and new_status == "cancelled":
        restored = " (stock restored)"
    audit.record(
        db, Outbox, user.username, f"order.{new_status}", "order", order.id,
        f"{order.customer_username or '-'}: {previous} -> {new_status}, total {order.total}{restored}",
    )
    db.commit()
    if restored and items:
        _release_stock(request, db, items, f"order #{order.id} cancelled")
    db.refresh(order)
    return order


# ---- internal API (customer service, report service, system service) --------


def _favorites(request: Request, db: Session, username: str) -> List[FavoriteOut]:
    """Most-bought products (non-cancelled orders) that can still be bought."""
    candidates = favorite_candidates(db, username)
    if not candidates:
        return []
    ids = ",".join(str(pid) for pid, _ in candidates)
    try:
        products = _clients(request)["catalog"].get("/internal/products", params={"ids": ids, "active_only": "true"})
    except UpstreamError:
        return []
    names = {p["id"]: p["name"] for p in products}
    favorites = [
        FavoriteOut(product_id=pid, name=names[pid], quantity=qty) for pid, qty in candidates if pid in names
    ]
    favorites.sort(key=lambda f: (-f.quantity, f.name))
    return favorites[:5]


@internal.get("/customers/stats", response_model=CustomersStatsOut)
def customers_stats(request: Request, db: Session = Depends(get_db)):
    """Balance, totals and statistics for every customer with orders (admin list)."""
    due = _due_date(request)
    orders = db.query(Order).filter(Order.customer_username.isnot(None)).order_by(Order.created_at, Order.id).all()
    grouped: dict[str, list] = {}
    for order in orders:
        grouped.setdefault(order.customer_username, []).append(order)
    result = {}
    for username, rows in grouped.items():
        result[username] = CustomerSummary(
            balance=money(sum(o.total for o in rows if o.status == "pending")),
            total_paid=money(sum(o.total for o in rows if o.status == "paid")),
            order_count=len(rows),
            stats=stats_from_orders(db, username, rows, due),
        )
    return CustomersStatsOut(next_due_date=due, customers=result)


@internal.get("/customers/{username}/history", response_model=CustomerHistoryOut)
def customer_history(username: str, request: Request, db: Session = Depends(get_db)):
    name = normalize_username(username)
    orders = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.customer_username == name)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )
    return CustomerHistoryOut(
        balance=totals_for(db, name, "pending"),
        total_paid=totals_for(db, name, "paid"),
        orders=orders,
        stats=stats_for(db, name, _due_date(request)),
        favorites=_favorites(request, db, name),
    )


@internal.get("/customers/{username}/balance")
def customer_balance(username: str, db: Session = Depends(get_db)):
    name = normalize_username(username)
    return {
        "username": name,
        "balance": totals_for(db, name, "pending"),
        "total_paid": totals_for(db, name, "paid"),
        "pending_orders": db.query(Order).filter(Order.customer_username == name, Order.status == "pending").count(),
    }


@internal.post("/customers/{username}/settle")
def settle_customer(username: str, data: SettleIn, db: Session = Depends(get_db)):
    """Mark ALL pending orders of a customer paid (reset payment / self-mark-paid)."""
    name = normalize_username(username)
    orders = db.query(Order).filter(Order.customer_username == name, Order.status == "pending").all()
    # Compare-and-set per order: an order cancelled by staff at this very moment
    # (its stock already restored) must not end up paid.
    now = utcnow()
    settled = []
    for order in orders:
        claimed = (
            db.query(Order)
            .filter(Order.id == order.id, Order.status == "pending")
            .update({"status": "paid", "completed_at": now}, synchronize_session=False)
        )
        if claimed:
            settled.append(order)
    amount = money(sum(o.total for o in settled))
    if settled:
        audit.record(
            db, Outbox, data.actor, data.action, "customer", name,
            f"{len(settled)} order(s) marked paid: " + ", ".join(f"#{o.id}" for o in settled) + f"; amount {amount}",
        )
    db.commit()
    return {"username": name, "settled": len(settled), "amount": amount}


@internal.get("/export", response_model=List[OrderExportOut])
def export_orders(
    since: Optional[str] = None, status_: Optional[str] = None, db: Session = Depends(get_db)
):
    """Every order with its lines (cost included) for the report service."""
    query = db.query(Order).options(joinedload(Order.items))
    if since:
        query = query.filter(Order.created_at >= parse_dt(since))
    if status_:
        query = query.filter(Order.status == status_)
    return query.order_by(Order.created_at, Order.id).all()


@internal.get("/stats")
def stats(db: Session = Depends(get_db)):
    return {
        "orders": db.query(Order).count(),
        "pending_orders": db.query(Order).filter(Order.status == "pending").count(),
    }
