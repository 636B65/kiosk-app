# AGENTS.md

Guidance for AI coding agents working on this repo. Read this before editing anything.

## What this is

A self-service kiosk app for a small store: customers pick products at a touchscreen,
check out on a "tab" under their username, and the **staff mark orders as paid later**
(admin panel). Includes per-user purchase stats and a store-wide payment due date.

- Backend: **FastAPI + SQLAlchemy (1.x-style `Column` API) + SQLite**, `python:3.12` in Docker.
- Frontend: **vanilla JS, no framework/build step** (plain `<script>` tags), served by `nginx:alpine` behind **self-signed TLS**.
- Tests: pytest (backend) + a zero-dependency Playwright harness (e2e, uses system Chromium).
- CI: 3 jobs — Backend API tests, End-to-end browser tests, Docker + TLS smoke (`ci.yml`).
- Releases: every `v*` tag triggers `publish-images.yml`, which builds and pushes
  `ghcr.io/636b65/kiosk/backend` and `.../frontend` images (`v<tag>` + `latest`).

## Quick commands

```bash
# Backend tests (Python 3.12; see Gotchas for the pinned-deps note)
cd backend && pytest tests -v

# Lint / types (mypy checks config.py, timeutil.py, schemas.py, security.py, seed.py per pyproject.toml)
cd backend && ruff check .
cd backend && mypy

# Frontend JS syntax (no build step exists)
node --check frontend/js/*.js

# End-to-end tests (launches backend with E2E_PYTHON + system Chromium; NO Docker needed)
cd tests/e2e && npm ci
CHROMIUM_PATH=/usr/bin/chromium E2E_PYTHON=python3.12 npm test

# Full stack with TLS (self-signed cert generated into data/tls/ on first boot)
docker compose up -d --build
curl -sk https://localhost/api/health
```

Do all three repo checks before finishing a change: backend tests, ruff/mypy, and `node --check`.
The e2e suite is the source of truth for user-facing behavior — update it when behavior or
admin UI columns change.

## Layout

```
backend/
  main.py          app wiring, CORS, mounts /api/images, runs migrate()+seed() at startup
  config.py        Settings (pydantic-settings, env_file=".env"), SECRET_KEY handling
  database.py      SQLite engine + session (read DATABASE_PATH at import time)
  models.py        User, Category, Product, Customer, Order, OrderItem, Setting
  migrations.py    idempotent SQLite ALTER TABLE-style migrations, run at startup
  seed.py          admin user (ADMIN_PASSWORD or random) + demo categories/products/settings
  security.py      bcrypt + JWT auth, OAuth2 bearer
  timeutil.py      utcnow()        # naive UTC. NEVER use datetime.utcnow()
  due_dates.py     payment_due_date parsing/computation helpers
  schemas.py       Pydantic v2 response/serialization schemas
  routers/         auth, categories, customers, orders, products, reports, settings, users
  tests/           test_api.py (full API suite) + test_due_dates.py (units)
frontend/
  index.html       no <meta> CSP; scripts loaded in fixed order (api -> app -> customer -> admin -> handlers -> debug)
  css/             styles.css
  js/
    api.js         fetch wrapper + token storage
    app.js         entry: route handling, Store, Toast, Modal, currency list
    customer.js    Kiosk cart/checkout + user lookup
    admin.js       admin panel (orders, products, categories, customers, users, settings, reports)
    handlers.js    Actions registry (event delegation)
    debug.js       Debug panel
tests/e2e/
  e2e.js          main Playwright harness (npm test)
  https-smoke.js  TLS/CSP/admin-login smoke against docker compose
```

## Business rules (critical — do not change without updating tests + frontend)

- **Tab checkout**: `POST /api/orders` accepts a username (not a paid transaction). An
  order is created as `pending`; staff settle it via `PATCH /api/orders/{id}/status` or the
  admin "Reset payment" for a whole customer.
- **Unpaid-order block**: if the customer already has an order with `status == "pending"`,
  checkout returns **403** "Your previous order is still unpaid. Ask the staff to mark it
  as paid before you can buy again." (cancelled orders do NOT block). This is enforced
  server-side in `routers/orders.py::create_order`; the kiosk shows the message as a red toast.
- **Reset payment** (`POST /api/customers/{username}/reset-payment`) marks ALL pending
  orders of a customer as `paid`. This is the only unblock besides setting them paid individually.
- **Admin payment**: `PATCH /api/orders/{id}/status` accepts `pending|paid|cancelled`.
  Cancelling a `pending` order **restores stock**; paid orders can't have stock restored.
- **Due date**: Setting `payment_due_date` (ISO date `YYYY-MM-DD`, default `""` = no end date).
  When set, new orders get `due_date = <that date> 23:59:59` (naive UTC). Empty/invalid = `NULL`.
  This is the store-wide "pay by" moment shown in admin and on customer lookups.
- **Weekly specials / pricing**: a product's displayed price is `special_price` when
  `is_weekly_special` is true, else `price`. Orders always store the price snapshotted
  at purchase time in `OrderItem.unit_price` (and `product_name`), so admin order lines
  still show what was paid even if the product later changes.
- **Stock**: decremented at order creation; never negative (400 if insufficient).
- **Lookup/suggest is public** (no auth): `GET /api/customers/suggest` returns only matching
  usernames (max 20) — never balances. `GET /api/customers/{username}` returns full history
  including balance. Both match usernames case-insensitively (stored lowercase).
