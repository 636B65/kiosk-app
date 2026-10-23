"""API tests for the Kiosk backend.

Run with:  python -m pytest backend/tests -v
Uses the FastAPI TestClient against a throwaway SQLite database.
"""

import csv
import io
import os
import sys
import threading
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

# Ensure the backend package is importable regardless of CWD.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Use a temporary DB for every test run.
DB = Path(os.environ.get("KIOSK_TEST_DB", "/tmp/kiosk-test.db")).resolve()
os.environ["DATABASE_PATH"] = str(DB)
# Seed creates the admin account with ADMIN_PASSWORD (or a random password).
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "test-admin-password")
os.environ["ADMIN_PASSWORD"] = ADMIN_PASSWORD
try:
    DB.unlink()
except FileNotFoundError:
    pass


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def products(client):
    r = client.get("/api/products")
    assert r.status_code == 200
    data = r.json()
    assert len(data) > 0, "seed products should exist"
    return data


@pytest.fixture(scope="session")
def admin_headers(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# Currency / pricing
# --------------------------------------------------------------------------- #
def test_products_expose_optional_image_url(products):
    for p in products:
        assert "image_url" in p
        assert p["image_url"] is None or p["image_url"].startswith("/api/images/")


def test_products_are_sek_priced(products):
    for p in products:
        assert isinstance(p["price"], (int, float))
        assert p["price"] >= 0


def test_product_barcodes_support_multiple_scans_and_unique_lookup(
    client, admin_headers
):
    created = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Barcode Test Drink",
            "price": 2.5,
            "stock": 5,
            "barcodes": [" 00012345 ", "DRINK-A", "drink-a", ""],
        },
    )
    assert created.status_code == 201, created.text
    product = created.json()
    assert product["barcodes"] == ["00012345", "drink-a"]

    for barcode in ("00012345", "DRINK-A"):
        found = client.get(f"/api/products/barcode/{barcode}")
        assert found.status_code == 200
        assert found.json()["id"] == product["id"]

    duplicate = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Duplicate Barcode Test",
            "price": 1,
            "stock": 1,
            "barcodes": ["drink-a"],
        },
    )
    assert duplicate.status_code == 409

    updated = client.put(
        f"/api/products/{product['id']}",
        headers=admin_headers,
        json={"barcodes": ["NEW-CODE", "new-code"]},
    )
    assert updated.status_code == 200
    assert updated.json()["barcodes"] == ["new-code"]
    assert client.get("/api/products/barcode/00012345").status_code == 404
    assert client.get("/api/products/barcode/NEW-CODE").json()["id"] == product["id"]

    inactive = client.put(
        f"/api/products/{product['id']}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert inactive.status_code == 200
    assert client.get("/api/products/barcode/new-code").status_code == 404
    assert client.get("/api/products/barcode/not-found").status_code == 404
    assert client.post(
        "/api/products",
        json={"name": "Unauthorized", "price": 1, "stock": 1},
    ).status_code == 401


# --------------------------------------------------------------------------- #
# Customer checkout / tab model
# --------------------------------------------------------------------------- #
def test_checkout_creates_customer(client, products):
    r = client.post(
        "/api/orders",
        json={"customer_username": "alice", "items": [{"product_id": products[0]["id"], "quantity": 2}]},
    )
    assert r.status_code == 201
    order = r.json()
    assert order["status"] == "pending"
    assert order["customer_username"] == "alice"
    # no tax: total == subtotal == unit_price * qty
    assert order["total"] == pytest.approx(order["subtotal"])
    assert order["total"] == pytest.approx(products[0]["price"] * 2)


def test_balance_accumulates_case_insensitive(client, products, admin_headers):
    # alice still has an unpaid order from test_checkout_creates_customer; with
    # the payment due date already passed, a new purchase must be blocked
    # regardless of username casing.
    assert client.put(
        "/api/settings/payment_due_date",
        json={"key": "payment_due_date", "value": "2020-01-01"},
        headers=admin_headers,
    ).status_code == 200
    try:
        r = client.post(
            "/api/orders",
            json={"customer_username": "Alice", "items": [{"product_id": products[1]["id"], "quantity": 1}]},
        )
        assert r.status_code == 403
        assert "unpaid" in r.json()["detail"].lower()
        # no extra order or balance was created
        lookup = client.get("/api/customers/alice").json()
        assert lookup["customer"]["username"] == "alice"  # case-insensitive match
        assert len(lookup["orders"]) == 1
        assert lookup["balance"] == pytest.approx(products[0]["price"] * 2)
    finally:
        client.put(
            "/api/settings/payment_due_date",
            json={"key": "payment_due_date", "value": ""},
            headers=admin_headers,
        )


def test_checkout_requires_username(client, products):
    r = client.post("/api/orders", json={"items": [{"product_id": products[0]["id"], "quantity": 1}]})
    assert r.status_code == 422
    r = client.post(
        "/api/orders",
        json={"customer_username": "   ", "items": [{"product_id": products[0]["id"], "quantity": 1}]},
    )
    assert r.status_code == 400


def test_lookup_unknown_customer_404(client):
    assert client.get("/api/customers/nobody").status_code == 404


def test_customer_suggest_prefix(client):
    """Public autocomplete only returns matching usernames, capped."""
    # Existing customers from earlier tests: 'alice', 'special_tester', 'abuser'
    r = client.get("/api/customers/suggest?q=ali")
    assert r.status_code == 200
    assert "alice" in r.json()
    # case-insensitive
    r = client.get("/api/customers/suggest?q=ALI")
    assert "alice" in r.json()
    # no match -> empty, never leaks balances/history
    r = client.get("/api/customers/suggest?q=zzz")
    assert r.status_code == 200
    assert r.json() == []
    # empty query -> no dump
    assert client.get("/api/customers/suggest?q=").json() == []
    # limit honoured
    r = client.get("/api/customers/suggest?q=a&limit=1")
    assert len(r.json()) == 1


# --------------------------------------------------------------------------- #
# Security hardening
# --------------------------------------------------------------------------- #
def test_forged_token_with_known_secret_rejected(client):
    """A token signed with the old well-known secret must be rejected."""
    import base64
    import hashlib
    import hmac
    import json
    import time

    def b64url(data):
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    secret = "change-me-in-production"  # the historically hardcoded key
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64url(
        json.dumps({"sub": "admin", "exp": int(time.time()) + 3600}).encode()
    )
    msg = f"{header}.{payload}".encode()
    sig = b64url(hmac.new(secret.encode(), msg, hashlib.sha256).digest())
    forged = f"{header}.{payload}.{sig}"

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_secret_key_is_not_hardcoded(client):
    from config import settings

    assert settings.secret_key not in ("", "change-me-in-production")
    assert len(settings.secret_key) >= 32


def test_cors_blocks_foreign_origins(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert r.headers.get("access-control-allow-origin") is None
    r = client.get("/api/health", headers={"Origin": "https://localhost"})
    assert r.headers.get("access-control-allow-origin") == "https://localhost"


def test_login_rate_limited_after_failures(client):
    from routers import auth as auth_router

    for _ in range(5):
        r = client.post(
            "/api/auth/login", json={"username": "admin", "password": "wrong"}
        )
        assert r.status_code == 401
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert r.status_code == 429
    auth_router._failed_attempts.clear()


def test_rate_limiter_ignores_spoofed_xff(client):
    """The limiter keys on the last X-Forwarded-For hop (set by nginx), so a
    spoofed leading value must not reset the counter."""
    from routers import auth as auth_router

    auth_router._failed_attempts.clear()
    # 5 failures from a fixed real IP (appended last) -> lockout, even though
    # the client spoofs a different leading hop each time.
    for _ in range(5):
        r = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "nope"},
            headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.9"},
        )
        assert r.status_code == 401
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "nope"},
        headers={"X-Forwarded-For": "5.6.7.8, 203.0.113.9"},
    )
    assert r.status_code == 429
    auth_router._failed_attempts.clear()


