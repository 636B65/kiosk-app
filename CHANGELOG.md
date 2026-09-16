# Changelog

All notable changes to the Kiosk App are documented in this file.

## [1.0.14] - 2026-09-16

### Added
- **`AGENTS.md`** with contributor/AI-agent guidance: quick commands (tests, lint, mypy,
  e2e), architecture and layout, business rules (unpaid-order block, due-date, weekly
  specials), backend/frontend conventions, config/env vars, release process, and the known
  e2e/testing gotchas. Cloning the repo is now enough to spin up development and releases.
- Minor: refreshed CI + e2e reporting so a failing step keeps the assertion detail.

### Tests
- All backend tests (41), the full e2e suite (24 steps), ruff, mypy, and JS syntax
  validation pass.

## [1.0.13] - 2026-09-16

### Added
- **Store-wide payment due date** (`backend/due_dates.py`, `backend/routers/orders.py`,
  `backend/routers/settings.py`). A new `payment_due_date` setting (an ISO date, e.g.
  `2026-10-15`) sets the date by which outstanding balances must be paid. While it is
  set, a new order's `due_date` column is stamped with that date; the setting is empty
  by default, meaning orders have **no end date**.
  - Customers with **any unpaid order** are blocked from placing a new order until their
    balance is settled (`403` at checkout).
  - Admin can set/clear the due date on the Settings page (empty = no end date) and see
    the next due date in the customer modal.
  - Kiosk checkout confirmation shows a "Next payment due" reminder when a balance exists
    and a due date is configured.
- **Per-user purchase statistics** (`backend/routers/customers.py`, `backend/schemas.py`,
  `frontend/js/app.js`, `frontend/js/admin.js`). Each customer now receives:
  - `avg_orders_per_month` and `busiest_day` (weekday name).
  - `orders_per_month` (list of `{month, orders}`) and `orders_by_weekday` (list of
    `{day, orders}`, Monday–Sunday order).
  - `next_due_date` computed from the current balance.
  Admin: customers table shows **Orders/mo** and **Busiest day** columns; the per-user
  modal now displays all extended stats and the next due date. Kiosk lookup and
  order-complete confirmation both show the due date when a balance is outstanding.
- **Due date column on orders** (`backend/models.py`, `frontend/js/admin.js`).
  The admin Orders table now includes a **Due** column; overdue pending orders are
  highlighted in red with a ⚠ indicator.
- **Database migration** (`backend/migrations.py`). Adds `due_date` column to the
  `orders` table (nullable, backfilled from the configured `payment_due_date` if any,
  otherwise left empty).
- **Unit tests for due-date parsing** (`backend/tests/test_due_dates.py`). Covers
  empty/invalid values (→ no due date), ISO date parsing, and end-of-day due time.

### Tests
- Existing tests adapted to the new single-pending-order business rule; several tests
  now explicitly reset a customer's payment between purchases where two pending orders
  were previously required.
- New backend tests: `test_due_date_absent_by_default`,
  `test_checkout_blocked_until_marked_paid`,
  `test_cancel_preserves_previous_state`, `test_payment_due_date_setting_honored`,
  `test_customer_monthly_and_weekday_stats`, `test_summary_exposes_next_due_date`, and
  all `test_due_dates.py` unit tests.
- e2e: the second kiosk buy now asserts the unpaid-checkout block toast; the admin
  customers-table balance assertion tracks the new Orders/mo + Busiest day columns; a
  new step verifies a customer can buy again once the admin resets their payment.
- All backend tests (41), the full e2e suite (24 steps), ruff, mypy, and JS syntax
  validation pass.

## [1.0.12] - 2026-09-08

### Added
- **User-lookup autocomplete** (kiosk): while typing a username in the
  "Payment lookup" modal, matching existing customer usernames are suggested
  (debounced 180 ms) and can be picked with a click.
  - New public endpoint `GET /api/customers/suggest?q=<prefix>&limit=8`
    (`backend/routers/customers.py`): returns existing usernames that start
    with the typed prefix (case-insensitive, ordered, capped at 20). It returns
    **only usernames** — never balances/history — and an empty query returns
    nothing, so the kiosk can't dump the customer list.
  - Frontend: `Kiosk.suggestLookup` / `pickLookup` (`frontend/js/customer.js`),
    new `data-action-input="kiosk-lookup-suggest"` and
    `data-action="kiosk-lookup-pick"` handlers (`frontend/js/handlers.js`),
    suggestion dropdown styling (`frontend/css/styles.css`).
  - This only applies to the lookup modal; the checkout username field is
    unchanged.
