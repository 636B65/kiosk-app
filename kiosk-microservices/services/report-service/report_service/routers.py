import csv
import io
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from starlette.responses import Response

from kiosk_common.auth import get_current_user
from kiosk_common.csvutil import csv_safe
from kiosk_common.money import money
from kiosk_common.timeutil import utcnow
from report_service import reports as R
from report_service.data import load, load_adjustments
from report_service.reports import BASIS_LABEL, Basis

router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(get_current_user)])


def _calendar(now):
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    return today, week, week + timedelta(days=7), month, R.next_month_start(month)


@router.get("/customer-insights")
def customer_insights(request: Request, limit: int = Query(default=5, ge=1, le=20), basis: Basis = "sales"):
    orders = load(request).orders
    today, week, next_week, month, next_month = _calendar(utcnow())
    tomorrow = today + timedelta(days=1)
    return {
        "basis": basis,
        "today": R.top_customers_for_period(orders, today, limit, tomorrow, basis),
        "week": R.top_customers_for_period(orders, week, limit, next_week, basis),
        "month": R.top_customers_for_period(orders, month, limit, next_month, basis),
        "products_today": R.top_products_for_period(orders, today, limit, tomorrow, basis),
        "products_week": R.top_products_for_period(orders, week, limit, next_week, basis),
        "products_month": R.top_products_for_period(orders, month, limit, next_month, basis),
        "last_paid": R.last_payment(orders),
    }


@router.get("/summary")
def summary(request: Request, basis: Basis = "sales"):
    data = load(request, products=True, settings=True)
    orders = data.orders
    today, week, next_week, month, next_month = _calendar(utcnow())
    return {
        "basis": basis,
        "today": R.revenue_for_period(orders, today, today + timedelta(days=1), basis),
        "yesterday": R.revenue_for_period(orders, today - timedelta(days=1), today, basis),
        "week": R.revenue_for_period(orders, week, next_week, basis),
        "month": R.revenue_for_period(orders, month, next_month, basis),
        "all_time": R.revenue_for_period(orders, basis=basis),
        "outstanding": R.outstanding_total(orders),
        "pending_orders": sum(o["status"] == "pending" for o in orders),
        "next_due_date": data.due_date,
        "low_stock_products": R.low_stock_products(data.products),
        "margin_month": R.margins_for_period(orders, month, next_month, basis)["totals"],
    }


@router.get("/margins")
def margins(request: Request, period: Literal["today", "week", "month", "all"] = "all", basis: Basis = "sales"):
    start, end = R.period_bounds(period, utcnow())
    return {"period": period, "basis": basis, **R.margins_for_period(load(request).orders, start, end, basis)}


@router.get("/top-products")
def top_products(request: Request, limit: int = 10, basis: Basis = "sales"):
    return R.top_products_for_period(load(request).orders, None, limit, None, basis)


@router.get("/sales-by-day")
def sales_by_day(request: Request, days: int = 14, basis: Basis = "sales"):
    return R.sales_by_day(load(request).orders, utcnow() - timedelta(days=days), basis)


