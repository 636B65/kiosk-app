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
    r = client.get("/api/health", headers={"Origin": "http://localhost:8080"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8080"


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

    # Non-special products still use their normal price.
    r2 = client.post(
        "/api/orders",
        json={"customer_username": "special_tester", "items": [{"product_id": products[1]["id"], "quantity": 1}]},
    )
    assert r2.status_code == 201
    assert r2.json()["total"] == pytest.approx(products[1]["price"])
