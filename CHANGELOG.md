# Changelog

All notable changes to the Kiosk App are documented in this file.

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