@router.get("/export.csv")
def export_csv(request: Request, basis: Basis = "sales"):
    data = load(request, products=True, customers=True, settings=True)
    orders = data.orders
    now = utcnow()
    today, week, next_week, month, next_month = _calendar(now)
    last_14_days = now - timedelta(days=14)

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "section", "period", "record", "id", "name", "count", "quantity", "amount",
        "unit_price", "stock", "stock_value", "details",
    ])

    def write_row(section, period="", record="", record_id="", name="", count="", quantity="",
                  amount="", unit_price="", stock="", stock_value="", details=""):
        values = [section, period, record, record_id, name, count, quantity, amount,
                  unit_price, stock, stock_value, details]
        writer.writerow([csv_safe(value) for value in values])

    for period, start, end in (
        ("today", today, today + timedelta(days=1)),
        ("yesterday", today - timedelta(days=1), today),
        ("last_7_days", now - timedelta(days=7), None),
        ("last_30_days", now - timedelta(days=30), None),
        ("all_time", None, None),
    ):
        totals = R.revenue_for_period(orders, start, end, basis)
        write_row("sales_summary", period=period, count=totals["order_count"], amount=totals["revenue"],
                  details=BASIS_LABEL[basis])

    pending_orders = sorted((o for o in orders if o["status"] == "pending"), key=lambda o: (o["created_at"], o["id"]))
    pending_by_customer: dict[str, list] = {}
    for order in pending_orders:
        if order.get("customer_username"):
            pending_by_customer.setdefault(order["customer_username"], []).append(order)

    write_row("outstanding", record="store_total", count=len(pending_orders), amount=R.outstanding_total(orders),
              details="total pending customer balance")
    write_row("payment_due_date", record="store", details=data.due_date or "not configured")

    by_customer: dict[str, dict] = {}
    for order in orders:
        username = order.get("customer_username")
        if not username:
            continue
        row = by_customer.setdefault(username, {"orders": 0, "paid_orders": 0, "paid_total": 0.0})
        row["orders"] += 1
        if order["status"] == "paid":
            row["paid_orders"] += 1
            row["paid_total"] += order["total"]
    for customer in sorted(data.customers, key=lambda c: c["username"]):
        username = customer["username"]
        pending = pending_by_customer.get(username, [])
        lifetime = by_customer.get(username, {"orders": 0, "paid_orders": 0, "paid_total": 0.0})
        write_row("customer_summary", record="lifetime", record_id=customer["id"], name=username,
                  count=lifetime["orders"], amount=money(lifetime["paid_total"]),
                  details=f"paid orders: {lifetime['paid_orders']}")
        write_row(
            "customer_balance", record="pending", record_id=customer["id"], name=username,
            count=len(pending), amount=money(sum(o["total"] for o in pending)),
            details="pending orders: " + "; ".join(
                f"#{o['id']} due {o['due_date'].isoformat() if o.get('due_date') else 'not set'}" for o in pending
            ),
        )

    for product in sorted(data.products, key=lambda p: (p["name"], p["id"])):
        unit_price = product.get("effective_price", product.get("price") or 0.0)
        stock = product.get("stock") or 0
        cost_price = product.get("cost_price")
        cost = (
            f"; cost price {cost_price}; value at cost {money(stock * cost_price)}"
            if cost_price is not None else "; cost price not set"
        )
        write_row("inventory", record="active" if product.get("is_active") else "inactive",
                  record_id=product["id"], name=product["name"], unit_price=unit_price, stock=stock,
                  stock_value=money(stock * unit_price),
                  details=f"category: {product.get('category_name') or ''}; value at current selling price{cost}")

    for product in R.low_stock_products(data.products):
        write_row("restock_needed", record="low_stock", record_id=product["id"], name=product["name"],
                  stock=product["stock"], details=f"threshold {product['low_stock_threshold']}")

    for period in ("month", "all"):
        start, end = R.period_bounds(period, now)
        report = R.margins_for_period(orders, start, end, basis)
        label = "all_time" if period == "all" else period
        for row in report["products"]:
            write_row("margins", period=label, record="product", name=row["product"], quantity=row["quantity"],
                      amount=row["margin"],
                      details=(f"revenue {row['revenue']}; cost {row['cost']}; margin "
                               f"{row['margin_pct'] if row['margin_pct'] is not None else '-'}%; "
                               f"units without cost {row['uncosted_quantity']}"))
        totals = report["totals"]
        write_row("margins", period=label, record="store_total", quantity=totals["quantity"],
                  amount=totals["margin"], details=f"revenue {totals['revenue']}; cost {totals['cost']}")

    for day in R.sales_by_day(orders, last_14_days, basis):
        write_row("daily_sales", period=day["day"], count=day["orders"], amount=day["revenue"],
                  details=BASIS_LABEL[basis])

    for period, start, end in (("today", today, today + timedelta(days=1)), ("week", week, next_week),
                               ("month", month, next_month)):
        for rank, customer in enumerate(R.top_customers_for_period(orders, start, 20, end, basis), 1):
            write_row("top_customers", period=period, record=f"rank_{rank}", name=customer["username"],
                      count=customer["orders"], amount=customer["spent"])
        for rank, product in enumerate(R.top_products_for_period(orders, start, 20, end, basis), 1):
            write_row("top_products", period=period, record=f"rank_{rank}", name=product["product"],
                      quantity=product["quantity"], amount=product["revenue"])
    for rank, product in enumerate(R.top_products_for_period(orders, None, 20, basis=basis), 1):
        write_row("top_products", period="all_time", record=f"rank_{rank}", name=product["product"],
                  quantity=product["quantity"], amount=product["revenue"])

    latest = R.last_payment(orders)
    if latest:
        write_row("last_payment", record="latest", record_id=latest["order_id"], name=latest["username"],
                  amount=latest["amount"], details=latest["paid_at"].isoformat())

    filename = f"kiosk-report-{now:%Y-%m-%d}.csv"
    return Response(
        content="﻿" + output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/shrinkage")
def shrinkage(request: Request, period: Literal["today", "week", "month", "all"] = "month"):
    start, end = R.period_bounds(period, utcnow())
    return R.shrinkage_report(load_adjustments(request, start, end), period)


@router.get("/reorder")
def reorder(
    request: Request,
    days: int = Query(default=28, ge=1, le=365),
    cover_days: int = Query(default=14, ge=1, le=180),
):
    data = load(request, products=True)
    return R.reorder_suggestions(data.orders, data.products, days, cover_days, utcnow())


@router.get("/reorder.csv")
def reorder_csv(
    request: Request,
    days: int = Query(default=28, ge=1, le=365),
    cover_days: int = Query(default=14, ge=1, le=180),
):
    data = load(request, products=True)
    report = R.reorder_suggestions(data.orders, data.products, days, cover_days, utcnow())
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "product", "category", "stock", "low_stock_threshold", f"sold_last_{days}_days",
        "per_day", "order_quantity", "unit_cost", "estimated_cost",
    ])
    for r in report["products"]:
        writer.writerow([
            csv_safe(r["product_name"]), csv_safe(r["category"]), r["stock"], r["low_stock_threshold"],
            r["sold"], r["per_day"], r["suggested"],
            "" if r["unit_cost"] is None else r["unit_cost"],
            "" if r["estimated_cost"] is None else r["estimated_cost"],
        ])
    writer.writerow(["TOTAL", "", "", "", "", "", report["totals"]["units"], "", report["totals"]["estimated_cost"]])
    filename = f"kiosk-reorder-{utcnow():%Y-%m-%d}.csv"
    return Response(
        content="﻿" + output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
