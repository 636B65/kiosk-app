def test_health_is_aggregated_over_every_service(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["services"]) == {"auth", "catalog", "customers", "orders", "settings", "audit", "reports"}


def test_each_service_has_liveness_and_readiness_probes(stack):
    for name, app in stack.apps.items():
        service = stack.service(name)
        assert service.get("/healthz").json()["service"].endswith("-service"), name
        assert service.get("/readyz").status_code == 200, name


def test_unknown_api_path_is_404(client):
    assert client.get("/api/nothing-here").status_code == 404


def test_login_and_me(client, admin_headers):
    me = client.get("/api/auth/me", headers=admin_headers)
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_wrong_password_is_401(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "nope-nope"})
    assert response.status_code == 401


def test_seeded_catalog_hides_cost_price_from_the_public(client, admin_headers):
    public = client.get("/api/products").json()
    assert len(public) == 11
    assert all(p["cost_price"] is None for p in public)
    staff = client.get("/api/products", headers=admin_headers).json()
    assert any(p["cost_price"] is not None for p in staff)
    categories = client.get("/api/categories").json()
    assert [c["name"] for c in categories] == ["Electronics", "Snacks", "Beverages", "Clothing"]


def test_settings_are_seeded_and_public(client):
    settings = client.get("/api/settings").json()
    assert settings["currency"] == "EUR"
    assert settings["payment_due_date"] == ""