- **Lookup right after buying** (kiosk): the order-complete confirmation now
  offers a "**Look up user**" button that opens the (autocompleting) user
  lookup, so a customer can type their username and check their balance/history
  immediately after checking out. The "New Order" button is unchanged.

### Tests
- Backend: `test_customer_suggest_prefix` verifies prefix matching,
  case-insensitivity, empty-result, empty-query and `limit` behaviour.
- e2e: new steps verify typing a prefix shows an `alice` suggestion and that
  clicking it opens the customer history, and that "Look up user" from the
  order-complete modal opens the lookup and shows history after buying.

All backend tests (30), ruff, mypy, and the full e2e suite (24 steps) pass.

## [1.0.11] - 2026-09-08

### Security (pen-test follow-up)
- **Critical: order quantity abuse fixed** (`backend/routers/orders.py`,
  `backend/schemas.py`). `POST /api/orders` is unauthenticated (kiosk checkout)
  and accepted **negative or zero** quantities — the stock check only rejected
  quantities exceeding available stock. A customer could submit `quantity: -50`
  to drive line totals negative (wiping their own or anyone's balance) and to
  **inflate product stock** (`stock -= -50`). Quantities are now validated at
  the schema layer: must be `>= 1` and `<= 1000`, and an order is capped at 50
  line items with notes limited to 500 chars.
- **High: backend port no longer exposed on the host network**
  (`docker-compose.yml`). The backend was published as `8000:8000`, i.e.
  reachable from any LAN machine, bypassing nginx's security headers (CSP/HSTS)
  and letting attackers hammer admin login / API without the reverse proxy.
  It now binds to `127.0.0.1:8000:8000` (loopback only); the frontend still
  proxies `/api/` to it over Docker's internal network.
- **Medium: login rate limiter no longer trusts a spoofed `X-Forwarded-For`**
  (`backend/routers/auth.py`). The limiter keyed on the *first* header hop,
  which the client controls, so an attacker could reset the lockout by changing
  the header. It now keys on the **last** hop — the real client IP that nginx
  appends via `$proxy_add_x_forwarded_for` — making the 5-attempt/15-minute
  lockout effective.
- **Medium: minimum password length enforced** (`backend/schemas.py`,
  `backend/seed.py`). Admin-created users and password changes now require >= 8
  characters (422 otherwise). The initial `admin` bootstrap rejects a too-short
  `ADMIN_PASSWORD` (< 8 chars) and falls back to a generated random password
  instead of silently using a weak one.
- **Defense**: nginx `client_max_body_size 6m` set on the HTTPS server
  (`frontend/nginx.conf`) so oversized request bodies (a memory/disk exhaust
  vector via the public proxy) are rejected at the edge.

### Tests
- New backend regression tests: spoofed `X-Forwarded-For` does not defeat the
  rate limiter; negative/zero/oversized quantities are rejected without side
  effects (stock intact, no phantom customer); oversized order item lists are
  rejected; short passwords are rejected on create and update.

All backend API tests, ruff, and mypy pass.

## [1.0.10] - 2026-09-06

### Changed
- **Strict CSP restored without breaking the UI** (fixes the 1.0.9 trade-off).
  In 1.0.9 the Content-Security-Policy in `frontend/nginx.conf` was relaxed to
  `script-src 'self' 'unsafe-inline'` because the frontend used inline
  `onclick`/`oninput` attributes, which the earlier strict `script-src 'self'`
  policy (introduced in 1.0.8) silently blocked — making every Settings save and
  kiosk/Admin button appear dead.
  - The UI no longer uses inline event handlers at all. A new
    `frontend/js/handlers.js` module registers the handlers behind external,
    delegated data-attributes (`data-action` for clicks, `data-action-input` for
    typing) and dispatches them to the relevant object (`Modal`, `Kiosk`,
    `Admin`). All inline `onclick`/`oninput` handlers in `admin.js` and
    `customer.js` were converted.
  - `frontend/nginx.conf` now serves the original strict policy again
    (`script-src 'self'` with **no** `unsafe-inline`), keeping the XSS hardening
    while the app remains fully operable. The debug panel also starts collapsed
    (FAB only) so it never overlaps the kiosk checkout.
  - `tests/e2e/https-smoke.js` keeps its strict-CSP assertion (no
    `unsafe-inline`), which now passes legitimately. The Docker + TLS smoke test
    and the full e2e suite pass with the strict policy.

All backend API tests and end-to-end browser tests pass.

## [1.0.9] - 2026-09-06

### Added
- **Admin-toggleable Debug / verbose mode** (`frontend/js/debug.js`): admins can
  enable 🐞 Debug mode in **Settings**, which is persisted as a
  `debug_mode` setting and applies to every screen (customer kiosk and admin).
  When enabled, a collapsible floating panel shows:
  - page load times: `DOMContentLoaded`, `Load`, First Contentful Paint;
  - per-route render times for the current SPA page;
  - a live log of every API request (time, method, path, status, duration)
    with slow/failed calls highlighted;
  - JS heap memory usage and DOM node count;
  - network statistics (resource count, transferred bytes, images loaded).
  - The flag is read once at startup and re-polled every 15 s so all connected
    kiosk screens pick up a change without a reload. Only admins can toggle it
    (`PUT /api/settings/debug_mode` requires an authenticated session); the
    value itself is served with the public settings payload. Route rendering in
    `frontend/js/app.js` is measured via `debug.js`.

### Fixed
- **CSP regression that disabled the admin and kiosk UI** (`frontend/nginx.conf`):
  1.0.8 shipped `Content-Security-Policy` with `script-src 'self'` and **no**
  `unsafe-inline`, which blocked the frontend's inline `onclick`/`oninput`
  handlers. After a rebuild every inline-driven action silently stopped working:
  admin Settings could not be saved (store name, currency, debug toggle), and
  kiosk buttons such as "New Order" and modal "Cancel" after a user lookup did
  nothing. `script-src` now includes `'unsafe-inline'` (the rest of the policy
  is unchanged), restoring all inline event handlers. Verified end-to-end in a
  browser against the real backend (no CSP violations).

All backend API tests and end-to-end browser tests pass.

## [1.0.8] - 2026-09-05

### Changed
- **Replaced `python-jose` with `PyJWT`** (`backend/requirements.txt`): the
  jose library is effectively unmaintained upstream. Token creation and
  verification in `backend/security.py` now use `pyjwt==2.13.0`, and JWT
  `sub` claims are validated to be strings (a forged token with a non-string
  `sub` is rejected) — a genuine hardening caught by type checking.
- **Removed `datetime.utcnow()` deprecations**: new `backend/timeutil.py`
  provides `utcnow()` (UTC time as a naive datetime, matching how SQLite
  stores timestamps) and replaces the deprecated `datetime.utcnow()` in
  `models.py`, `security.py`, and the orders/customers/reports routers.
- **Linting + type checking added** (`backend/requirements-dev.txt`):
  - `ruff` configuration in `backend/pyproject.toml`; fixed findings
    (unused imports, `== True` comparisons, missing trailing newlines).
  - `mypy` configuration covering the pure-logic modules (`config`,
    `timeutil`, `schemas`, `security`, `seed`). Both run in CI.
  - Note: the SQLAlchemy models/routers use the classic 1.x `Column`/`Query`
    style which mypy cannot type-check cleanly; they are excluded pending a
    SQLAlchemy 2.0 `Mapped` migration (see `pyproject.toml`).
- **CSP hardening** (`frontend/nginx.conf`): `script-src` is now `'self'`
  with **no** `unsafe-inline`/`unsafe-eval` — inline script execution (the
  main XSS sink) is disabled. The frontend uses only external scripts.
  `style-src 'unsafe-inline'` is kept for now because the UI sets ~45 inline
  styles from JS templates; moving them to CSS classes is a follow-up.
  Inline bars for the confetti canvas were converted to CSSOM property
  assignments (`frontend/js/app.js`).
- **CI: Docker + TLS smoke test** (`.github/workflows/ci.yml`): builds and
  starts the real compose stack, verifies `nginx -t`, the self-signed cert is
  generated under `data/tls/`, HTTP 80 -> 301 -> HTTPS 443, the certificate is
  **not overwritten** on restart, and a new `tests/e2e/https-smoke.js` drives
  Chromium over HTTPS (CSP header, kiosk rendering, admin login).

All backend API tests and end-to-end browser tests pass.

## [1.0.7] - 2026-09-05

### Changed
- **HTTPS by default with self-signed certificate**:
  - The frontend now serves HTTPS on port **443** and redirects plain HTTP on
    port **80** to it (`301`). The host port mapping changed from `8080` to
    `80`/`443`.
  - On first start (`docker compose up --build`) a **self-signed certificate**
    is generated into `./data/tls/server.crt` + `server.key`
    (`openssl req -x509`, valid 10 years, bind-mounted to `/etc/nginx/certs`).
  - The certificate is **never overwritten** once it exists: replace it by
    dropping your own `server.crt`/`server.key` into `./data/tls/` and running
    `docker compose restart frontend` (e.g. a real CA-signed certificate).
  - `frontend/nginx.conf`: separate `443 ssl` server block, `Strict-Transport-
    Security` header added, `/api/` proxy sends `X-Forwarded-Proto: https`.
  - `frontend/Dockerfile`: installs `openssl`; new
    `docker-entrypoint.d/40-create-selfsigned-cert.sh` generates the cert on
    first boot only.
- **Backend CORS defaults** now allow `https://localhost` / `http://localhost`
  (and `127.0.0.1` equivalents) instead of the removed `:8080` origins.
- **Offline deployment**: `deploy-offline.sh` reports the new `https` URLs and
  preserves an existing `./data/tls` certificate across re-deploys.

All backend API tests and end-to-end browser tests pass.

## [1.0.6] - 2026-09-05

### Changed
- **Dependency updates (via Dependabot):**
  - `fastapi` 0.115.6 -> 0.141.1 (`backend/requirements.txt`)
  - `uvicorn[standard]` 0.34.0 -> 0.52.4 (`backend/requirements.txt`)
  - `sqlalchemy` 2.0.36 -> 2.0.52 (`backend/requirements.txt`)
  - `pydantic` 2.10.4 -> 2.13.5 (`backend/requirements.txt`)
  - `pydantic-settings` 2.7.0 -> 2.15.0 (`backend/requirements.txt`)
  - `bcrypt` 4.2.1 -> 5.0.0 (`backend/requirements.txt`)
  - `python-jose[cryptography]` 3.4.0 -> 3.5.0 (`backend/requirements.txt`)
  - `python-multipart` 0.0.31 -> 0.0.32 (`backend/requirements.txt`)
  - `pytest` 9.0.3 -> 9.1.1 (`backend/requirements-dev.txt`)
  - `httpx` 0.28.1 replaced by `httpx2` 2.12.0 (`backend/requirements-dev.txt`):
    starlette 1.x's `TestClient` now uses `httpx2` instead of `httpx`.
  - GitHub Actions: `actions/checkout` v4 -> v7, `actions/setup-python` v5 -> v7,
    `actions/setup-node` v4 -> v7, `docker/setup-qemu-action` v3 -> v4,
    `docker/metadata-action` v5 -> v6.
- **Pydantic V2 cleanup**: `backend/schemas.py` migrated from the deprecated
  class-based `Config` settings to `model_config = ConfigDict(...)`, removing the
  deprecation warnings that appear with pydantic 2.13.

All backend API tests and end-to-end browser tests pass with the updated
dependencies.

## [1.0.5] - 2026-09-05

### Security hardening

- **JWT signing key**: the app previously shipped with a hardcoded
  `SECRET_KEY` (`change-me-in-production`) that allowed anyone to forge valid
  admin tokens. `SECRET_KEY` is now read from the environment, and when unset a
  random key is generated at startup (existing sessions are then invalidated on
  restart). `docker-compose.yml` passes it through from the host environment,
  and empty values are rejected.
- **Default admin credentials removed**: the seed no longer creates the admin
  with the well-known `admin`/`admin123` password. The initial password is taken
  from `ADMIN_PASSWORD`, or a strong random password is generated and printed in
  the backend logs on first boot.
- **Deactivated users**: existing JTWs for a user who is later deactivated are
  now rejected immediately (previously the token stayed valid until expiry).
- **CORS**: the API no longer allows `allow_origins=["*"]` together with
  credentials; it is restricted to the kiosk origin (`http://localhost:8080`,
  configurable via `CORS_ORIGINS`).
- **Login rate limiting**: login endpoints now lock out a client IP after 5
  failed attempts for 15 minutes (HTTP 429 with `Retry-After`).
- **Image upload validation**: uploaded product images are verified against
  their file-signature magic bytes in addition to the declared `Content-Type`;
  disguised files (e.g. HTML/scripts sent as `image/png`) are rejected.
- **Security headers**: nginx now sends `Content-Security-Policy`,
  `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, and
  `Permissions-Policy`.

### Changed
- `backend/config.py`, `backend/seed.py`, `backend/security.py`,
  `backend/main.py`, `backend/routers/auth.py`, `backend/routers/products.py`,
  `docker-compose.yml`, `frontend/nginx.conf`.
- Tests updated (backend and e2e) to use the new admin bootstrap; new regression
  tests added for the security controls.

All backend API tests and end-to-end browser tests pass.

## [1.0.4] - 2026-09-05

### Added
- **Confetti on order completion**: the kiosk fires a confetti burst over the
  order-confirmation modal when a customer completes a purchase. The effect is
  a self-contained canvas animation (no external libraries, so the app remains
  fully offline-capable).

All backend API tests and end-to-end browser tests pass.

## [1.0.3] - 2026-09-05

### Added
- **Configurable store currency**: the admin picks the display currency in
  Settings (23 currencies supported, default **EUR**). All prices, cart totals,
  balances, reports, and dashboards render in the selected currency.
- **Product image uploads**:
  - Admins can upload a product photo (PNG/JPEG/WebP/GIF, max 5 MB) from the
    product form and remove it again.
  - Photos are stored on disk next to the database (`./data/product_images/`)
    in the existing bind mount, so they survive container rebuilds.
  - Products now expose an `image_url`; the kiosk and admin list show the photo
    (with a letter placeholder when none is set).
  - New endpoints: `POST /api/products/{id}/image` and
    `DELETE /api/products/{id}/image`; images are served under `/api/images/`.
- **Weekly specials**:
  - Admins can mark a product as a weekly special and set a special price.
  - Special products are listed at the **top of the shop** with a badge and the
    discounted price (original price struck through).
  - Carts and orders charge the special price; order lines, customer balances,
    and reports all reflect it.

### Changed
- Product API responses include `image_url`, `is_weekly_special`, and
  `special_price`. A startup migration adds the new columns to existing
  databases in place (see `backend/migrations.py`).
- Order pricing uses the effective (special) price of weekly-special products.

### Notes
- Existing databases are upgraded automatically on backend startup; no manual
  migration step is needed.

All backend API tests and end-to-end browser tests pass.

## [1.0.2] - 2026-09-03

### Added
- **GitHub Packages (GHCR) publishing pipeline** (`.github/workflows/publish-images.yml`):
  - Builds and publishes `ghcr.io/636b65/kiosk/backend` and
    `ghcr.io/636b65/kiosk/frontend` (linux/amd64) on every `v*` release tag.
  - Images are tagged with the SEMVER version (e.g. `1.0.2`) and `latest`.
  - `docker-compose.yml` continues to build from source; GHCR is an optional
    distribution channel.

## [1.0.1] - 2026-09-03

### Changed
- **Dependency updates (via Dependabot):**
  - `python-jose[cryptography]` 3.3.0 -> 3.4.0 (`backend/requirements.txt`)
  - `python-multipart` 0.0.20 -> 0.0.31 (`backend/requirements.txt`)
  - `pytest` 8.3.4 -> 9.0.3 (`backend/requirements-dev.txt`)

All backend API tests and end-to-end browser tests pass with the updated
dependencies.

## [1.0.0] - 2026-09-03

### Initial production release

Initial commit of the complete kiosk application.

#### Added
- **Backend (FastAPI + SQLAlchemy + SQLite):**
  - Product, category, order, customer, user, and setting models.
  - REST routers for auth, categories, products, orders, customers, reports,
    settings, and users.
  - JWT-based authentication with bcrypt password hashing.
  - Customer tab/credit model: orders are `pending` (add to a customer's
    balance) until marked `paid` or reset by an admin.
  - Customers are auto-created on first purchase; usernames are normalized to
    lowercase and deduplicated case-insensitively.
  - Automatic startup migrations (see `backend/migrations.py`) that upgrade an
    existing database in place.
  - Seed data: default admin (`admin`/`admin123`), store settings, sample
    products and categories.
- **Customer kiosk (vanilla JS + nginx):**
  - Browse products by category and search.
  - Cart with quantities and SEK total (no tax).
  - Checkout by username prompt with balance display.
  - "User lookup" showing balance, per-customer stats, and order history.
- **Admin panel:**
  - Dashboard with outstanding balance and sales stats.
  - Product/category/user management.
  - Orders view with status actions (mark paid / cancel) and item detail.
  - Customers view with balances, stats, monthly history, and reset payment.
  - Settings (store name, receipt footer).
- **Operations:**
  - Docker Compose setup (backend on 8000, nginx frontend on 8080).
  - Air-gapped deployment scripts (`build-offline.sh`, `deploy-offline.sh`)
    for shipping to offline machines.
  - `.gitignore` / `.dockerignore` files.
- **Testing / CI:**
  - Backend API tests with pytest + FastAPI TestClient
    (`backend/tests/test_api.py`).
  - End-to-end Playwright browser tests (`tests/e2e/e2e.js`).
  - GitHub Actions workflow (`.github/workflows/ci.yml`) running both suites on
    every push to `main` and on pull requests.

#### Changed
- None (initial release).

#### Fixed
- None (initial release).

#### Security notes
- Before shipping, change the default `SECRET_KEY` (in `docker-compose.yml`) and
  the default admin password.
