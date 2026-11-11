from datetime import datetime

from report_service import reports as R


def order(id, status, total, created, completed=None, items=()):
    return {
        "id": id, "status": status, "total": total, "customer_username": "u",
        "created_at": created, "completed_at": completed, "items": list(items),
    }


ORDERS = [
    order(1, "pending", 10.0, datetime(2026, 1, 1, 10), items=[{"product_name": "A", "quantity": 2, "unit_price": 5.0, "unit_cost": 3.0, "product_id": 1}]),
    order(2, "paid", 4.0, datetime(2026, 1, 2, 10), datetime(2026, 1, 5, 10), items=[{"product_name": "B", "quantity": 1, "unit_price": 4.0, "unit_cost": None, "product_id": 2}]),
    order(3, "cancelled", 99.0, datetime(2026, 1, 3, 10), items=[{"product_name": "A", "quantity": 9, "unit_price": 11.0, "unit_cost": 3.0, "product_id": 1}]),
]


def test_sales_basis_counts_unpaid_but_not_cancelled():
    assert R.revenue_for_period(ORDERS, basis="sales") == {"order_count": 2, "revenue": 14.0}
    assert R.revenue_for_period(ORDERS, basis="paid") == {"order_count": 1, "revenue": 4.0}


def test_paid_basis_dates_by_completed_at():
    start, end = datetime(2026, 1, 4), datetime(2026, 1, 6)
    assert R.revenue_for_period(ORDERS, start, end, "paid")["order_count"] == 1
    assert R.revenue_for_period(ORDERS, start, end, "sales")["order_count"] == 0


def test_margins_leave_uncosted_lines_out_of_the_margin():
    report = R.margins_for_period(ORDERS)
    totals = report["totals"]
    assert totals == {"quantity": 3, "revenue": 14.0, "cost": 6.0, "margin": 4.0, "margin_pct": 40.0, "uncosted_quantity": 1}
    assert [p["product"] for p in report["products"]] == ["A", "B"]


def test_outstanding_and_last_payment():
    assert R.outstanding_total(ORDERS) == 10.0
    assert R.last_payment(ORDERS)["order_id"] == 2


def test_reorder_suggestion_formula():
    products = [{"id": 1, "name": "A", "is_active": True, "stock": 1, "low_stock_threshold": 5, "cost_price": 3.0, "category_name": "x"}]
    now = datetime(2026, 1, 10)
    report = R.reorder_suggestions(ORDERS, products, days=28, cover_days=14, now=now)
    # 2 sold in 28 days -> 1 per 14 days; + threshold 5 - stock 1 = 5
    assert report["products"][0]["suggested"] == 5
    assert report["totals"]["estimated_cost"] == 15.0


def test_period_bounds_month_rollover():
    start, end = R.period_bounds("month", datetime(2026, 12, 15, 9))
    assert (start, end) == (datetime(2026, 12, 1), datetime(2027, 1, 1))
