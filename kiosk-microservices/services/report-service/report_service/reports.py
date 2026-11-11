"""Pure report computations over the data loaded from the other services."""

import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal

from kiosk_common.money import money

Basis = Literal["sales", "paid"]
BASIS_LABEL = {"sales": "all sales incl. unpaid (credit)", "paid": "paid orders only"}


def basis_scope(order: dict, basis: str) -> tuple[bool, datetime | None]:
    """Whether a sales statistic counts this order, and the date it counts on.

    "sales": every order that is not cancelled, dated when it was bought.
    "paid": paid orders only, dated when they were paid (the cash view).
    """
    if basis == "paid":
        return order["status"] == "paid", order.get("completed_at") or order.get("created_at")
    return order["status"] != "cancelled", order.get("created_at")


def in_period(at: datetime | None, start: datetime | None, end: datetime | None) -> bool:
    if at is None:
        return False
    if start is not None and at < start:
        return False
    if end is not None and at >= end:
        return False
    return True


def counted_orders(orders: list[dict], start, end, basis: str) -> list[dict]:
    result = []
    for order in orders:
        counted, at = basis_scope(order, basis)
        if counted and in_period(at, start, end):
            result.append(order)
    return result


def revenue_for_period(orders: list[dict], start=None, end=None, basis: str = "sales") -> dict:
    rows = counted_orders(orders, start, end, basis)
    return {"order_count": len(rows), "revenue": money(sum(o["total"] for o in rows))}


def outstanding_total(orders: list[dict]) -> float:
    return money(sum(o["total"] for o in orders if o["status"] == "pending"))


def low_stock_products(products: list[dict]) -> list[dict]:
    """Active products at or below their own restock threshold, emptiest first."""
    rows = [
        p for p in products
        if p.get("is_active") and (p.get("stock") or 0) <= (p.get("low_stock_threshold") or 0)
    ]
    rows.sort(key=lambda p: (p.get("stock") or 0, p["name"]))
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "stock": p.get("stock") or 0,
            "low_stock_threshold": p.get("low_stock_threshold"),
            "price": p.get("price"),
            "special_price": p.get("special_price"),
            "is_weekly_special": p.get("is_weekly_special"),
            "special_active": p.get("special_active"),
            "cost_price": p.get("cost_price"),
        }
        for p in rows
    ]


