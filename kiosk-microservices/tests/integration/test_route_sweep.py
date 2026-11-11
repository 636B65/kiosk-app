"""Every endpoint that is not deliberately public must refuse anonymous callers.

Public routes are listed explicitly (as the monolith's test suite did); the
``/internal/*`` routes must refuse callers without the internal token.
"""

import re

PUBLIC_ENDPOINTS = {
    ("system", "GET", "/api/health"),
    ("auth", "POST", "/api/auth/login"),
    ("auth", "POST", "/api/auth/login/form"),
    ("catalog", "GET", "/api/categories"),
    ("catalog", "GET", "/api/products"),
    ("catalog", "GET", "/api/products/{product_id}"),
    ("catalog", "GET", "/api/products/barcode/{barcode}"),
    ("settings", "GET", "/api/settings"),
    ("orders", "POST", "/api/orders"),
    ("customers", "GET", "/api/customers/suggest"),
    ("customers", "GET", "/api/customers/{username}"),
    ("customers", "POST", "/api/customers/{username}/self-mark-paid"),
    ("customers", "POST", "/api/customers/{username}/pin"),
}


def _endpoints(stack):
    for name, app in stack.apps.items():
        for path, operations in app.openapi()["paths"].items():
            for method in operations:
                yield name, method.upper(), path


def test_every_non_public_api_endpoint_requires_a_token(stack):
    seen = 0
    for name, method, path in _endpoints(stack):
        if not path.startswith("/api/") or (name, method, path) in PUBLIC_ENDPOINTS:
            continue
        seen += 1
        concrete = re.sub(r"\{[^}]+\}", "1", path)
        response = stack.service(name).request(method, concrete)
        assert response.status_code == 401, f"{name} {method} {path} answered {response.status_code}"
    assert seen > 35, "the sweep should see the whole API"


def test_every_internal_endpoint_requires_the_internal_token(stack, internal_headers):
    seen = 0
    for name, method, path in _endpoints(stack):
        if not path.startswith("/internal/"):
            continue
        seen += 1
        concrete = re.sub(r"\{[^}]+\}", "1", path)
        service = stack.service(name)
        assert service.request(method, concrete).status_code == 401, f"{name} {method} {path}"
        assert service.request(method, concrete, headers={"X-Internal-Token": "wrong"}).status_code == 401
        with_token = service.request(method, concrete, headers=internal_headers)
        assert with_token.status_code != 401, f"{name} {method} {path} rejected the internal token"
    assert seen >= 12


def test_public_endpoints_exist(stack):
    all_routes = set(_endpoints(stack))
    missing = PUBLIC_ENDPOINTS - all_routes
    assert not missing, missing
