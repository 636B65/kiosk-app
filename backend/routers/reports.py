import csv
import io
from datetime import datetime, timedelta

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session
from starlette.responses import Response

from database import get_db
from due_dates import get_due_date
from models import Customer, Order, OrderItem, Product
from security import get_current_user
from timeutil import utcnow

router = APIRouter(prefix="/api/reports", tags=["reports"])


def revenue_for_period(db: Session, start: datetime = None, end: datetime = None):
    paid_at = func.coalesce(Order.completed_at, Order.created_at)
    query = db.query(
        func.count(Order.id),
        func.coalesce(func.sum(Order.total), 0.0),
    ).filter(Order.status == "paid")
    if start:
        query = query.filter(paid_at >= start)
    if end:
        query = query.filter(paid_at < end)
    count, total = query.first()
    return {"order_count": count, "revenue": round(total or 0.0, 2)}


def outstanding_total(db: Session) -> float:
    total = (
        db.query(func.coalesce(func.sum(Order.total), 0.0))
        .filter(Order.status == "pending")
        .scalar()
    )
    return round(total or 0.0, 2)


def low_stock_products(db: Session) -> list[dict]:
    """Active products at or below their own restock threshold, emptiest first."""
    products = (
        db.query(Product)
        .filter(
            Product.is_active,
            Product.stock <= func.coalesce(Product.low_stock_threshold, 0),
        )
        .order_by(Product.stock.asc(), Product.name.asc())
        .all()
    )
    return [
        {
            "id": p.id,
            "name": p.name,
            "stock": p.stock,
            "low_stock_threshold": p.low_stock_threshold,
            "price": p.price,
            "special_price": p.special_price,
            "is_weekly_special": p.is_weekly_special,
            "special_active": p.special_active,
            "cost_price": p.cost_price,
        }
        for p in products
    ]


