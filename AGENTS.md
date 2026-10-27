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
- Releases: when CI on `main` is green and the newest `CHANGELOG.md` version has no tag yet,
  `release.yml` creates the `vX.Y.Z` tag and calls `publish-images.yml` (also run by any pushed
  `v*` tag), which builds and pushes the `ghcr.io/636b65/kiosk/backend` and `.../frontend`
  images and then creates the GitHub Release. The `docker/metadata-action`
  semver pattern strips the leading `v`, so tag `v1.0.17` publishes as `1.0.17` + `latest`.

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
# Node >= 24.22.1 (CI pins Node 24 LTS and refuses older versions)
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
  migrations.py    idempotent SQLite ALTER TABLE-style migrations + ADDED_COLUMNS (all dialects), run at startup
  seed.py          admin user (ADMIN_PASSWORD or random) + demo categories/products/settings
  audit.py         audit.record(db, actor, action, ...) helper (no commit; caller commits)
  pins.py          customer PINs: Argon2id over HMAC-SHA256(pepper, pin); pepper outside the DB
  backups.py       SQLite VACUUM INTO backups, pruning, BackupScheduler thread
  security.py      bcrypt + JWT auth, OAuth2 bearer
  timeutil.py      utcnow()        # naive UTC. NEVER use datetime.utcnow()
  due_dates.py     payment_due_date parsing/computation helpers
  schemas.py       Pydantic v2 response/serialization schemas
  routers/         auth, audit, categories, customers, orders, products, reports, restocks,
                   settings, system (status + backups), users
  tests/           test_api.py (full API suite) + test_due_dates.py (units)
frontend/
  version.json     dev placeholder; the Docker build overwrites it with release + commit
  index.html       footer (release, commit, Changelog button); no <meta> CSP; scripts loaded in fixed order (demo -> api -> app -> customer -> admin -> handlers -> debug)
  css/             styles.css
  js/
    demo.js        in-browser API mock for the GitHub Pages demo (no-op unless .github.io host or ?demo=1)
    api.js         fetch wrapper + token storage
    app.js         entry: route handling, Store, Toast, Modal, AppInfo (footer), currency list
    customer.js    Kiosk cart/checkout + user lookup
    admin.js       admin panel (orders, products, categories, customers, users, settings, reports)
    handlers.js    Actions registry (event delegation)
    debug.js       Debug panel
scripts/
  release-info.sh  writes the version/commit JSON baked into both images
tests/e2e/
  e2e.js          main Playwright harness (npm test)
  https-smoke.js  TLS/CSP/admin-login smoke against docker compose