- **Stats**: `CustomerStats` = order count, total spent/paid, balance (sum of pending), avg
  order, items bought, first/last order, top item, orders-per-month + spent/month,
  orders-by-weekday, busiest day, next due date. Balance shown in admin = pending total only.

## Backend conventions

- `python:3.12`, pydantic v2, SQLAlchemy classic `Column(...)` models (no `Mapped[]`).
- Run migrations in `migrations.py` (idempotent, `migrate(engine)`, uses `ALTER TABLE`
  style adds with `IF NOT EXISTS`-guarded logic). Inspect `sqlite_master` before altering.
- Use `timeutil.utcnow()` — never `datetime.utcnow()`. All timestamps are naive UTC.
- Admin-only endpoints: `dependency=Depends(get_current_user)`. Customer-facing endpoints
  (orders POST, customers GET/suggest/{username}) are public by design — do not protect them.
- Schema responses via Pydantic v2 (`model_validate`, `ConfigDict(from_attributes=True)` in schemas.py).
- `money = round(x, 2)` floats; keep it consistent.
- Do NOT modify `backend/requirements.txt` / `requirements-dev.txt` unless you also update
  the Dockerfiles pin-worthy versions — every dependency pinned there is used by Docker/CI.

## Frontend conventions

- **No build step, no JS modules.** Globals: `Store`, `API`, `Modal`, `Toast`, `Kiosk`,
  `Admin`, `Actions`, `Debug`. Script include order in `index.html` defines load order.
- **Event handling MUST use the `Actions` registry** (`data-action` attributes, delegated
  click/input listeners in `handlers.js`). Do NOT add `onclick=` inline handlers — they fight
  the CSP-less page and the codebase convention.
- `Store.cart` is persisted to `localStorage["kiosk_cart"]`. After page load the kiosk
  keeps showing the persisted cart.
- Routing is hash-based (`#/admin/dashboard` etc.) handled in `app.js::parseRoute`.
- Format money with the currency from `Store.settings.currency` (SUPPORTED_CURRENCIES in app.js).
- `Modal.open(content)`/`Modal.fill(content)`/`Modal.close()` for dialogs; `Toast.success/error`.
- The admin customers table columns, in order: User | Created | Orders | Orders/mo |
  Busiest day | Total paid | **Balance** | actions. E2E reads balance via `td:nth(6)`.

## Config & env vars

| Env | Effect |
| --- | --- |
| `DATABASE_PATH` | SQLite file (default `data/kiosk.db`) |
| `SECRET_KEY` | JWT signing key; if unset a random one is generated per process (tokens invalidate on restart) — never ship a hardcoded key |
| `ADMIN_PASSWORD` | Seed password for `admin`; **min 8 chars**, else ignored and a random one is generated + printed at first boot |
| `CORS_ORIGINS` | Comma-separated allowed origins (defaults to localhost/https+s hosts) |
| `KIOSK_TEST_DB` | pytest + e2e write their SQLite test DB wherever this points |
| `E2E_PYTHON` | Python used by the e2e harness to launch the backend |
| `CHROMIUM_PATH` | System Chromium/Chrome binary used by Playwright tests |

## Release process

1. Bump **CHANGELOG.md** with the new `[x.y.z] - <date>` section and update the test-count line in
   the Tests section.
2. Commit and push to `main`, then verify CI is green (backends + e2e + Docker/TLS smoke).
3. `git tag vX.Y.Z` and push it → `publish-images.yml` builds/pushes GHCR images and you
   create the GitHub Release (no source assets are attached historically).
4. Version bumps are the only tag-triggered releases; a plain `main` push does NOT rebuild images.

**Note:** the GHCR packages are currently **private** (unauthenticated `docker pull` → 401).
Making them public requires the `read:packages` + `write:packages` scopes on the `gh` token
(`gh auth refresh -h github.com -s read:packages,write:packages` or manual package settings);
a token without those scopes gets HTTP 401/403 from the Packages API.

## Testing notes & gotchas

- Backend tests are session-scoped against one SQLite DB (`KIOSK_TEST_DB`) so state persists
  between tests (customers/orders created early are reused later). They set
  `ADMIN_PASSWORD=test-admin-password` and use an `admin_headers` fixture for protected calls.
  Order matters — keep tests in the file consistent with the shared DB.
- e2e gotchas discovered the hard way:
  - The lookup trigger (`#lookup-btn`) also has class `cart-btn`, so Playwright's doubled
    `click()` opens the cart overlay — start failure-prone steps with a fresh `page.goto`.
  - The kiosk cart persists in `localStorage["kiosk_cart"]` across page loads; a failed/blocked
    checkout leaves items in the cart (add buttons become qty controls). Clear the key +
    reload when a prior step intentionally left the cart populated.
  - Any new customer-facing toast or new admin table column usually means updating e2e.js
    (balance is `td:nth(6)`; the unpaid-block toast text must match `orders.py` detail).
- Local Python is frequently newer than 3.12; the pinned `requirements.txt` wheels may lack
  compatibility → install first `fastapi pydantic sqlalchemy uvicorn python-multipart
  pyjwt bcrypt pytest ruff mypy` as latest (loose) when developing locally, but never change
  the pinned requirement files themselves.
- The Docker+TLS smoke job needs a Docker daemon and cannot run on a machine without one —
  run it in CI or `docker compose up` locally.
- `#app` + admin views render via JS; there are no server-side templates.

## Workflow conventions

- Make changes intentionally and small; run the three checks above.
- Keep the e2e suite in lockstep with behavior and admin-UI changes (it's the compatibility
  gate in CI).
- Do not commit generated files, the SQLite DB, `data/tls/` certs, or `node_modules`.