def test_password_too_short_rejected(client, admin_headers):
    r = client.post(
        "/api/users",
        json={"username": "shortpass", "password": "short"},
        headers=admin_headers,
    )
    assert r.status_code == 422
    # updating a password that is too short is also rejected
    users = client.get("/api/users", headers=admin_headers).json()
    target = next(u for u in users if u["username"] == "admin")
    r = client.put(
        f"/api/users/{target['id']}",
        json={"password": "short"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_order_rejects_negative_and_zero_quantity(client, products):
    pid = products[0]["id"]
    stock_before = client.get(f"/api/products/{pid}").json()["stock"]
    r = client.post(
        "/api/orders",
        json={"customer_username": "abuser", "items": [{"product_id": pid, "quantity": -50}]},
    )
    assert r.status_code == 422
    r = client.post(
        "/api/orders",
        json={"customer_username": "abuser", "items": [{"product_id": pid, "quantity": 0}]},
    )
    assert r.status_code == 422
    # stock unchanged and no negative-balance customer was created
    assert client.get(f"/api/products/{pid}").json()["stock"] == stock_before
    assert client.get("/api/customers/abuser").status_code == 404


def test_order_rejects_excess_quantity_items(client, products):
    pid = products[0]["id"]
    items = [{"product_id": pid, "quantity": 1} for _ in range(60)]
    r = client.post(
        "/api/orders",
        json={"customer_username": "bigcart", "items": items},
    )
    assert r.status_code == 422


def test_order_stock_is_not_oversold_under_concurrency(client, admin_headers):
    from fastapi.testclient import TestClient
    from main import app

    pid = client.get("/api/products").json()[0]["id"]
    stock_before = client.get(f"/api/products/{pid}").json()["stock"]
    barrier = threading.Barrier(2)
    usernames = [f"race_user_{uuid.uuid4().hex}", f"race_user_{uuid.uuid4().hex}"]

    def buy_once(username: str):
        barrier.wait()
        with TestClient(app) as c:
            return c.post(
                "/api/orders",
                json={"customer_username": username, "items": [{"product_id": pid, "quantity": 1}]},
            )

    try:
        client.put(
            f"/api/products/{pid}",
            json={"stock": 1},
            headers=admin_headers,
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(buy_once, usernames))

        statuses = [r.status_code for r in results]
        assert statuses.count(201) == 1
        assert statuses.count(400) == 1
        assert client.get(f"/api/products/{pid}").json()["stock"] == 0
        for username in usernames:
            lookup = client.get(f"/api/customers/{username}")
            if lookup.status_code != 200:
                continue
            for order in lookup.json()["orders"]:
                if order["status"] == "pending":
                    r = client.patch(
                        f"/api/orders/{order['id']}/status?new_status=cancelled",
                        headers=admin_headers,
                    )
                    assert r.status_code == 200, r.text
    finally:
        client.put(
            f"/api/products/{pid}",
            json={"stock": stock_before},
            headers=admin_headers,
        )


def test_disabled_user_token_invalid(client, admin_headers):
    # Create a second admin whose token stays valid after the main user is
    # disabled (safe user cannot re-enable itself).
    r = client.post(
        "/api/users",
        json={"username": "backup_admin", "password": "backup-pass"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/api/auth/login", json={"username": "backup_admin", "password": "backup-pass"}
    )
    assert r.status_code == 200, r.text
    backup_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    users = client.get("/api/users", headers=admin_headers).json()
    admin_id = next(u["id"] for u in users if u["username"] == "admin")
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 200

    client.put(f"/api/users/{admin_id}", json={"is_active": False}, headers=backup_headers)
    # The disabled admin's token is now invalid.
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 401
    # Re-enable via the second admin so later tests keep working.
    client.put(f"/api/users/{admin_id}", json={"is_active": True}, headers=backup_headers)
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 200


def test_upload_rejects_spoofed_image(client, admin_headers, products):
    """Declared image/png but actual content is text -> rejected."""
    pid = products[0]["id"]
    r = client.post(
        f"/api/products/{pid}/image",
        headers=admin_headers,
        files={"file": ("x.png", b"<script>alert(1)</script>", "image/png")},
    )
    assert r.status_code in (400, 422)


# --------------------------------------------------------------------------- #
# Customer stats
# --------------------------------------------------------------------------- #
def test_customer_stats(client):
    lookup = client.get("/api/customers/alice").json()
    stats = lookup["stats"]
    assert stats["orders"] == 1
    assert stats["items_bought"] == 2
    assert stats["top_item_qty"] >= 1
    assert stats["total_spent"] == pytest.approx(
        stats["balance"] + stats["total_paid"]
    )
    assert stats["avg_orders_per_month"] >= 1
    assert stats["busiest_day"] in {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
    assert len(stats["orders_per_month"]) == 1
    assert stats["orders_per_month"][0]["orders"] == 1
    assert len(stats["orders_by_weekday"]) == 1
    assert stats["next_due_date"] is None  # no due date configured by default


# --------------------------------------------------------------------------- #
# Admin: customers, reports, payment flow
# --------------------------------------------------------------------------- #
def test_admin_list_customers(client, admin_headers):
    r = client.get("/api/customers", headers=admin_headers)
    assert r.status_code == 200
    assert any(c["username"] == "alice" for c in r.json())
    # requires auth
    assert client.get("/api/customers").status_code == 401


def test_admin_auth_required(client):
    assert client.get("/api/reports/summary").status_code == 401


def test_reports_outstanding_before_payment(client, admin_headers):
    summ = client.get("/api/reports/summary", headers=admin_headers).json()
    assert summ["outstanding"] > 0
    assert summ["pending_orders"] >= 1
    assert summ["today"]["revenue"] == 0  # nothing paid yet


def test_customer_insights_rank_paid_customers_and_show_latest_payment(
    client, products, admin_headers
):
    product = max(products, key=lambda item: item["stock"])
    created_orders = []
    for username, quantity in (("insight_runner_up", 4), ("insight_leader", 8)):
        response = client.post(
            "/api/orders",
            json={
                "customer_username": username,
                "items": [{"product_id": product["id"], "quantity": quantity}],
            },
        )
        assert response.status_code == 201
        order_id = response.json()["id"]
        paid = client.patch(
            f"/api/orders/{order_id}/status?new_status=paid",
            headers=admin_headers,
        )
        assert paid.status_code == 200
        created_orders.append(paid.json())

    insights = client.get(
        "/api/reports/customer-insights", headers=admin_headers
    ).json()
    for period in ("today", "week", "month"):
        ranked = insights[period]
        assert ranked[0]["username"] == "insight_leader"
        assert ranked[0]["orders"] == 1
        assert ranked[0]["spent"] > next(
            row["spent"] for row in ranked if row["username"] == "insight_runner_up"
        )
    for period in ("products_today", "products_week", "products_month"):
        assert insights[period][0]["product"] == product["name"]
        assert insights[period][0]["quantity"] >= 12

    assert insights["last_paid"]["username"] == "insight_leader"
    assert insights["last_paid"]["order_id"] == created_orders[-1]["id"]
    assert insights["last_paid"]["amount"] == pytest.approx(
        created_orders[-1]["total"]
    )
    stats = client.get("/api/customers/insight_leader").json()["stats"]
    assert stats["paid_orders"] == 1
    assert stats["pending_orders"] == 0
    assert stats["cancelled_orders"] == 0
    assert stats["last_paid_amount"] == pytest.approx(created_orders[-1]["total"])


def test_reset_payment_clears_balance(client, admin_headers):
    r = client.post("/api/customers/alice/reset-payment", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["settled"] == 1
    lookup = client.get("/api/customers/alice").json()
    assert lookup["balance"] == pytest.approx(0)
    assert lookup["total_paid"] > 0


def test_reports_reflect_paid_after_reset(client, admin_headers):
    summ = client.get("/api/reports/summary", headers=admin_headers).json()
    assert summ["outstanding"] == pytest.approx(0)
    assert summ["today"]["revenue"] > 0
    top = client.get("/api/reports/top-products?limit=3", headers=admin_headers).json()
    assert len(top) <= 3


def test_customer_insights_rank_by_payment_date(client, admin_headers):
    from database import SessionLocal
    from models import Order
    from timeutil import utcnow

    settled_late = f"settled_late_{uuid.uuid4().hex[:8]}"
    settled_early = f"settled_early_{uuid.uuid4().hex[:8]}"
    settled_control = f"settled_control_{uuid.uuid4().hex[:8]}"
    ranking_product = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": f"Ranking Test {uuid.uuid4().hex[:8]}",
            "price": 100,
            "stock": 10,
        },
    )
    assert ranking_product.status_code == 201, ranking_product.text
    order_ids = {}
    for username, quantity in (
        (settled_late, 3),
        (settled_early, 3),
        (settled_control, 1),
    ):
        response = client.post(
            "/api/orders",
            json={
                "customer_username": username,
                "items": [
                    {"product_id": ranking_product.json()["id"], "quantity": quantity}
                ],
            },
        )
        assert response.status_code == 201, response.text
        order_id = response.json()["id"]
        paid = client.patch(
            f"/api/orders/{order_id}/status?new_status=paid",
            headers=admin_headers,
        )
        assert paid.status_code == 200, paid.text
        order_ids[username] = order_id

    now = utcnow()
    with SessionLocal() as db:
        late_order = db.get(Order, order_ids[settled_late])
        early_order = db.get(Order, order_ids[settled_early])
        control_order = db.get(Order, order_ids[settled_control])
        late_order.created_at = now - timedelta(days=60)
        late_order.completed_at = now - timedelta(minutes=1)
        early_order.created_at = now
        early_order.completed_at = now - timedelta(days=60)
        control_order.completed_at = now - timedelta(minutes=2)
        db.commit()

    insights = client.get(
        "/api/reports/customer-insights?limit=20", headers=admin_headers
    ).json()
    for period in ("today", "week", "month"):
        usernames = [row["username"] for row in insights[period]]
        assert settled_late in usernames
        assert settled_early not in usernames
        assert usernames.index(settled_late) < usernames.index(settled_control)


def test_customer_self_service_payment_is_admin_enabled(
    client, products, admin_headers
):
    username = f"selfpay_{uuid.uuid4().hex[:8]}"
    order = client.post(
        "/api/orders",
        json={
            "customer_username": username,
            "items": [{"product_id": products[0]["id"], "quantity": 1}],
        },
    )
    assert order.status_code == 201, order.text
    path = f"/api/customers/{username}/self-mark-paid"
    setting_path = "/api/settings/customer_self_service_payment"
    try:
        disabled = client.post(path, json={})
        assert disabled.status_code == 403

        enabled = client.put(
            setting_path,
            headers=admin_headers,
            json={"key": "customer_self_service_payment", "value": "true"},
        )
        assert enabled.status_code == 200, enabled.text
        paid = client.post(path, json={})
        assert paid.status_code == 200, paid.text
        assert paid.json()["settled"] == 1

        history = client.get(f"/api/customers/{username}").json()
        assert history["balance"] == pytest.approx(0)
        assert history["orders"][0]["status"] == "paid"
    finally:
        client.put(
            setting_path,
            headers=admin_headers,
            json={"key": "customer_self_service_payment", "value": "false"},
        )


def test_reports_csv_exports_stock_balances_and_report_statistics(
    client, admin_headers
):
    product_name = '=HYPERLINK("https://example.test"), Item'
    product_response = client.post(
        "/api/products",
        headers=admin_headers,
        json={"name": product_name, "price": 3.25, "stock": 10},
    )
    assert product_response.status_code == 201, product_response.text
    product_id = product_response.json()["id"]

    for status in ("pending", "paid"):
        order_response = client.post(
            "/api/orders",
            json={
                "customer_username": "csv_export_customer",
                "items": [{"product_id": product_id, "quantity": 1}],
            },
        )
        assert order_response.status_code == 201, order_response.text
        if status == "paid":
            paid = client.patch(
                f"/api/orders/{order_response.json()['id']}/status?new_status=paid",
                headers=admin_headers,
            )
            assert paid.status_code == 200

    unauthorized = client.get("/api/reports/export.csv")
    assert unauthorized.status_code == 401

    response = client.get("/api/reports/export.csv", headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="kiosk-report-'
    )
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))

    customer_rows = [
        row for row in rows
        if row["section"] == "customer_balance"
        and row["name"] == "csv_export_customer"
    ]
    assert len(customer_rows) == 1
    assert customer_rows[0]["count"] == "1"
    assert float(customer_rows[0]["amount"]) == pytest.approx(3.25)

    inventory = next(
        row for row in rows
        if row["section"] == "inventory" and row["id"] == str(product_id)
    )
    assert inventory["name"] == "'" + product_name
    assert inventory["stock"] == "8"
    assert float(inventory["stock_value"]) == pytest.approx(26.0)
    assert any(row["section"] == "sales_summary" for row in rows)
    assert any(row["section"] == "customer_summary" for row in rows)
    assert any(row["section"] == "payment_due_date" for row in rows)
    assert any(
        row["section"] == "top_customers"
        and row["name"] == "csv_export_customer"
        for row in rows
    )
    assert any(
        row["section"] == "last_payment"
        and row["name"] == "csv_export_customer"
        for row in rows
    )


def test_order_items_endpoint(client, admin_headers):
    lookup = client.get("/api/customers/alice").json()
    order_id = lookup["orders"][0]["id"]
    items = client.get(f"/api/orders/{order_id}/items", headers=admin_headers)
    assert items.status_code == 200
    assert len(items.json()) >= 1


def test_mark_order_paid(client, products, admin_headers):
    # create a fresh pending order, then mark it paid
    r = client.post(
        "/api/orders",
        json={"customer_username": "alice", "items": [{"product_id": products[0]["id"], "quantity": 1}]},
    )
    assert r.status_code == 201
    order_id = r.json()["id"]
    paid_before = client.get("/api/customers/alice").json()["total_paid"]
    r = client.patch(
        f"/api/orders/{order_id}/status?new_status=paid", headers=admin_headers
    )
    assert r.status_code == 200
    after = client.get("/api/customers/alice").json()
    assert after["total_paid"] > paid_before
    assert after["balance"] == pytest.approx(0)
    # alice now has 2 orders / 3 items aggregate, and the per-month stats
    # reflect both (same calendar month).
    stats = after["stats"]
    assert stats["orders"] == 2
    assert stats["items_bought"] == 3
    assert stats["orders_per_month"][0]["orders"] == 2
    assert stats["avg_orders_per_month"] == 2.0


# --------------------------------------------------------------------------- #
# Product images
# --------------------------------------------------------------------------- #
def _sample_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"  # signature
        b"\x00\x00\x00\rIHDR"  # chunk header
        + (8).to_bytes(4, "big") + (8).to_bytes(4, "big") + (8).to_bytes(5, "big")
        + b"\x00\x00\x00\x00IDATA"  # start IDAT placeholder
    )