def margins_for_period(
    db: Session, start: datetime | None = None, end: datetime | None = None
) -> dict:
    """Paid sales per product with cost and margin.

    Cost comes from the purchase price snapshotted on each order line, so
    lines sold before a cost was known count toward revenue but are left out
    of the margin (reported as ``uncosted_quantity``).
    """
    paid_at = func.coalesce(Order.completed_at, Order.created_at)
    costed = OrderItem.unit_cost.isnot(None)
    line_revenue = OrderItem.unit_price * OrderItem.quantity
    query = (
        db.query(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("quantity"),
            func.coalesce(func.sum(line_revenue), 0.0).label("revenue"),
            func.coalesce(
                func.sum(case((costed, line_revenue), else_=0.0)), 0.0
            ).label("costed_revenue"),
            func.coalesce(
                func.sum(case((costed, OrderItem.unit_cost * OrderItem.quantity), else_=0.0)),
                0.0,
            ).label("cost"),
            func.coalesce(
                func.sum(case((costed, 0), else_=OrderItem.quantity)), 0
            ).label("uncosted_quantity"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status == "paid")
    )
    if start:
        query = query.filter(paid_at >= start)
    if end:
        query = query.filter(paid_at < end)
    rows = query.group_by(OrderItem.product_name).all()

    def margin_row(name, quantity, revenue, costed_revenue, cost, uncosted):
        margin = costed_revenue - cost
        return {
            "product": name,
            "quantity": int(quantity or 0),
            "revenue": round(revenue or 0.0, 2),
            "cost": round(cost or 0.0, 2),
            "margin": round(margin, 2),
            "margin_pct": round(margin / costed_revenue * 100, 1) if costed_revenue else None,
            "uncosted_quantity": int(uncosted or 0),
        }

    products = [
        margin_row(
            r.product_name, r.quantity, r.revenue, r.costed_revenue, r.cost, r.uncosted_quantity
        )
        for r in rows
    ]
    products.sort(key=lambda r: (-r["margin"], -r["revenue"], r["product"]))
    totals = margin_row(
        None,
        sum(r.quantity or 0 for r in rows),
        sum(r.revenue or 0.0 for r in rows),
        sum(r.costed_revenue or 0.0 for r in rows),
        sum(r.cost or 0.0 for r in rows),
        sum(r.uncosted_quantity or 0 for r in rows),
    )
    totals.pop("product")
    return {"products": products, "totals": totals}


def period_bounds(period: str, now: datetime) -> tuple[datetime | None, datetime | None]:
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        return today, today + timedelta(days=1)
    if period == "week":
        week = today - timedelta(days=today.weekday())
        return week, week + timedelta(days=7)
    if period == "month":
        month = today.replace(day=1)
        next_month = (
            month.replace(year=month.year + 1, month=1)
            if month.month == 12
            else month.replace(month=month.month + 1)
        )
        return month, next_month
    return None, None


def top_customers_for_period(
    db: Session,
    start: datetime | None,
    limit: int,
    end: datetime | None = None,
) -> list[dict]:
    paid_at = func.coalesce(Order.completed_at, Order.created_at)
    query = (
        db.query(
            Customer.username,
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total), 0.0).label("spent"),
        )
        .join(Order, Order.customer_id == Customer.id)
        .filter(Order.status == "paid")
    )
    if start:
        query = query.filter(paid_at >= start)
    if end:
        query = query.filter(paid_at < end)
    rows = (
        query.group_by(Customer.id, Customer.username)
        .order_by(
            func.coalesce(func.sum(Order.total), 0.0).desc(),
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
    db: Session,
    start: datetime | None,
    limit: int,
    end: datetime | None = None,
) -> list[dict]:
    paid_at = func.coalesce(Order.completed_at, Order.created_at)
    query = (
        db.query(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("quantity"),
            func.coalesce(
                func.sum(OrderItem.unit_price * OrderItem.quantity), 0.0
            ).label("revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status == "paid")
        .group_by(OrderItem.product_name)
        .order_by(
            func.sum(OrderItem.quantity).desc(),
            func.sum(OrderItem.unit_price * OrderItem.quantity).desc(),
            OrderItem.product_name.asc(),
        )
    )
    if start:
        query = query.filter(paid_at >= start)
    if end:
        query = query.filter(paid_at < end)
    rows = query.limit(limit).all()
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
    tomorrow = today + timedelta(days=1)
    week = today - timedelta(days=today.weekday())
    next_week = week + timedelta(days=7)
    month = today.replace(day=1)
    next_month = (
        month.replace(year=month.year + 1, month=1)
        if month.month == 12
        else month.replace(month=month.month + 1)
    )
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
        "today": top_customers_for_period(db, today, limit, tomorrow),
        "week": top_customers_for_period(db, week, limit, next_week),
        "month": top_customers_for_period(db, month, limit, next_month),
        "products_today": top_products_for_period(db, today, limit, tomorrow),
        "products_week": top_products_for_period(db, week, limit, next_week),
        "products_month": top_products_for_period(db, month, limit, next_month),
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
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())
    next_week = week + timedelta(days=7)
    month = today.replace(day=1)
    next_month = (
        month.replace(year=month.year + 1, month=1)
        if month.month == 12
        else month.replace(month=month.month + 1)
    )
    return {
        "today": revenue_for_period(db, start=today, end=today + timedelta(days=1)),
        "yesterday": revenue_for_period(
            db,
            start=today - timedelta(days=1),
            end=today,
        ),
        "week": revenue_for_period(db, start=week, end=next_week),
        "month": revenue_for_period(db, start=month, end=next_month),
        "all_time": revenue_for_period(db),
        "outstanding": outstanding_total(db),
        "pending_orders": db.query(Order).filter(Order.status == "pending").count(),
        "next_due_date": get_due_date(db),
        "low_stock_products": low_stock_products(db),
        "margin_month": margins_for_period(db, month, next_month)["totals"],
    }


@router.get("/margins")
def margins(
    period: Literal["today", "week", "month", "all"] = "all",
    _: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start, end = period_bounds(period, utcnow())
    return {"period": period, **margins_for_period(db, start, end)}


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
    paid_at = func.coalesce(Order.completed_at, Order.created_at)
    paid_day = func.date(paid_at)
    rows = (
        db.query(
            paid_day.label("day"),
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), 0.0),
        )
        .filter(Order.status == "paid", paid_at >= start)
        .group_by(paid_day)
        .order_by(paid_day)
        .all()
    )
    return [
        {"day": r.day, "orders": r[1], "revenue": round(r[2], 2)} for r in rows
    ]


@router.get("/export.csv")
def export_csv(_: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())
    next_week = week + timedelta(days=7)
    month = today.replace(day=1)
    next_month = (
        month.replace(year=month.year + 1, month=1)
        if month.month == 12
        else month.replace(month=month.month + 1)
    )
    last_14_days = now - timedelta(days=14)

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "section",
            "period",
            "record",
            "id",
            "name",
            "count",
            "quantity",
            "amount",
            "unit_price",
            "stock",
            "stock_value",
            "details",
        ]
    )

    def write_row(
        section,
        period="",
        record="",
        record_id="",
        name="",
        count="",
        quantity="",
        amount="",
        unit_price="",
        stock="",
        stock_value="",
        details="",
    ):
        values = [
            section,
            period,
            record,
            record_id,
            name,
            count,
            quantity,
            amount,
            unit_price,
            stock,
            stock_value,
            details,
        ]
        safe_values = [
            "'" + value
            if isinstance(value, str)
            and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
            else value
            for value in values
        ]
        writer.writerow(safe_values)

    for period, start, end in (
        ("today", today, today + timedelta(days=1)),
        ("yesterday", today - timedelta(days=1), today),
        ("last_7_days", now - timedelta(days=7), None),
        ("last_30_days", now - timedelta(days=30), None),
        ("all_time", None, None),
    ):
        totals = revenue_for_period(db, start=start, end=end)
        write_row(
            "sales_summary",
            period=period,
            count=totals["order_count"],
            amount=totals["revenue"],
            details="paid orders and revenue",
        )

    pending_orders = (
        db.query(Order)
        .filter(Order.status == "pending")
        .order_by(Order.created_at, Order.id)
        .all()
    )
    pending_by_customer = {}
    for order in pending_orders:
        if order.customer_id is None:
            continue
        pending_by_customer.setdefault(order.customer_id, []).append(order)

    write_row(
        "outstanding",
        record="store_total",
        count=len(pending_orders),
        amount=outstanding_total(db),
        details="total pending customer balance",
    )
    write_row(
        "payment_due_date",
        record="store",
        details=get_due_date(db) or "not configured",
    )
    paid_by_customer = {
        row.customer_id: (
            row.order_count,
            row.paid_orders,
            round(row.paid_total or 0.0, 2),
        )
        for row in db.query(
            Order.customer_id,
            func.count(Order.id).label("order_count"),
            func.sum(case((Order.status == "paid", 1), else_=0)).label("paid_orders"),
            func.coalesce(
                func.sum(case((Order.status == "paid", Order.total), else_=0.0)),
                0.0,
            ).label("paid_total"),
        )
        .group_by(Order.customer_id)
        .all()
        if row.customer_id is not None
    }
    for customer in db.query(Customer).order_by(Customer.username).all():
        orders = pending_by_customer.get(customer.id, [])
        total_orders, paid_orders, paid_total = paid_by_customer.get(
            customer.id, (0, 0, 0.0)
        )
        write_row(
            "customer_summary",
            record="lifetime",
            record_id=customer.id,
            name=customer.username,
            count=total_orders,
            amount=paid_total,
            details=f"paid orders: {paid_orders}",
        )
        write_row(
            "customer_balance",
            record="pending",
            record_id=customer.id,
            name=customer.username,
            count=len(orders),
            amount=round(sum(order.total for order in orders), 2),
            details="pending orders: "
            + "; ".join(
                f"#{order.id} due {order.due_date.isoformat() if order.due_date else 'not set'}"
                for order in orders
            ),
        )

    for product in db.query(Product).order_by(Product.name, Product.id).all():
        unit_price = product.effective_price
        category = product.category.name if product.category else ""
        cost = (
            f"; cost price {product.cost_price}; value at cost "
            f"{round(product.stock * product.cost_price, 2)}"
            if product.cost_price is not None
            else "; cost price not set"
        )
        write_row(
            "inventory",
            record="active" if product.is_active else "inactive",
            record_id=product.id,
            name=product.name,
            unit_price=unit_price,
            stock=product.stock,
            stock_value=round(product.stock * unit_price, 2),
            details=f"category: {category}; value at current selling price{cost}",
        )

    for product in low_stock_products(db):
        write_row(
            "restock_needed",
            record="low_stock",
            record_id=product["id"],
            name=product["name"],
            stock=product["stock"],
            details=f"threshold {product['low_stock_threshold']}",
        )

    for period in ("month", "all"):
        start, end = period_bounds(period, now)
        report = margins_for_period(db, start, end)
        for row in report["products"]:
            write_row(
                "margins",
                period="all_time" if period == "all" else period,
                record="product",
                name=row["product"],
                quantity=row["quantity"],
                amount=row["margin"],
                details=(
                    f"revenue {row['revenue']}; cost {row['cost']}; margin "
                    f"{row['margin_pct'] if row['margin_pct'] is not None else '-'}%; "
                    f"units without cost {row['uncosted_quantity']}"
                ),
            )
        totals = report["totals"]
        write_row(
            "margins",
            period="all_time" if period == "all" else period,
            record="store_total",
            quantity=totals["quantity"],
            amount=totals["margin"],
            details=f"revenue {totals['revenue']}; cost {totals['cost']}",
        )

    paid_at = func.coalesce(Order.completed_at, Order.created_at)
    paid_day = func.date(paid_at)
    for day in (
        db.query(
            paid_day.label("day"),
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), 0.0),
        )
        .filter(Order.status == "paid", paid_at >= last_14_days)
        .group_by(paid_day)
        .order_by(paid_day)
        .all()
    ):
        write_row(
            "daily_sales",
            period=day.day,
            count=day[1],
            amount=round(day[2], 2),
            details="paid orders and revenue",
        )

    for period, start, end in (
        ("today", today, today + timedelta(days=1)),
        ("week", week, next_week),
        ("month", month, next_month),
    ):
        for rank, customer in enumerate(
            top_customers_for_period(db, start, 20, end), 1
        ):
            write_row(
                "top_customers",
                period=period,
                record=f"rank_{rank}",
                name=customer["username"],
                count=customer["orders"],
                amount=customer["spent"],
            )
        for rank, product in enumerate(
            top_products_for_period(db, start, 20, end), 1
        ):
            write_row(
                "top_products",
                period=period,
                record=f"rank_{rank}",
                name=product["product"],
                quantity=product["quantity"],
                amount=product["revenue"],
            )
    for rank, product in enumerate(top_products_for_period(db, None, 20), 1):
        write_row(
            "top_products",
            period="all_time",
            record=f"rank_{rank}",
            name=product["product"],
            quantity=product["quantity"],
            amount=product["revenue"],
        )

    latest_payment = (
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
    if latest_payment:
        write_row(
            "last_payment",
            record="latest",
            record_id=latest_payment.id,
            name=latest_payment.username,
            amount=round(latest_payment.total, 2),
            details=latest_payment.paid_at.isoformat(),
        )

    filename = f"kiosk-report-{now:%Y-%m-%d}.csv"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