def margins_for_period(orders: list[dict], start=None, end=None, basis: str = "sales") -> dict:
    """Sales per product with cost and margin; lines without a cost count toward revenue only."""
    agg: dict[str, dict] = {}
    for order in counted_orders(orders, start, end, basis):
        for item in order.get("items", []):
            row = agg.setdefault(
                item["product_name"],
                {"quantity": 0, "revenue": 0.0, "costed_revenue": 0.0, "cost": 0.0, "uncosted": 0},
            )
            line_revenue = item["unit_price"] * item["quantity"]
            row["quantity"] += item["quantity"]
            row["revenue"] += line_revenue
            if item.get("unit_cost") is not None:
                row["costed_revenue"] += line_revenue
                row["cost"] += item["unit_cost"] * item["quantity"]
            else:
                row["uncosted"] += item["quantity"]

    def margin_row(name, quantity, revenue, costed_revenue, cost, uncosted):
        margin = costed_revenue - cost
        return {
            "product": name,
            "quantity": int(quantity),
            "revenue": money(revenue),
            "cost": money(cost),
            "margin": money(margin),
            "margin_pct": round(margin / costed_revenue * 100, 1) if costed_revenue else None,
            "uncosted_quantity": int(uncosted),
        }

    products = [
        margin_row(name, r["quantity"], r["revenue"], r["costed_revenue"], r["cost"], r["uncosted"])
        for name, r in agg.items()
    ]
    products.sort(key=lambda r: (-r["margin"], -r["revenue"], r["product"]))
    totals = margin_row(
        None,
        sum(r["quantity"] for r in agg.values()),
        sum(r["revenue"] for r in agg.values()),
        sum(r["costed_revenue"] for r in agg.values()),
        sum(r["cost"] for r in agg.values()),
        sum(r["uncosted"] for r in agg.values()),
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
        return month, next_month_start(month)
    return None, None


def next_month_start(month: datetime) -> datetime:
    return month.replace(year=month.year + 1, month=1) if month.month == 12 else month.replace(month=month.month + 1)


def top_customers_for_period(orders, start, limit: int, end=None, basis: str = "sales") -> list[dict]:
    agg: dict[str, dict] = {}
    for order in counted_orders(orders, start, end, basis):
        if not order.get("customer_username"):
            continue
        row = agg.setdefault(order["customer_username"], {"orders": 0, "spent": 0.0})
        row["orders"] += 1
        row["spent"] += order["total"]
    rows = [{"username": u, "orders": r["orders"], "spent": money(r["spent"])} for u, r in agg.items()]
    rows.sort(key=lambda r: (-r["spent"], -r["orders"], r["username"]))
    return rows[:limit]


def top_products_for_period(orders, start, limit: int, end=None, basis: str = "sales") -> list[dict]:
    agg: dict[str, dict] = {}
    for order in counted_orders(orders, start, end, basis):
        for item in order.get("items", []):
            row = agg.setdefault(item["product_name"], {"quantity": 0, "revenue": 0.0})
            row["quantity"] += item["quantity"]
            row["revenue"] += item["unit_price"] * item["quantity"]
    rows = [{"product": p, "quantity": r["quantity"], "revenue": money(r["revenue"])} for p, r in agg.items()]
    rows.sort(key=lambda r: (-r["quantity"], -r["revenue"], r["product"]))
    return rows[:limit]


def sales_by_day(orders, since: datetime, basis: str) -> list[dict]:
    days: dict[str, dict] = {}
    for order in orders:
        counted, at = basis_scope(order, basis)
        if not counted or at is None or at < since:
            continue
        row = days.setdefault(at.date().isoformat(), {"orders": 0, "revenue": 0.0})
        row["orders"] += 1
        row["revenue"] += order["total"]
    return [{"day": d, "orders": r["orders"], "revenue": money(r["revenue"])} for d, r in sorted(days.items())]


def last_payment(orders) -> dict | None:
    paid = [o for o in orders if o["status"] == "paid" and o.get("customer_username")]
    if not paid:
        return None
    latest = max(paid, key=lambda o: (o.get("completed_at") or o["created_at"], o["id"]))
    return {
        "username": latest["customer_username"],
        "order_id": latest["id"],
        "amount": money(latest["total"]),
        "paid_at": latest.get("completed_at") or latest["created_at"],
    }


def shrinkage_report(adjustments: list[dict], period: str) -> dict:
    products: dict[str, dict] = {}
    by_reason: dict[str, int] = {}
    for adj in adjustments:
        if not adj["difference"]:
            continue
        row = products.setdefault(adj["product_name"], {
            "product_id": adj.get("product_id"), "product_name": adj["product_name"],
            "units_lost": 0, "units_found": 0, "value_lost": 0.0, "counts": 0,
        })
        row["counts"] += 1
        if adj["difference"] < 0:
            lost = -adj["difference"]
            row["units_lost"] += lost
            row["value_lost"] += lost * (adj.get("unit_cost") or 0)
            by_reason[adj["reason"]] = by_reason.get(adj["reason"], 0) + lost
        else:
            row["units_found"] += adj["difference"]
    rows = sorted(products.values(), key=lambda r: (-r["value_lost"], -r["units_lost"], r["product_name"]))
    for row in rows:
        row["value_lost"] = money(row["value_lost"])
    return {
        "period": period,
        "products": rows,
        "by_reason": by_reason,
        "totals": {
            "units_lost": sum(r["units_lost"] for r in rows),
            "units_found": sum(r["units_found"] for r in rows),
            "value_lost": money(sum(r["value_lost"] for r in rows)),
        },
    }


def reorder_suggestions(orders, products, days: int, cover_days: int, now: datetime) -> dict:
    """suggested = ceil(sold_per_day * cover_days) + low_stock_threshold - stock"""
    since = now - timedelta(days=days)
    sold: dict[int, int] = defaultdict(int)
    for order in orders:
        if order["status"] == "cancelled" or order["created_at"] < since:
            continue
        for item in order.get("items", []):
            if item.get("product_id") is not None:
                sold[item["product_id"]] += item["quantity"]
    rows = []
    for product in products:
        if not product.get("is_active"):
            continue
        units = int(sold.get(product["id"], 0))
        per_day = units / days
        threshold = product.get("low_stock_threshold") or 0
        stock = product.get("stock") or 0
        suggested = max(0, math.ceil(per_day * cover_days) + threshold - stock)
        if suggested == 0:
            continue
        cost = product.get("cost_price")
        rows.append({
            "product_id": product["id"],
            "product_name": product["name"],
            "category": product.get("category_name") or "",
            "stock": stock,
            "low_stock_threshold": threshold,
            "sold": units,
            "per_day": round(per_day, 2),
            "suggested": suggested,
            "unit_cost": cost,
            "estimated_cost": money(suggested * cost) if cost is not None else None,
        })
    rows.sort(key=lambda r: (-r["suggested"], r["product_name"]))
    return {
        "days": days,
        "cover_days": cover_days,
        "products": rows,
        "totals": {
            "units": sum(r["suggested"] for r in rows),
            "estimated_cost": money(sum(r["estimated_cost"] or 0 for r in rows)),
        },
    }
