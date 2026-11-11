"""Business rules of the kiosk, exercised across the services through the gateway.

The tests share one stack (session scope) and build on each other in order,
like the monolith's API suite did.
"""

import io
import tarfile
import threading
from datetime import date, timedelta

import jwt
import pytest

from tests.integration.conftest import ADMIN_PASSWORD, SECRET_KEY

OVERDUE_DETAIL = (
    "The payment due date has passed and your previous order is still unpaid. "
    "Ask the staff to mark it as paid before you can buy again."
)


def product_by_name(client, name, headers=None):
    products = client.get("/api/products?active_only=false", headers=headers).json()
    return next(p for p in products if p["name"] == name)


def set_setting(client, admin_headers, key, value):
    response = client.put(f"/api/settings/{key}", json={"key": key, "value": value}, headers=admin_headers)
    assert response.status_code == 200, response.text


# ---- checkout -----------------------------------------------------------------


def test_checkout_creates_a_pending_order_and_decrements_stock(client, stack):
    cola = product_by_name(client, "Cola")
    chips = product_by_name(client, "Potato Chips")
    response = client.post(
        "/api/orders",
        json={"customer_username": "  Alice ", "items": [{"product_id": cola["id"], "quantity": 2},
                                                           {"product_id": chips["id"], "quantity": 1}]},
    )
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["status"] == "pending"
    assert order["customer_username"] == "alice"
    assert order["total"] == round(2 * cola["price"] + chips["price"], 2)
    assert order["due_date"] is None
    assert product_by_name(client, "Cola")["stock"] == cola["stock"] - 2
    assert product_by_name(client, "Potato Chips")["stock"] == chips["stock"] - 1


