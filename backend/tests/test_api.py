"""API tests for the Kiosk backend.

Run with:  python -m pytest backend/tests -v
Uses the FastAPI TestClient against a throwaway SQLite database.
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure the backend package is importable regardless of CWD.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Use a temporary DB for every test run.
DB = Path(os.environ.get("KIOSK_TEST_DB", "/tmp/kiosk-test.db")).resolve()
os.environ["DATABASE_PATH"] = str(DB)
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
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# Currency / pricing
# --------------------------------------------------------------------------- #
def test_products_have_no_image_url(products):
    for p in products:
        assert "image_url" not in p


def test_products_are_sek_priced(products):
    for p in products:
        assert isinstance(p["price"], (int, float))
        assert p["price"] >= 0


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


def test_balance_accumulates_case_insensitive(client, products):
    r1 = client.post(
        "/api/orders",
        json={"customer_username": "Alice", "items": [{"product_id": products[1]["id"], "quantity": 1}]},
    )
    assert r1.status_code == 201
    lookup = client.get("/api/customers/alice").json()
    assert lookup["customer"]["username"] == "alice"
    expected = products[0]["price"] * 2 + products[1]["price"]
    assert lookup["balance"] == pytest.approx(expected)
    assert len(lookup["orders"]) == 2


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


# --------------------------------------------------------------------------- #
# Customer stats
# --------------------------------------------------------------------------- #
def test_customer_stats(client):
    lookup = client.get("/api/customers/alice").json()
    stats = lookup["stats"]
    assert stats["orders"] == 2
    assert stats["items_bought"] == 3  # 2 + 1
    assert stats["top_item_qty"] >= 1
    assert stats["total_spent"] == pytest.approx(
        stats["balance"] + stats["total_paid"]
    )


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
    assert summ["pending_orders"] >= 2
    assert summ["today"]["revenue"] == 0  # nothing paid yet


def test_reset_payment_clears_balance(client, admin_headers):
    r = client.post("/api/customers/alice/reset-payment", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["settled"] >= 2
    lookup = client.get("/api/customers/alice").json()
    assert lookup["balance"] == pytest.approx(0)
    assert lookup["total_paid"] > 0


def test_reports_reflect_paid_after_reset(client, admin_headers):
    summ = client.get("/api/reports/summary", headers=admin_headers).json()
    assert summ["outstanding"] == pytest.approx(0)
    assert summ["today"]["revenue"] > 0
    top = client.get("/api/reports/top-products?limit=3", headers=admin_headers).json()
    assert len(top) <= 3


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