def test_upload_product_image(client, admin_headers, products):
    pid = products[0]["id"]
    r = client.post(
        f"/api/products/{pid}/image",
        headers=admin_headers,
        files={"file": ("test.png", _sample_png(), "image/png")},
    )
    assert r.status_code == 200, r.text
    url = r.json()["image_url"]
    assert url and url.startswith("/api/images/")

    # Image should be fetchable
    img = client.get(url)
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"

    # Requires auth
    unauth = client.post(
        f"/api/products/{pid}/image",
        files={"file": ("x.png", _sample_png(), "image/png")},
    )
    assert unauth.status_code in (401, 422)


def test_upload_rejects_bad_type(client, admin_headers, products):
    pid = products[0]["id"]
    r = client.post(
        f"/api/products/{pid}/image",
        headers=admin_headers,
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


def test_delete_product_image(client, admin_headers, products):
    pid = products[0]["id"]
    url = client.get(f"/api/products/{pid}").json()["image_url"]
    # ensure there is an image attached first
    if not url:
        client.post(
            f"/api/products/{pid}/image",
            headers=admin_headers,
            files={"file": ("t.png", _sample_png(), "image/png")},
        )
        url = client.get(f"/api/products/{pid}").json()["image_url"]
        assert url, "image should have been uploaded"
    r = client.delete(f"/api/products/{pid}/image", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["image_url"] is None


# --------------------------------------------------------------------------- #
# Weekly specials
# --------------------------------------------------------------------------- #
def test_product_weekly_special_fields(client, admin_headers, products):
    pid = products[0]["id"]
    r = client.put(
        f"/api/products/{pid}",
        headers=admin_headers,
        json={"is_weekly_special": True, "special_price": 1.5},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_weekly_special"] is True
    assert data["special_price"] == pytest.approx(1.5)


def test_order_uses_special_price_for_weekly_special(client, admin_headers, products):
    # Make the first product a weekly special priced below its normal price.
    pid = products[0]["id"]
    normal = products[0]["price"]
    client.put(
        f"/api/products/{pid}",
        headers=admin_headers,
        json={"is_weekly_special": True, "special_price": 1.0},
    )
    r = client.post(
        "/api/orders",
        json={"customer_username": "special_tester", "items": [{"product_id": pid, "quantity": 2}]},
    )
    assert r.status_code == 201
    order = r.json()
    assert order["total"] == pytest.approx(2.0)
    assert order["total"] != pytest.approx(normal * 2)

    # settle the tab through the admin reset flow before the next purchase
    assert client.post(
        "/api/customers/special_tester/reset-payment", headers=admin_headers
    ).status_code == 200

    # Non-special products still use their normal price.
    r2 = client.post(
        "/api/orders",
        json={"customer_username": "special_tester", "items": [{"product_id": products[1]["id"], "quantity": 1}]},
    )
    assert r2.status_code == 201
    assert r2.json()["total"] == pytest.approx(products[1]["price"])


# --------------------------------------------------------------------------- #
# Payment due dates / per-user statistics
# --------------------------------------------------------------------------- #
def _parse_api_dt(value):
    from datetime import datetime

    return datetime.fromisoformat(str(value).replace(" ", "T"))


def test_due_date_absent_by_default(client, products):
    """With no payment due date configured, orders get no due date at all."""
    assert client.get("/api/settings").json().get("payment_due_date", "") == ""
    r = client.post(
        "/api/orders",
        json={"customer_username": "due_tester", "items": [{"product_id": products[2]["id"], "quantity": 1}]},
    )
    assert r.status_code == 201
    assert r.json()["due_date"] is None


def test_tab_stays_open_without_due_date(client, products, admin_headers):
    """Regression for the v1.0.13 due-date change: checkout used to 403 on ANY
    unpaid order, so a customer could only ever buy once. Without a payment due
    date - or with one still days away - the tab must stay open and further
    purchases must be accepted; only an overdue balance blocks."""
    def buy():
        return client.post(
            "/api/orders",
            json={"customer_username": "tab_tester", "items": [{"product_id": products[2]["id"], "quantity": 1}]},
        )

    assert buy().status_code == 201
    assert buy().status_code == 201  # no due date configured -> tab stays open
    lookup = client.get("/api/customers/tab_tester").json()
    assert len(lookup["orders"]) == 2
    assert lookup["balance"] == pytest.approx(products[2]["price"] * 2)

    # a due date set days after the purchase keeps the tab open as well
    assert client.put(
        "/api/settings/payment_due_date",
        json={"key": "payment_due_date", "value": "2099-12-31"},
        headers=admin_headers,
    ).status_code == 200
    try:
        assert buy().status_code == 201
        lookup = client.get("/api/customers/tab_tester").json()
        assert len(lookup["orders"]) == 3
    finally:
        client.put(
            "/api/settings/payment_due_date",
            json={"key": "payment_due_date", "value": ""},
            headers=admin_headers,
        )


def test_checkout_blocked_until_marked_paid(client, products, admin_headers):
    """Once the payment due date has passed, a user with an unpaid order cannot
    buy again until the staff settles their balance."""
    assert client.put(
        "/api/settings/payment_due_date",
        json={"key": "payment_due_date", "value": "2020-01-01"},
        headers=admin_headers,
    ).status_code == 200
    try:
        r = client.post(
            "/api/orders",
            json={"customer_username": "blocked_tester", "items": [{"product_id": products[2]["id"], "quantity": 1}]},
        )
        assert r.status_code == 201

        r = client.post(
            "/api/orders",
            json={"customer_username": "blocked_tester", "items": [{"product_id": products[2]["id"], "quantity": 1}]},
        )
        assert r.status_code == 403
        assert "mark it as paid" in r.json()["detail"]

        # mark paid -> purchase allowed again
        assert client.post(
            "/api/customers/blocked_tester/reset-payment", headers=admin_headers
        ).status_code == 200
        r = client.post(
            "/api/orders",
            json={"customer_username": "blocked_tester", "items": [{"product_id": products[2]["id"], "quantity": 1}]},
        )
        assert r.status_code == 201
    finally:
        client.put(
            "/api/settings/payment_due_date",
            json={"key": "payment_due_date", "value": ""},
            headers=admin_headers,
        )


def test_cancel_preserves_previous_state(client, products):
    """Cancelling an order removes it from the outstanding balance."""
    r = client.post(
        "/api/orders",
        json={"customer_username": "cancel_tester", "items": [{"product_id": products[2]["id"], "quantity": 1}]},
    )
    assert r.status_code == 201
    order_id = r.json()["id"]
    # admin cancels the pending order, releasing the block
    login = client.post(
        "/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    r = client.patch(
        f"/api/orders/{order_id}/status?new_status=cancelled", headers=headers
    )
    assert r.status_code == 200
    r = client.post(
        "/api/orders",
        json={"customer_username": "cancel_tester", "items": [{"product_id": products[2]["id"], "quantity": 1}]},
    )
    assert r.status_code == 201
    assert client.get("/api/customers/cancel_tester").json()["balance"] == pytest.approx(
        products[2]["price"]
    )


def test_payment_due_date_setting_honored(client, admin_headers, products):
    """Setting a payment due date stamps it on new orders and is exposed as the
    customer's next due date; clearing it re-enables "no end date"."""
    from datetime import datetime

    assert client.put(
        "/api/settings/payment_due_date",
        json={"key": "payment_due_date", "value": "2026-10-15"},
        headers=admin_headers,
    ).status_code == 200
    try:
        r = client.post(
            "/api/orders",
            json={"customer_username": "duedate_tester", "items": [{"product_id": products[2]["id"], "quantity": 1}]},
        )
        assert r.status_code == 201
        assert _parse_api_dt(r.json()["due_date"]) == datetime(2026, 10, 15, 23, 59, 59)
        stats = client.get("/api/customers/duedate_tester").json()["stats"]
        assert _parse_api_dt(stats["next_due_date"]) == datetime(2026, 10, 15, 23, 59, 59)
    finally:
        client.put(
            "/api/settings/payment_due_date",
            json={"key": "payment_due_date", "value": ""},
            headers=admin_headers,
        )


def test_customer_monthly_and_weekday_stats(client):
    """special_tester has two orders in the same month -> aggregated stats."""
    lookup = client.get("/api/customers/special_tester").json()
    stats = lookup["stats"]
    assert stats["orders"] == 2
    assert stats["avg_orders_per_month"] == 2.0
    assert {m["month"] for m in stats["orders_per_month"]} == {
        lookup["orders"][0]["created_at"][:7]
    }
    assert stats["orders_per_month"][0]["orders"] == 2
    assert stats["orders_by_weekday"], "weekday aggregation should be filled"
    assert sum(d["orders"] for d in stats["orders_by_weekday"]) == 2
    assert stats["busiest_day"] == stats["orders_by_weekday"][0]["day"]
    assert stats["next_due_date"] is None  # no end date by default


def test_summary_exposes_next_due_date(client, admin_headers):
    summ = client.get("/api/reports/summary", headers=admin_headers).json()
    assert "next_due_date" in summ
    assert summ["next_due_date"] is None  # no due date configured by default
    assert "due_day" not in summ
    assert client.get("/api/reports/summary").status_code == 401  # still protected


# --------------------------------------------------------------------------- #
# Purchase prices, restocks, low-stock alerts and margins
# --------------------------------------------------------------------------- #
def _new_product(client, admin_headers, **fields):
    payload = {
        "name": f"Feature {uuid.uuid4().hex[:8]}",
        "price": 4.0,
        "stock": 2,
        "low_stock_threshold": 3,
        **fields,
    }
    r = client.post("/api/products", json=payload, headers=admin_headers)
    assert r.status_code == 201, r.text
    return r.json()


def _buy(client, username, product_id, quantity=1):
    r = client.post(
        "/api/orders",
        json={
            "customer_username": username,
            "items": [{"product_id": product_id, "quantity": quantity}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_seeded_settings_include_idle_and_backup_defaults(client):
    settings = client.get("/api/settings").json()
    assert settings["kiosk_idle_seconds"] == "90"
    assert settings["backup_interval_hours"] == "24"
    assert settings["backup_keep"] == "7"


def test_cost_price_is_only_visible_to_admins(client, admin_headers):
    product = _new_product(client, admin_headers, cost_price=1.5, barcodes=["cost-secret-1"])
    assert product["cost_price"] == 1.5

    public = {p["id"]: p for p in client.get("/api/products").json()}
    assert public[product["id"]]["cost_price"] is None
    assert all(p["cost_price"] is None for p in public.values())
    assert client.get(f"/api/products/{product['id']}").json()["cost_price"] is None
    assert client.get("/api/products/barcode/cost-secret-1").json()["cost_price"] is None
    # An invalid token is treated as anonymous, not as an error.
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.get("/api/products", headers=bad).status_code == 200

    admin = {p["id"]: p for p in client.get("/api/products", headers=admin_headers).json()}
    assert admin[product["id"]]["cost_price"] == 1.5
    seeded = [p for p in admin.values() if p["name"] == "Wireless Mouse"]
    assert seeded and seeded[0]["cost_price"] is not None


def test_low_stock_uses_each_products_threshold(client, admin_headers):
    low = _new_product(client, admin_headers, stock=3, low_stock_threshold=3)
    high = _new_product(client, admin_headers, stock=4, low_stock_threshold=3)
    custom = _new_product(client, admin_headers, stock=20, low_stock_threshold=25)
    summary = client.get("/api/reports/summary", headers=admin_headers).json()
    alerts = {p["id"]: p for p in summary["low_stock_products"]}
    assert low["id"] in alerts
    assert alerts[low["id"]]["low_stock_threshold"] == 3
    assert high["id"] not in alerts
    assert custom["id"] in alerts
    stocks = [p["stock"] for p in summary["low_stock_products"]]
    assert stocks == sorted(stocks)

    r = client.put(
        f"/api/products/{custom['id']}", json={"is_active": False}, headers=admin_headers
    )
    assert r.status_code == 200
    summary = client.get("/api/reports/summary", headers=admin_headers).json()
    assert custom["id"] not in {p["id"] for p in summary["low_stock_products"]}
    assert client.post(
        "/api/products", json={"name": "Bad", "low_stock_threshold": -1}, headers=admin_headers
    ).status_code == 422


def test_restock_adds_stock_logs_delivery_and_updates_cost(client, admin_headers):
    product = _new_product(client, admin_headers, stock=2, low_stock_threshold=3)
    path = f"/api/products/{product['id']}/restock"

    assert client.post(path, json={"quantity": 5}).status_code == 401
    assert client.post(path, json={"quantity": 0}, headers=admin_headers).status_code == 422
    assert client.post(
        path, json={"quantity": 1, "unit_cost": -1}, headers=admin_headers
    ).status_code == 422
    assert client.post(
        "/api/products/999999/restock", json={"quantity": 1}, headers=admin_headers
    ).status_code == 404

    r = client.post(
        path,
        json={"quantity": 10, "unit_cost": 2.5, "note": "  weekly delivery  "},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    restock = r.json()
    assert restock["quantity"] == 10
    assert restock["unit_cost"] == 2.5
    assert restock["stock_after"] == 12
    assert restock["note"] == "weekly delivery"
    assert restock["created_by"] == "admin"

    # A delivery without a price keeps the last known purchase price.
    r = client.post(path, json={"quantity": 3}, headers=admin_headers)
    assert r.status_code == 201
    assert r.json()["stock_after"] == 15

    updated = client.get(f"/api/products/{product['id']}", headers=admin_headers).json()
    assert updated["stock"] == 15
    assert updated["cost_price"] == 2.5
    summary = client.get("/api/reports/summary", headers=admin_headers).json()
    assert product["id"] not in {p["id"] for p in summary["low_stock_products"]}

    history = client.get(
        f"/api/products/{product['id']}/restocks", headers=admin_headers
    ).json()
    assert [h["quantity"] for h in history] == [3, 10]
    recent = client.get("/api/restocks?limit=5", headers=admin_headers).json()
    assert recent[0]["product_id"] == product["id"]
    assert client.get("/api/restocks").status_code == 401

    entries = client.get(
        "/api/audit?action=product.restock", headers=admin_headers
    ).json()
    assert entries[0]["entity_id"] == str(product["id"])
    assert entries[0]["actor"] == "admin"
    assert "+3" in entries[0]["details"]


def test_orders_snapshot_cost_for_margin_report(client, admin_headers):
    product = _new_product(client, admin_headers, price=5.0, stock=20, cost_price=2.0)
    uncosted = _new_product(client, admin_headers, price=3.0, stock=20)
    order = _buy(client, "margin_tester", product["id"], 2)
    other = _buy(client, "margin_tester", uncosted["id"], 1)
    pending = _buy(client, "margin_tester", product["id"], 1)
    for o in (order, other):
        assert client.patch(
            f"/api/orders/{o['id']}/status?new_status=paid", headers=admin_headers
        ).status_code == 200

    # Changing the purchase price later must not rewrite past margins.
    client.put(f"/api/products/{product['id']}", json={"cost_price": 4.5}, headers=admin_headers)

    report = client.get("/api/reports/margins?period=all", headers=admin_headers).json()
    rows = {r["product"]: r for r in report["products"]}
    row = rows[product["name"]]
    assert row["quantity"] == 2  # the pending order is not counted
    assert row["revenue"] == 10.0
    assert row["cost"] == 4.0
    assert row["margin"] == 6.0
    assert row["margin_pct"] == 60.0
    assert row["uncosted_quantity"] == 0
    no_cost = rows[uncosted["name"]]
    assert no_cost["margin_pct"] is None
    assert no_cost["uncosted_quantity"] == 1
    assert report["totals"]["revenue"] >= 13.0

    month = client.get("/api/reports/margins?period=month", headers=admin_headers).json()
    assert product["name"] in {r["product"] for r in month["products"]}
    assert client.get("/api/reports/margins?period=year", headers=admin_headers).status_code == 422
    assert client.get("/api/reports/margins").status_code == 401
    summary = client.get("/api/reports/summary", headers=admin_headers).json()
    assert summary["margin_month"]["margin"] >= 6.0

    # Unit cost stays private: order lines in the public lookup do not expose it.
    lookup = client.get("/api/customers/margin_tester").json()
    assert all("unit_cost" not in item for o in lookup["orders"] for item in o["items"])
    assert pending["status"] == "pending"

    r = client.get("/api/reports/export.csv", headers=admin_headers)
    rows = list(csv.DictReader(io.StringIO(r.text.lstrip("﻿"))))
    margins = [x for x in rows if x["section"] == "margins" and x["name"] == product["name"]]
    assert {x["period"] for x in margins} == {"month", "all_time"}
    assert all(float(x["amount"]) == 6.0 for x in margins)
    assert any(x["section"] == "margins" and x["record"] == "store_total" for x in rows)
    inventory = [x for x in rows if x["section"] == "inventory" and x["name"] == product["name"]]
    assert "cost price 4.5" in inventory[0]["details"]
    assert any(x["section"] == "restock_needed" for x in rows)


# --------------------------------------------------------------------------- #
# Time-limited specials
# --------------------------------------------------------------------------- #
def test_special_follows_its_schedule(client, admin_headers):
    from timeutil import utcnow

    today = utcnow().date()
    tomorrow = (today + timedelta(days=1)).isoformat()
    yesterday = (today - timedelta(days=1)).isoformat()
    product = _new_product(
        client,
        admin_headers,
        price=10.0,
        stock=10,
        is_weekly_special=True,
        special_price=6.0,
        special_starts_on=tomorrow,
    )
    assert product["special_active"] is False
    assert _buy(client, "schedule_tester", product["id"])["total"] == 10.0

    r = client.put(
        f"/api/products/{product['id']}",
        json={"special_starts_on": yesterday, "special_ends_on": today.isoformat()},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["special_active"] is True
    public = {p["id"]: p for p in client.get("/api/products").json()}
    assert public[product["id"]]["special_active"] is True
    assert _buy(client, "schedule_tester", product["id"])["total"] == 6.0

    r = client.put(
        f"/api/products/{product['id']}",
        json={"special_ends_on": yesterday},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["special_active"] is False

    # An end before the start is rejected, also when only one side changes.
    assert client.put(
        f"/api/products/{product['id']}",
        json={"special_starts_on": tomorrow, "special_ends_on": yesterday},
        headers=admin_headers,
    ).status_code == 422
    assert client.put(
        f"/api/products/{product['id']}",
        json={"special_starts_on": tomorrow},
        headers=admin_headers,
    ).status_code == 422
    unchanged = client.get(f"/api/products/{product['id']}").json()
    assert unchanged["special_starts_on"] == yesterday
    assert client.post(
        "/api/products",
        json={"name": "Bad window", "special_starts_on": tomorrow, "special_ends_on": yesterday},
        headers=admin_headers,
    ).status_code == 422

    # Clearing both dates makes the special open-ended again.
    r = client.put(
        f"/api/products/{product['id']}",
        json={"special_starts_on": None, "special_ends_on": None},
        headers=admin_headers,
    )
    assert r.json()["special_active"] is True


# --------------------------------------------------------------------------- #
# Audit log
# --------------------------------------------------------------------------- #
def test_payment_and_admin_changes_are_audited(client, admin_headers):
    product = _new_product(client, admin_headers, price=2.0, stock=10)
    first = _buy(client, "audit_tester", product["id"])
    second = _buy(client, "audit_tester", product["id"])

    assert client.get("/api/audit").status_code == 401

    client.patch(f"/api/orders/{first['id']}/status?new_status=cancelled", headers=admin_headers)
    entry = client.get("/api/audit?action=order.", headers=admin_headers).json()[0]
    assert entry["action"] == "order.cancelled"
    assert entry["entity_id"] == str(first["id"])
    assert "pending -> cancelled" in entry["details"]
    assert "stock restored" in entry["details"]

    client.post("/api/customers/audit_tester/reset-payment", headers=admin_headers)
    entry = client.get("/api/audit?action=customer.", headers=admin_headers).json()[0]
    assert entry["action"] == "customer.reset_payment"
    assert entry["actor"] == "admin"
    assert f"#{second['id']}" in entry["details"]

    # Nothing pending -> nothing to record.
    before = len(client.get("/api/audit?action=customer.", headers=admin_headers).json())
    client.post("/api/customers/audit_tester/reset-payment", headers=admin_headers)
    assert len(client.get("/api/audit?action=customer.", headers=admin_headers).json()) == before

    _buy(client, "audit_tester", product["id"])
    client.put(
        "/api/settings/customer_self_service_payment",
        json={"key": "customer_self_service_payment", "value": "true"},
        headers=admin_headers,
    )
    try:
        assert client.post("/api/customers/audit_tester/self-mark-paid").status_code == 200
    finally:
        client.put(
            "/api/settings/customer_self_service_payment",
            json={"key": "customer_self_service_payment", "value": "false"},
            headers=admin_headers,
        )
    entry = client.get("/api/audit?action=customer.", headers=admin_headers).json()[0]
    assert entry["action"] == "customer.self_mark_paid"
    assert entry["actor"] == "kiosk"

    settings_entries = client.get("/api/audit?action=settings.", headers=admin_headers).json()
    assert settings_entries[0]["entity_id"] == "customer_self_service_payment"
    assert settings_entries[0]["details"] == "customer_self_service_payment: true -> false"
    # Saving an unchanged value is not logged.
    client.put(
        "/api/settings/customer_self_service_payment",
        json={"key": "customer_self_service_payment", "value": "false"},
        headers=admin_headers,
    )
    assert len(client.get("/api/audit?action=settings.", headers=admin_headers).json()) == len(
        settings_entries
    )

    client.put(f"/api/products/{product['id']}", json={"price": 2.5}, headers=admin_headers)
    entry = client.get("/api/audit?action=product.update", headers=admin_headers).json()[0]
    assert "price: 2.0 -> 2.5" in entry["details"]

    r = client.post(
        "/api/users",
        json={"username": "audited_user", "password": "audited-password"},
        headers=admin_headers,
    )
    user_id = r.json()["id"]
    client.put(f"/api/users/{user_id}", json={"password": "another-password"}, headers=admin_headers)
    client.delete(f"/api/users/{user_id}", headers=admin_headers)
    actions = [e["action"] for e in client.get("/api/audit?action=user.", headers=admin_headers).json()]
    assert actions[:3] == ["user.delete", "user.update", "user.create"]
    log = client.get("/api/audit?limit=1000", headers=admin_headers).json()
    assert all("another-password" not in e["details"] for e in log)
    assert len(client.get("/api/audit?limit=2", headers=admin_headers).json()) == 2


# --------------------------------------------------------------------------- #
# Buy again (favorites)
# --------------------------------------------------------------------------- #
def test_lookup_lists_most_bought_products_as_favorites(client, admin_headers):
    a = _new_product(client, admin_headers, name=f"Fav A {uuid.uuid4().hex[:6]}", stock=50)
    b = _new_product(client, admin_headers, name=f"Fav B {uuid.uuid4().hex[:6]}", stock=50)
    c = _new_product(client, admin_headers, name=f"Fav C {uuid.uuid4().hex[:6]}", stock=50)
    gone = _new_product(client, admin_headers, name=f"Fav D {uuid.uuid4().hex[:6]}", stock=50)
    _buy(client, "favorite_tester", a["id"], 3)
    _buy(client, "favorite_tester", b["id"], 1)
    _buy(client, "favorite_tester", gone["id"], 5)
    cancelled = _buy(client, "favorite_tester", c["id"], 9)
    client.patch(
        f"/api/orders/{cancelled['id']}/status?new_status=cancelled", headers=admin_headers
    )
    client.put(f"/api/products/{gone['id']}", json={"is_active": False}, headers=admin_headers)

    favorites = client.get("/api/customers/favorite_tester").json()["favorites"]
    assert [f["product_id"] for f in favorites] == [a["id"], b["id"]]
    assert favorites[0] == {"product_id": a["id"], "name": a["name"], "quantity": 3}

    for i in range(6):
        p = _new_product(client, admin_headers, name=f"Fav many {i} {uuid.uuid4().hex[:6]}", stock=5)
        _buy(client, "favorite_tester", p["id"])
    assert len(client.get("/api/customers/favorite_tester").json()["favorites"]) == 5


# --------------------------------------------------------------------------- #
# Backups and system status
# --------------------------------------------------------------------------- #
def test_backups_create_list_download_and_prune(client, admin_headers):
    import backups
    from database import engine

    assert client.post("/api/system/backups").status_code == 401
    client.put(
        "/api/settings/backup_keep", json={"key": "backup_keep", "value": "2"}, headers=admin_headers
    )
    try:
        names = []
        for _ in range(3):
            r = client.post("/api/system/backups", headers=admin_headers)
            assert r.status_code == 201, r.text
            names.append(r.json()["name"])
        assert len(set(names)) == 3

        info = client.get("/api/system/backups", headers=admin_headers).json()
        assert info["supported"] is True
        assert info["keep"] == 2
        assert info["count"] == 2
        assert [item["name"] for item in info["items"]] == [names[2], names[1]]
        assert info["last_backup_at"] is not None

        r = client.get(f"/api/system/backups/{names[2]}", headers=admin_headers)
        assert r.status_code == 200
        assert r.content.startswith(b"SQLite format 3")
        assert client.get(f"/api/system/backups/{names[0]}", headers=admin_headers).status_code == 404
        assert client.get("/api/system/backups/..%2Fkiosk.db", headers=admin_headers).status_code == 404
        assert client.get("/api/system/backups/kiosk.db", headers=admin_headers).status_code == 404
        assert client.get(f"/api/system/backups/{names[2]}").status_code == 401

        actions = [e["action"] for e in client.get("/api/audit?action=backup.", headers=admin_headers).json()]
        assert actions[0] == "backup.download"
        assert actions.count("backup.create") == 3

        # The scheduler only acts when a backup is due.
        scheduler = backups.BackupScheduler(engine, lambda: next(_session()))
        assert scheduler.run_once() is None  # a backup was just taken
        assert backups.backup_due(engine, 0) is False
    finally:
        client.put(
            "/api/settings/backup_keep", json={"key": "backup_keep", "value": "7"}, headers=admin_headers
        )
        for item in backups.list_backups(engine):
            os.remove(os.path.join(backups.backup_dir(engine), item["name"]))


def _session():
    from database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_backup_scheduler_takes_a_backup_when_none_exists(client, admin_headers):
    import backups
    from database import SessionLocal, engine

    scheduler = backups.BackupScheduler(engine, SessionLocal)
    try:
        assert backups.list_backups(engine) == []
        result = scheduler.run_once()
        assert result is not None
        assert [b["name"] for b in backups.list_backups(engine)] == [result["name"]]
        assert scheduler.run_once() is None
    finally:
        for item in backups.list_backups(engine):
            os.remove(os.path.join(backups.backup_dir(engine), item["name"]))


def test_system_status_reports_health(client, admin_headers):
    assert client.get("/api/system/status").status_code == 401
    status = client.get("/api/system/status", headers=admin_headers).json()
    assert status["version"] == os.environ.get("APP_VERSION", "dev")
    assert status["database"]["engine"] == "sqlite"
    assert status["database"]["size_bytes"] > 0
    assert status["uptime_seconds"] >= 0
    assert status["counts"]["products"] >= status["counts"]["active_products"] > 0
    assert status["counts"]["low_stock_products"] >= 1
    assert status["counts"]["users"] >= 1
    assert status["backups"]["supported"] is True
    assert status["backups"]["interval_hours"] == 24
    assert status["last_activity"]["actor"]


def test_release_info_reads_build_file_and_env_wins(tmp_path, monkeypatch):
    from routers import system

    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.setattr(system, "RELEASE_FILE", str(tmp_path / "missing.json"))
    assert system.release_info() == {"version": "dev", "commit": ""}

    release = tmp_path / "release.json"
    release.write_text('{"version": "1.2.3", "commit": "abc123"}\n')
    monkeypatch.setattr(system, "RELEASE_FILE", str(release))
    assert system.release_info() == {"version": "1.2.3", "commit": "abc123"}

    monkeypatch.setenv("APP_VERSION", "9.9.9")
    assert system.release_info() == {"version": "9.9.9", "commit": "abc123"}

    release.write_text("not json")
    monkeypatch.delenv("APP_VERSION")
    assert system.release_info() == {"version": "dev", "commit": ""}