def test_insufficient_stock_rolls_back_every_line(client):
    cola = product_by_name(client, "Cola")
    earbuds = product_by_name(client, "Bluetooth Earbuds")
    response = client.post(
        "/api/orders",
        json={"customer_username": "alice", "items": [
            {"product_id": cola["id"], "quantity": 1},
            {"product_id": earbuds["id"], "quantity": earbuds["stock"] + 1},
        ]},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == f"Insufficient stock for 'Bluetooth Earbuds' ({earbuds['stock']} left)"
    # The cola line was reserved first and must have been given back.
    assert product_by_name(client, "Cola")["stock"] == cola["stock"]


def test_unknown_product_is_rejected(client):
    response = client.post("/api/orders", json={"customer_username": "alice", "items": [{"product_id": 9999, "quantity": 1}]})
    assert response.status_code == 400
    assert response.json()["detail"] == "Product 9999 not available"


def test_orders_stack_freely_without_a_due_date(client):
    water = product_by_name(client, "Bottled Water")
    for _ in range(2):
        response = client.post("/api/orders", json={"customer_username": "alice", "items": [{"product_id": water["id"], "quantity": 1}]})
        assert response.status_code == 201, response.text


def test_customer_lookup_shows_history_stats_and_favorites(client):
    response = client.get("/api/customers/ALICE")
    assert response.status_code == 200
    body = response.json()
    assert body["customer"]["username"] == "alice"
    assert body["customer"]["has_pin"] is False
    assert len(body["orders"]) == 3
    assert body["orders"][0]["items"], "orders carry their lines"
    assert body["balance"] == pytest.approx(sum(o["total"] for o in body["orders"]))
    assert body["total_paid"] == 0
    stats = body["stats"]
    assert stats["orders"] == 3 and stats["pending_orders"] == 3
    assert stats["items_bought"] == 5
    assert stats["top_item"] in ("Cola", "Bottled Water")
    assert stats["busiest_day"] is not None
    assert len(stats["orders_per_month"]) == 1
    favorites = body["favorites"]
    assert [f["name"] for f in favorites][:2] in (["Cola", "Bottled Water"], ["Bottled Water", "Cola"])
    assert all(f["quantity"] >= 1 for f in favorites)


def test_suggest_returns_usernames_only_and_escapes_wildcards(client):
    assert client.get("/api/customers/suggest?q=al").json() == ["alice"]
    assert client.get("/api/customers/suggest?q=%").json() == []
    assert client.get("/api/customers/suggest?q=").json() == []


def test_unknown_customer_is_404(client):
    assert client.get("/api/customers/ghost_user_x").status_code == 404


def test_new_username_rules(client):
    cola = product_by_name(client, "Cola")
    too_long = "x" * 65
    response = client.post("/api/orders", json={"customer_username": too_long, "items": [{"product_id": cola["id"], "quantity": 1}]})
    assert response.status_code == 422
    response = client.post("/api/orders", json={"customer_username": "bad​name", "items": [{"product_id": cola["id"], "quantity": 1}]})
    assert response.status_code == 422
    response = client.post("/api/orders", json={"customer_username": "   ", "items": [{"product_id": cola["id"], "quantity": 1}]})
    assert response.status_code == 400


# ---- admin: orders, payment, cancel ------------------------------------------


def test_orders_need_a_token(client):
    assert client.get("/api/orders").status_code == 401


def test_admin_lists_orders_and_items(client, admin_headers):
    orders = client.get("/api/orders?status_=pending", headers=admin_headers).json()
    assert len(orders) == 3
    items = client.get(f"/api/orders/{orders[-1]['id']}/items", headers=admin_headers).json()
    assert {i["product_name"] for i in items} == {"Cola", "Potato Chips"}


def test_cancelling_a_pending_order_restores_stock_and_is_final(client, admin_headers, stack):
    water_before = product_by_name(client, "Bottled Water")["stock"]
    orders = client.get("/api/orders?status_=pending", headers=admin_headers).json()
    water_order = next(o for o in orders if o["total"] == product_by_name(client, "Bottled Water")["price"])
    response = client.patch(
        f"/api/orders/{water_order['id']}/status?new_status=cancelled&expected_status=pending", headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert product_by_name(client, "Bottled Water")["stock"] == water_before + 1
    # cancelled is final
    response = client.patch(f"/api/orders/{water_order['id']}/status?new_status=paid", headers=admin_headers)
    assert response.status_code == 409
    # the audit entry reached the audit service through the outbox
    stack.flush_outboxes()
    audit = client.get("/api/audit?action=order.cancelled", headers=admin_headers).json()
    assert audit and "(stock restored)" in audit[0]["details"]
    assert audit[0]["actor"] == "admin"


def test_expected_status_guards_against_a_lost_race(client, admin_headers):
    orders = client.get("/api/orders?status_=pending", headers=admin_headers).json()
    order = orders[0]
    response = client.patch(f"/api/orders/{order['id']}/status?new_status=paid", headers=admin_headers)
    assert response.status_code == 200
    # A Cancel button that still showed "pending" must not cancel a paid order.
    response = client.patch(
        f"/api/orders/{order['id']}/status?new_status=cancelled&expected_status=pending", headers=admin_headers
    )
    assert response.status_code == 409
    assert "already paid" in response.json()["detail"]
    # paid -> pending is allowed
    response = client.patch(f"/api/orders/{order['id']}/status?new_status=pending", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_invalid_status_is_400(client, admin_headers):
    orders = client.get("/api/orders", headers=admin_headers).json()
    assert client.patch(f"/api/orders/{orders[0]['id']}/status?new_status=bogus", headers=admin_headers).status_code == 400
    assert client.patch("/api/orders/99999/status?new_status=paid", headers=admin_headers).status_code == 404


def test_customers_list_shows_balance_and_total_paid(client, admin_headers):
    customers = client.get("/api/customers", headers=admin_headers).json()
    alice = next(c for c in customers if c["username"] == "alice")
    assert alice["order_count"] == 3
    assert alice["balance"] > 0
    assert alice["stats"]["cancelled_orders"] == 1
    assert alice["stats"]["pending_orders"] == 2


# ---- due date & unpaid block --------------------------------------------------


def test_future_due_date_is_stamped_on_orders_but_does_not_block(client, admin_headers):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    set_setting(client, admin_headers, "payment_due_date", tomorrow)
    cola = product_by_name(client, "Cola")
    response = client.post("/api/orders", json={"customer_username": "alice", "items": [{"product_id": cola["id"], "quantity": 1}]})
    assert response.status_code == 201, response.text
    assert response.json()["due_date"].startswith(tomorrow)
    lookup = client.get("/api/customers/alice").json()
    assert lookup["stats"]["next_due_date"].startswith(tomorrow)


def test_overdue_balance_blocks_checkout_until_reset_payment(client, admin_headers, stack):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    set_setting(client, admin_headers, "payment_due_date", yesterday)
    cola = product_by_name(client, "Cola")
    stock_before = cola["stock"]
    response = client.post("/api/orders", json={"customer_username": "alice", "items": [{"product_id": cola["id"], "quantity": 1}]})
    assert response.status_code == 403
    assert response.json()["detail"] == OVERDUE_DETAIL
    assert product_by_name(client, "Cola")["stock"] == stock_before, "a blocked checkout takes no stock"

    # A new customer is not blocked.
    response = client.post("/api/orders", json={"customer_username": "bob", "items": [{"product_id": cola["id"], "quantity": 1}]})
    assert response.status_code == 201

    # Reset payment settles every pending order and unblocks the customer.
    response = client.post("/api/customers/alice/reset-payment", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["settled"] == 3
    assert client.get("/api/customers/alice").json()["balance"] == 0
    response = client.post("/api/orders", json={"customer_username": "alice", "items": [{"product_id": cola["id"], "quantity": 1}]})
    assert response.status_code == 201

    stack.flush_outboxes()
    audit = client.get("/api/audit?action=customer.reset_payment", headers=admin_headers).json()
    assert audit and audit[0]["actor"] == "admin" and "3 order(s) marked paid" in audit[0]["details"]

    set_setting(client, admin_headers, "payment_due_date", "")


def test_reset_payment_for_unknown_customer_is_404(client, admin_headers):
    assert client.post("/api/customers/ghost_user_x/reset-payment", headers=admin_headers).status_code == 404


def test_self_mark_paid_is_disabled_by_default(client, admin_headers):
    response = client.post("/api/customers/bob/self-mark-paid")
    assert response.status_code == 403
    set_setting(client, admin_headers, "customer_self_service_payment", "true")
    response = client.post("/api/customers/bob/self-mark-paid")
    assert response.status_code == 200
    assert response.json()["settled"] == 1
    set_setting(client, admin_headers, "customer_self_service_payment", "false")


# ---- PINs -------------------------------------------------------------------


def test_pin_flow(client, admin_headers, stack):
    cola = product_by_name(client, "Cola")
    assert client.post("/api/customers/bob/pin", json={"pin": "12"}).status_code == 422
    assert client.post("/api/customers/bob/pin", json={"pin": "1234"}).json() == {"username": "bob", "has_pin": True}

    # Lookup and checkout now need the PIN.
    assert client.get("/api/customers/bob").status_code == 428
    assert client.get("/api/customers/bob", headers={"X-Customer-PIN": "0000"}).status_code == 403
    assert client.get("/api/customers/bob", headers={"X-Customer-PIN": "1234"}).status_code == 200
    response = client.post("/api/orders", json={"customer_username": "bob", "items": [{"product_id": cola["id"], "quantity": 1}]})
    assert response.status_code == 428
    assert response.json()["detail"] == "PIN required"
    response = client.post("/api/orders", json={"customer_username": "bob", "customer_pin": "9999", "items": [{"product_id": cola["id"], "quantity": 1}]})
    assert response.status_code == 403
    assert response.json()["detail"] == "Wrong PIN"
    response = client.post("/api/orders", json={"customer_username": "bob", "customer_pin": "1234", "items": [{"product_id": cola["id"], "quantity": 1}]})
    assert response.status_code == 201, response.text

    # An admin token does not bypass the order PIN, but the admin lookup does.
    response = client.post("/api/orders", headers=admin_headers, json={"customer_username": "bob", "items": [{"product_id": cola["id"], "quantity": 1}]})
    assert response.status_code == 428
    assert client.get("/api/customers/bob?as_admin=true", headers=admin_headers).status_code == 200
    assert client.get("/api/customers/bob?as_admin=true").status_code == 428

    # Changing the PIN needs the current one.
    assert client.post("/api/customers/bob/pin", json={"pin": "5678"}).status_code == 428
    assert client.post("/api/customers/bob/pin", json={"pin": "5678", "current_pin": "1234"}).status_code == 200

    # Staff cannot remove the PIN while orders are pending.
    response = client.post("/api/customers/bob/reset-pin", headers=admin_headers)
    assert response.status_code == 409
    assert client.post("/api/customers/bob/reset-payment", headers=admin_headers).status_code == 200
    assert client.post("/api/customers/bob/reset-pin", headers=admin_headers).json() == {"username": "bob", "has_pin": False}
    assert client.get("/api/customers/bob").status_code == 200

    stack.flush_outboxes()
    actions = {a["action"] for a in client.get("/api/audit?action=customer.pin", headers=admin_headers).json()}
    assert {"customer.pin_set", "customer.pin_changed", "customer.pin_reset"} <= actions


def test_pin_lockout_after_five_wrong_attempts(client, stack, admin_headers):
    client.post("/api/customers/bob/pin", json={"pin": "4321"})
    for _ in range(5):
        assert client.get("/api/customers/bob", headers={"X-Customer-PIN": "0000"}).status_code == 403
    response = client.get("/api/customers/bob", headers={"X-Customer-PIN": "4321"})
    assert response.status_code == 429
    assert "Too many wrong PINs" in response.json()["detail"]
    stack.flush_outboxes()
    locked = client.get("/api/audit?action=customer.pin_locked", headers=admin_headers).json()
    assert locked and locked[0]["actor"] == "kiosk"
    # unlock for later tests by removing the PIN (no pending orders for bob now)
    assert client.post("/api/customers/bob/reset-pin", headers=admin_headers).status_code == 200


# ---- catalog admin ------------------------------------------------------------


def test_product_crud_restock_and_counts(client, admin_headers, stack):
    response = client.post(
        "/api/products", headers=admin_headers,
        json={"name": "Test Gum", "price": 1.5, "cost_price": 0.5, "stock": 10, "barcodes": ["GUM-1", " gum-1 "]},
    )
    assert response.status_code == 201, response.text
    product = response.json()
    assert product["barcodes"] == ["gum-1"]
    assert client.get("/api/products/barcode/GUM-1").json()["id"] == product["id"]
    assert client.get("/api/products/barcode/nope").status_code == 404

    # duplicate barcode on another product is a conflict
    response = client.post("/api/products", headers=admin_headers, json={"name": "Dup", "price": 1, "barcodes": ["gum-1"]})
    assert response.status_code == 409

    # stock only changes with the expected_stock the form showed
    response = client.put(f"/api/products/{product['id']}", headers=admin_headers, json={"stock": 12, "expected_stock": 99})
    assert response.status_code == 409
    response = client.put(f"/api/products/{product['id']}", headers=admin_headers, json={"stock": 12, "expected_stock": 10, "price": 1.75})
    assert response.status_code == 200
    assert response.json()["stock"] == 12 and response.json()["price"] == 1.75

    # special window validation
    response = client.put(
        f"/api/products/{product['id']}", headers=admin_headers,
        json={"is_weekly_special": True, "special_price": 1.0, "special_starts_on": "2026-02-02", "special_ends_on": "2026-01-01"},
    )
    assert response.status_code == 422
    response = client.put(
        f"/api/products/{product['id']}", headers=admin_headers,
        json={"is_weekly_special": True, "special_price": 1.0, "special_starts_on": None, "special_ends_on": None},
    )
    assert response.json()["special_active"] is True

    # restock adds stock and records the purchase price
    response = client.post(f"/api/products/{product['id']}/restock", headers=admin_headers, json={"quantity": 8, "unit_cost": 0.6, "note": "box"})
    assert response.status_code == 201
    assert response.json()["stock_after"] == 20
    assert client.get(f"/api/products/{product['id']}", headers=admin_headers).json()["cost_price"] == 0.6
    assert client.get(f"/api/products/{product['id']}/restocks", headers=admin_headers).json()[0]["quantity"] == 8
    assert client.get("/api/restocks?limit=5", headers=admin_headers).json()[0]["product_name"] == "Test Gum"

    # a sale at the special price snapshots that price onto the order line
    response = client.post("/api/orders", json={"customer_username": "carol", "items": [{"product_id": product["id"], "quantity": 2}]})
    assert response.status_code == 201
    assert response.json()["total"] == 2.0

    # count: a moved line is a conflict, the other is applied
    response = client.post(
        "/api/inventory/counts", headers=admin_headers,
        json={"items": [
            {"product_id": product["id"], "counted": 15, "expected_stock": 18},
            {"product_id": product["id"], "counted": 1, "expected_stock": 999},
            {"product_id": 99999, "counted": 1, "expected_stock": 1},
        ]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["applied"]) == 1 and body["applied"][0]["difference"] == -3
    assert body["applied"][0]["reason"] == "shrinkage"
    assert len(body["conflicts"]) == 2
    assert client.get("/api/inventory/adjustments?limit=5", headers=admin_headers).json()[0]["counted"] == 15

    stack.flush_outboxes()
    actions = [a["action"] for a in client.get("/api/audit?action=product.", headers=admin_headers).json()]
    assert {"product.create", "product.update", "product.restock", "product.count"} <= set(actions)

    # delete
    assert client.delete(f"/api/products/{product['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/products/{product['id']}").status_code == 404


def test_product_image_upload_and_delete(client, admin_headers):
    cola = product_by_name(client, "Cola")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    response = client.post(f"/api/products/{cola['id']}/image", headers=admin_headers, files={"file": ("c.png", png, "image/png")})
    assert response.status_code == 200, response.text
    url = response.json()["image_url"]
    assert url.startswith("/api/images/")
    assert client.get(url).status_code == 200
    bad = client.post(f"/api/products/{cola['id']}/image", headers=admin_headers, files={"file": ("c.png", b"not a png", "image/png")})
    assert bad.status_code == 400
    assert client.delete(f"/api/products/{cola['id']}/image", headers=admin_headers).json()["image_url"] is None


def test_category_crud(client, admin_headers):
    response = client.post("/api/categories", headers=admin_headers, json={"name": "Temp", "sort_order": 9})
    assert response.status_code == 201
    cid = response.json()["id"]
    assert client.post("/api/categories", headers=admin_headers, json={"name": "Temp"}).status_code == 400
    assert client.put(f"/api/categories/{cid}", headers=admin_headers, json={"description": "x"}).json()["description"] == "x"
    assert client.delete(f"/api/categories/{cid}", headers=admin_headers).status_code == 204


# ---- reports -----------------------------------------------------------------


def test_reports(client, admin_headers):
    summary = client.get("/api/reports/summary", headers=admin_headers).json()
    assert summary["basis"] == "sales"
    assert summary["all_time"]["order_count"] >= 5
    assert summary["outstanding"] > 0
    assert summary["pending_orders"] >= 1
    assert isinstance(summary["low_stock_products"], list)
    assert summary["margin_month"]["revenue"] > 0

    paid = client.get("/api/reports/summary?basis=paid", headers=admin_headers).json()
    assert paid["all_time"]["order_count"] < summary["all_time"]["order_count"]

    margins = client.get("/api/reports/margins?period=all", headers=admin_headers).json()
    assert margins["totals"]["margin"] > 0
    assert margins["products"][0]["margin_pct"] is not None

    top = client.get("/api/reports/top-products?limit=3", headers=admin_headers).json()
    assert top and top[0]["quantity"] >= top[-1]["quantity"]

    by_day = client.get("/api/reports/sales-by-day?days=14", headers=admin_headers).json()
    assert len(by_day) == 1 and by_day[0]["orders"] >= 5

    insights = client.get("/api/reports/customer-insights?limit=5", headers=admin_headers).json()
    assert insights["today"][0]["username"] in ("alice", "bob", "carol")
    assert insights["last_paid"]["username"] in ("alice", "bob")

    shrink = client.get("/api/reports/shrinkage?period=month", headers=admin_headers).json()
    assert shrink["totals"]["units_lost"] == 3
    assert shrink["by_reason"] == {"shrinkage": 3}
    assert shrink["totals"]["value_lost"] == pytest.approx(1.8)

    reorder = client.get("/api/reports/reorder?days=28&cover_days=14", headers=admin_headers).json()
    assert reorder["days"] == 28
    assert all(r["suggested"] > 0 for r in reorder["products"])
    csv_text = client.get("/api/reports/reorder.csv", headers=admin_headers).text
    assert csv_text.lstrip("﻿").startswith("product,category,stock")

    export = client.get("/api/reports/export.csv", headers=admin_headers)
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    text = export.text
    for section in ("sales_summary", "outstanding", "customer_balance", "inventory", "margins", "daily_sales", "top_products", "last_payment"):
        assert f"\n{section}," in text, section
    assert client.get("/api/reports/export.csv").status_code == 401


# ---- settings, users, audit -----------------------------------------------------


def test_settings_update_is_audited(client, admin_headers, stack):
    set_setting(client, admin_headers, "store_name", "Test Store")
    assert client.get("/api/settings").json()["store_name"] == "Test Store"
    assert client.put("/api/settings/store_name", json={"key": "store_name", "value": "x"}).status_code == 401
    stack.flush_outboxes()
    audit = client.get("/api/audit?action=settings.update", headers=admin_headers).json()
    assert audit[0]["details"] == "store_name: My Kiosk Store -> Test Store"


def test_users_crud_and_password_change_revokes_tokens(client, admin_headers, stack):
    assert client.post("/api/users", headers=admin_headers, json={"username": "staff", "password": "short"}).status_code == 422
    response = client.post("/api/users", headers=admin_headers, json={"username": "staff", "password": "staff-password-1", "full_name": "Staff"})
    assert response.status_code == 201
    staff = response.json()
    assert client.post("/api/users", headers=admin_headers, json={"username": "staff", "password": "staff-password-1"}).status_code == 400

    token = client.post("/api/auth/login", json={"username": "staff", "password": "staff-password-1"}).json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/orders", headers=staff_headers).status_code == 200, "other services accept the token"

    # a password change invalidates older tokens everywhere
    assert client.put(f"/api/users/{staff['id']}", headers=admin_headers, json={"password": "staff-password-2"}).status_code == 200
    assert client.get("/api/orders", headers=staff_headers).status_code == 401
    assert client.get("/api/auth/me", headers=staff_headers).status_code == 401

    # a deactivated user cannot log in
    client.put(f"/api/users/{staff['id']}", headers=admin_headers, json={"is_active": False})
    assert client.post("/api/auth/login", json={"username": "staff", "password": "staff-password-2"}).status_code == 401

    me = client.get("/api/auth/me", headers=admin_headers).json()
    assert client.delete(f"/api/users/{me['id']}", headers=admin_headers).status_code == 400
    assert client.delete(f"/api/users/{staff['id']}", headers=admin_headers).status_code == 204

    stack.flush_outboxes()
    audit = client.get("/api/audit?action=user.", headers=admin_headers).json()
    assert {a["action"] for a in audit} == {"user.create", "user.update", "user.delete"}
    assert all("staff-password" not in a["details"] for a in audit)


def test_forged_and_unsigned_tokens_are_rejected_everywhere(client):
    forged = jwt.encode({"sub": "admin"}, "not-the-secret-but-long-enough-for-hs256", algorithm="HS256")
    unsigned = jwt.encode({"sub": "admin"}, None, algorithm="none")
    signed_unknown_user = jwt.encode({"sub": "nobody", "pwv": "x"}, SECRET_KEY, algorithm="HS256")
    for token in (forged, unsigned, signed_unknown_user):
        headers = {"Authorization": f"Bearer {token}"}
        for path in ("/api/orders", "/api/users", "/api/customers", "/api/audit", "/api/reports/summary", "/api/system/status"):
            assert client.get(path, headers=headers).status_code == 401, path


def test_login_rate_limit(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password"})
    response = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    # another client address is unaffected (the gateway forwards X-Forwarded-For)
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD},
        headers={"X-Forwarded-For": "10.0.0.9"},
    )
    assert response.status_code == 200
    from auth_service.routers import auth as auth_routes

    auth_routes._failed_attempts.clear()


# ---- system: status & backups --------------------------------------------------


def test_system_status_and_backups(client, admin_headers, stack):
    status = client.get("/api/system/status", headers=admin_headers).json()
    assert status["version"] == "dev"
    assert status["database"]["engine"] == "sqlite"
    assert status["database"]["size_bytes"] > 0
    assert set(status["database"]["databases"]) == {"auth", "catalog", "customers", "orders", "settings", "audit"}
    assert status["counts"]["products"] == 11
    assert status["counts"]["customers"] == 3
    assert status["counts"]["users"] == 1
    assert status["counts"]["orders"] >= 6
    assert status["last_activity"]["action"]
    assert status["backups"]["supported"] is True
    assert status["backups"]["interval_hours"] == 24 and status["backups"]["keep"] == 7

    response = client.post("/api/system/backups", headers=admin_headers)
    assert response.status_code == 201, response.text
    backup = response.json()
    assert backup["name"].startswith("kiosk-") and backup["name"].endswith(".tar.gz")
    assert backup["databases"] == ["audit", "auth", "catalog", "customers", "orders", "settings"]

    listing = client.get("/api/system/backups", headers=admin_headers).json()
    assert listing["count"] == 1 and listing["items"][0]["name"] == backup["name"]

    download = client.get(f"/api/system/backups/{backup['name']}", headers=admin_headers)
    assert download.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(download.content), mode="r:gz") as archive:
        assert sorted(archive.getnames()) == ["audit.db", "auth.db", "catalog.db", "customers.db", "orders.db", "settings.db"]
    assert client.get("/api/system/backups/../etc/passwd", headers=admin_headers).status_code in (404, 400)
    assert client.get("/api/system/backups/kiosk-00000000-000000.tar.gz", headers=admin_headers).status_code == 404

    stack.flush_outboxes()
    audit = client.get("/api/audit?action=backup.", headers=admin_headers).json()
    assert {a["action"] for a in audit} == {"backup.create", "backup.download"}


# ---- concurrency --------------------------------------------------------------


def test_simultaneous_checkouts_never_oversell(client, admin_headers):
    response = client.post("/api/products", headers=admin_headers, json={"name": "Race Soda", "price": 2.0, "stock": 6})
    product = response.json()
    results = []

    def buy():
        r = client.post("/api/orders", json={"customer_username": "racer", "items": [{"product_id": product["id"], "quantity": 2}]})
        results.append(r.status_code)

    threads = [threading.Thread(target=buy) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 201, 201, 400, 400, 400], results
    assert product_by_name(client, "Race Soda")["stock"] == 0
    racer = client.get("/api/customers/racer").json()
    assert racer["stats"]["items_bought"] == 6