```

## Business rules (critical — do not change without updating tests + frontend)

- **Tab checkout**: `POST /api/orders` accepts a username (not a paid transaction). An
  order is created as `pending`; staff settle it via `PATCH /api/orders/{id}/status` or the
  admin "Reset payment" for a whole customer.
- **Unpaid-order block (overdue only)**: checkout returns **403** "The payment due date has
  passed and your previous order is still unpaid. Ask the staff to mark it as paid before
  you can buy again." only when a store-wide `payment_due_date` is configured **and has
  already passed** AND the customer has an order with `status == "pending"` (cancelled
  orders do NOT block). With no due date — or one still in the future — the tab stays open
  and orders stack freely (this guard was unconditional from v1.0.13 until the fix, which
  made every second purchase fail). Enforced server-side in `routers/orders.py::create_order`;
  the kiosk shows the message as a red toast; `demo.js` mirrors the rule for the GitHub Pages demo.
- **Reset payment** (`POST /api/customers/{username}/reset-payment`) marks ALL pending
  orders of a customer as `paid`. Unblocks are: this endpoint, paying orders individually,
  cancelling them, or clearing/moving the due date back into the future.
- **Customer self-mark-paid** is disabled by default. If an admin enables the
  `customer_self_service_payment` setting, the public username lookup lets anyone who knows
  a customer's username mark all of that customer's pending orders as paid. This does not
  verify identity or receipt of payment; enable it only when that trust model is acceptable.
- **Admin payment**: `PATCH /api/orders/{id}/status` accepts `pending|paid|cancelled`.
  Cancelling a `pending` order **restores stock**; paid orders can't have stock restored.
- **Due date**: Setting `payment_due_date` (ISO date `YYYY-MM-DD`, default `""` = no end date).
  When set, new orders get `due_date = <that date> 23:59:59` (naive UTC). Empty/invalid = `NULL`.
  This is the store-wide "pay by" moment shown in admin and on customer lookups, and once it
  has passed it gates further checkout while a balance is outstanding (see the block rule above).
- **Weekly specials / pricing**: a product's displayed price is `special_price` when the
  special is active, else `price`. A special is active when `is_weekly_special` is true,
  `special_price` is set, and today (UTC date) is within the optional inclusive
  `special_starts_on`..`special_ends_on` window (`Product.special_active`, exposed in
  `ProductOut`; the frontend uses `isSpecialActive()`/`specialState()` and must not
  re-derive it from `is_weekly_special` alone). An end before the start is a 422.
  Orders always store the price snapshotted at purchase time in `OrderItem.unit_price`
  (and `product_name`), so admin order lines still show what was paid even if the
  product later changes.
- **Purchase prices / margins**: `Product.cost_price` is staff-only. Public product
  endpoints (`GET /api/products`, `/{id}`, `/barcode/{code}`) return `cost_price: null`
  unless a valid admin token is sent (`get_optional_user`), and the Redis cache only
  stores/serves requests without an `Authorization` header. Orders snapshot the cost
  into `OrderItem.unit_cost` (never exposed in order/lookup schemas).
  `GET /api/reports/margins?period=today|week|month|all` reports revenue, cost and
  margin of paid lines; lines without a cost count as revenue but not toward margin.
- **Restocks**: `POST /api/products/{id}/restock` (admin; quantity 1..100000, optional
  `unit_cost` which also becomes the product's `cost_price`, note) adds stock and logs a
  `Restock` row; history via `GET /api/products/{id}/restocks` and `GET /api/restocks`.
- **Low stock**: each product has `low_stock_threshold` (default 5); the dashboard
  "Restock needed" list (`summary.low_stock_products`), CSV `restock_needed` rows, the
  admin stock colouring and the kiosk "low stock" label all use it.
- **Audit log** (`GET /api/audit?action=<prefix>&limit=`, admin): written in the same
  transaction as the change for order status changes (`order.<status>`), reset payment
  (`customer.reset_payment`), self-mark-paid (`customer.self_mark_paid`, actor `kiosk`),
  product create/update/delete/restock, changed settings, user create/update/delete
  (never the password itself) and backup create/download. New admin mutations should
  call `audit.record(...)` too.
- **Backups**: SQLite only. `backups.py` writes `kiosk-YYYYmmdd-HHMMSS[-N].db` with
  `VACUUM INTO` into `<db dir>/backups/`; settings `backup_interval_hours` (default 24,
  0 = off) and `backup_keep` (default 7). The scheduler thread first checks after 10 min,
  so tests never trigger it. Endpoints: `GET/POST /api/system/backups`,
  `GET /api/system/backups/{name}` (name must match the backup pattern).
  `GET /api/system/status` reports version (`APP_VERSION`/`GIT_COMMIT` env, else the
  image's `/app/release.json`), uptime, DB size, counts and backups.
- **Kiosk idle reset**: setting `kiosk_idle_seconds` (default 90, 0 = off). On the
  customer route, if there is anything to clear (cart, open dialog/cart, search,
  category), the kiosk shows a 10 s "Still there?" warning, then empties the cart and
  closes dialogs. Any touch/key cancels it.
- **Buy again**: `GET /api/customers/{username}` includes `favorites` (top 5 active
  products by quantity over non-cancelled orders); the lookup shows them as one-tap
  add-to-cart buttons.
- **Stock**: decremented at order creation; never negative (400 if insufficient).
- **Customer PINs (optional)**: a customer sets a 4-8 digit PIN from the kiosk lookup
  (`POST /api/customers/{username}/pin`; changing it needs `current_pin`). Stored only as
  `Argon2id(HMAC-SHA256(pepper, pin))` (`pins.py`, explicit params m=64 MiB, t=3, p=4).
  The pepper is `PIN_PEPPER` (>= 32 chars) or `pin_pepper.key` (0600) next to the database,
  never in the DB or the app's backups (gitignored; back it up separately - without it
  every PIN stops matching). With a PIN, `POST /api/orders` needs `customer_pin`, and the
  lookup and self-mark-paid need the `X-Customer-PIN` header: 428 = PIN required,
  403 "Wrong PIN", 429 after 5 wrong PINs (locked 15 min, counters in the `customers` row,
  `customer.pin_locked` audit). An admin token never bypasses the order PIN; the lookup
  skips it only with `?as_admin=true` plus a valid admin token (the admin panel's history).
  Admins can only remove a PIN (`POST /api/customers/{username}/reset-pin`), and only when
  no orders are pending (409 otherwise). `customers.has_pin` is exposed in `CustomerOut`.
- **Self-scanning**: setting `kiosk_barcode_scanning` (default `"false"`) shows the kiosk's
  "Scan barcode" field; the barcode lookup endpoint itself stays public.
- **Kiosk focus/Esc**: Buy and User lookup put the cursor in the username field (then the
  PIN field when one is asked for); Esc closes the open dialog, else the cart.
- **Customer usernames**: stored lowercase and NFC-normalized (`normalize_username`). New
  ones (`validate_new_username`, on first purchase) are at most 64 characters with no
  control/format characters (422 otherwise); existing customers are not re-validated.
- **Lookup/suggest is public** (no auth): `GET /api/customers/suggest` returns only matching
  usernames (max 20; `%`/`_` are matched literally) — never balances. `GET /api/customers/{username}` returns full history
  including balance. Both match usernames case-insensitively (stored lowercase).
- **Stats**: `CustomerStats` = order count, total spent/paid, balance (sum of pending), avg
  order, items bought, first/last order, top item, orders-per-month + spent/month,
  orders-by-weekday, busiest day, next due date. Balance shown in admin = pending total only.
- **Report exports**: `GET /api/reports/export.csv` is admin-only and exports sales totals,
  customer pending balances, current inventory/stock value, daily sales, customer/product
  rankings, and the latest payment. Keep CSV export aligned with the admin Reports view.

## Backend conventions

- `python:3.12`, pydantic v2, SQLAlchemy classic `Column(...)` models (no `Mapped[]`).
- Run migrations in `migrations.py` (idempotent, `migrate(engine)`, uses `ALTER TABLE`
  style adds with `IF NOT EXISTS`-guarded logic). Inspect `sqlite_master` before altering.
  New nullable/defaulted columns go in `ADDED_COLUMNS`, which `add_missing_columns()`
  applies on SQLite **and** PostgreSQL (high-traffic mode skips `migrate()`).
- Use `timeutil.utcnow()` — never `datetime.utcnow()`. All timestamps are naive UTC.
- Admin-only endpoints: `dependency=Depends(get_current_user)`. Customer-facing endpoints
  (orders POST, customers GET/suggest/{username}) are public by design — do not protect them.
  `PUBLIC_ENDPOINTS` in `tests/test_api.py` lists every intentionally public route; the
  route sweep test fails if any other endpoint answers without a valid token, so a new
  public endpoint must be added there deliberately.
- Tokens carry `pwv` (a fingerprint of the password hash, `security.token_claims`); a
  password change invalidates older tokens. Unknown usernames at login still run a bcrypt
  check (`_DUMMY_HASH`) so timing does not reveal valid usernames.
- Schema responses via Pydantic v2 (`model_validate`, `ConfigDict(from_attributes=True)` in schemas.py).
- `money = round(x, 2)` floats; keep it consistent.
- Do NOT modify `backend/requirements.txt` / `requirements-dev.txt` unless you also update
  the Dockerfiles pin-worthy versions — every dependency pinned there is used by Docker/CI.

## Frontend conventions

- **No build step, no JS modules.** Globals: `Store`, `API`, `Modal`, `Toast`, `AppInfo`, `Kiosk`,
  `Admin`, `Actions`, `Debug`. Script include order in `index.html` defines load order.
- `demo.js` is a `<script>` hook loaded **before** `api.js`. It is a no-op unless the
  host is `*.github.io` or the URL has `?demo=1`; in demo mode it replaces `window.fetch`
  with an in-memory mock of every endpoint the frontend calls (routes mirror
  `backend/routers/*`). `api.js` binds `const API`, so the mock must never reassign it —
  it intercepts at the `fetch` level. Keep `demo.js` in lockstep with backend routes and
  schemas when anything changes, and keep the seed data (products/customers/orders)
  consistent (order items must not exceed the seeded stock).
- **Event handling MUST use the `Actions` registry** (`data-action` attributes, delegated
  click/input listeners in `handlers.js`). Do NOT add `onclick=` inline handlers — they fight
  the CSP-less page and the codebase convention.
- `Store.cart` is persisted to `localStorage["kiosk_cart"]`. After page load the kiosk
  keeps showing the persisted cart.
- Routing is hash-based (`#/admin/dashboard` etc.) handled in `app.js::parseRoute`.
- Format money with the currency from `Store.settings.currency` (SUPPORTED_CURRENCIES in app.js).
- `Modal.open(content)`/`Modal.fill(content)`/`Modal.close()` for dialogs; `Toast.success/error`.
- Admin views get their container with `const app = this.mainFor("<view>"); if (!app) return;`
  **after** their awaits, so a slow render never overwrites a view the admin moved on to.
- The admin customers table columns, in order: User | Created | Orders | Orders/mo |
  Busiest day | Total paid | **Balance** | actions. E2E reads balance via `td:nth(6)`.

## Config & env vars

| Env | Effect |
| --- | --- |
| `DATABASE_PATH` | SQLite file (default `data/kiosk.db`) |
| `SECRET_KEY` | JWT signing key; if unset a random one is generated per process (tokens invalidate on restart) — never ship a hardcoded key |
| `ADMIN_PASSWORD` | Seed password for `admin`; **min 8 chars**, else ignored and a random one is generated + printed at first boot |
| `CORS_ORIGINS` | Comma-separated allowed origins (defaults to localhost/https+s hosts) |
| `PIN_PEPPER` | Secret (>= 32 chars) for customer PIN hashes; if unset, `pin_pepper.key` is created next to the DB. Changing/losing it invalidates every PIN |
| `KIOSK_TEST_DB` | pytest + e2e write their SQLite test DB wherever this points |
| `E2E_PYTHON` | Python used by the e2e harness to launch the backend |
| `CHROMIUM_PATH` | System Chromium/Chrome binary used by Playwright tests |

## Release process

1. Bump **CHANGELOG.md** with the new `[x.y.z] - <date>` section and update the test-count line in
   the Tests section.
2. Commit and push (or merge) to `main`. CI runs (backend + e2e + Docker/TLS smoke).
3. When that CI run succeeds, `release.yml` (workflow_run on CI) reads the newest
   `## [x.y.z]` heading in CHANGELOG.md. If `vX.Y.Z` does not exist yet, it tags the tested
   commit and calls `publish-images.yml`, which builds/pushes the GHCR images and then creates
   the GitHub Release titled `vX.Y.Z` with that CHANGELOG.md section as notes plus a
   "Full Changelog" compare link (no source assets). Do not tag by hand.
4. A `main` push whose newest CHANGELOG.md version is already tagged releases nothing, so do
   not add a new version heading until the change is ready to ship. `release.yml` can also be
   run manually (workflow_dispatch on `main`); pushing a `v*` tag by hand still runs
   `publish-images.yml` directly. Re-running the `release` job updates an existing release's notes.

The footer shows the running release and commit from `version.json`; the System page reads the
backend's `/app/release.json`. Both Dockerfiles write them with `scripts/release-info.sh`, which
takes the `APP_VERSION` / `GIT_COMMIT` build args when given (release workflow: tag version +
SHA; `compose.sh` / `build-offline.sh`: `git describe` + `git rev-parse`) and otherwise the newest
`CHANGELOG.md` version and the commit from `.git/HEAD` + refs, so a plain `docker compose up
--build` is stamped too (`dev` only without a CHANGELOG version). Both builds need the named build
context `repo` (`additional_contexts` in compose, `--build-context repo=.` for buildx), mounted
only for that step; the root `.dockerignore` limits it to the changelog, the script and
`.git/HEAD`/`refs`/`packed-refs`. The CI Docker smoke job builds without the args and checks both
values. The Pages workflow copies `CHANGELOG.md` and a `version.json` into `frontend/` before
upload, and the e2e harness serves the root `CHANGELOG.md`.

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
  - The lookup trigger (`#lookup-btn`) also has class `cart-btn` for styling; the cart
    click handler excludes it (it used to open the cart behind the lookup dialog).
  - The kiosk cart persists in `localStorage["kiosk_cart"]` across page loads; a failed/blocked
    checkout leaves items in the cart (add buttons become qty controls). Clear the key +
    reload when a prior step intentionally left the cart populated.
  - Any new customer-facing toast or new admin table column usually means updating e2e.js
    (balance is `td:nth(6)`; the unpaid-block toast text must match `orders.py` detail).
  - Any browser console/page error fails the e2e run unless it matches `expectedErrors` in
    e2e.js (the overdue-checkout 403 and the `ghost_user_x` lookup 404). A new step that
    intentionally triggers an error response must add a narrow pattern there.
  - `hasText` is a case-insensitive substring match ("Cola" matches "Chocolate Bar");
    use the `productRow(name)` helper for admin product rows.
  - Set `E2E_FAIL_SHOTS=<dir>` to save a screenshot (and log the URL) for each failed step.
  - The backup step writes `backups/` next to the e2e DB, and the PIN steps create
    `pin_pepper.key` there; the harness removes both at the end if the run created them
    (both are also gitignored).
  - API errors carry `err.status` (`api.js`); the kiosk PIN flow branches on 428/403/429.
- Local Python is frequently newer than 3.12; the pinned `requirements.txt` wheels may lack
  compatibility → install first `fastapi pydantic sqlalchemy uvicorn python-multipart
  pyjwt bcrypt pytest ruff mypy` as latest (loose) when developing locally, but never change
  the pinned requirement files themselves.
- The Docker+TLS smoke job needs a Docker daemon and cannot run on a machine without one —
  run it in CI or `docker compose up` locally.
- `#app` + admin views render via JS; there are no server-side templates.

## Agent skills

Reusable task skills are maintained for GitHub Copilot (`.github/skills/`), Claude Code
(`.claude/skills/`), and agents that discover the portable `.agents/skills/` directory.
Keep matching skill names and contents synchronized across these directories. The
`kiosk-development`, `kiosk-testing`, and `kiosk-release` skills cover common repo work;
this `AGENTS.md` remains the shared source of project conventions for agents that do not
load skills.

## Workflow conventions

- Make changes intentionally and small; run the three checks above.
- Keep the e2e suite in lockstep with behavior and admin-UI changes (it's the compatibility
  gate in CI).
- Do not commit generated files, the SQLite DB, `data/tls/` certs, or `node_modules`.