# Changelog

All notable changes to the Kiosk App are documented in this file.

## [Unreleased]

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

#### Changed
- None (initial release).

#### Fixed
- None (initial release).

#### Security notes
- Before shipping, change the default `SECRET_KEY` (in `docker-compose.yml`) and
  the default admin password.
