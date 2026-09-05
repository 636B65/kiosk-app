# Changelog

All notable changes to the Kiosk App are documented in this file.

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
