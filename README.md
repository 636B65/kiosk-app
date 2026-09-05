# Kiosk App

A self-service retail kiosk with a customer-facing ordering screen and an admin
panel. Customers browse products, put them in a cart, and buy on a credit/tab
basis using a username. An admin user views sales, manages products, and tracks
customer balances.

Built to run fully **offline (air-gapped)** via Docker Compose.

## Features

**Customer kiosk** (`/`)
- Browse products by category with live search
- Add/remove items in a cart with running totals
- Checkout by entering a username (auto-creates the customer on first purchase)
- Purchases are added to the customer's balance (paid later at the counter)
- "User lookup" to view your balance, stats, and full monthly order history
- All prices in **EUR** (admin can change the currency in Settings)
- Product photos uploaded by the admin (PNG/JPEG/WebP/GIF, up to 5 MB)
- Weekly specials: admin marks products with a special price and they appear at
  the top of the shop with the discounted price

**Admin panel** (`/#admin`)
- Dashboard: outstanding balance, today/week/month/all-time sales, low stock
- Products/Categories management, including product image upload and weekly
  specials (special price, listed at the top of the shop)
- Orders with paid/cancelled statuses and per-order item detail
- Customers: balances, per-customer stats, monthly history, reset payment
- Reports with outstanding balance and sales breakdown
- User management (admin accounts)

## Tech stack

| Layer     | Technology                                              |
|-----------|---------------------------------------------------------|
| Backend   | Python 3.12, FastAPI, SQLAlchemy, SQLite, JWT auth      |
| Frontend  | Vanilla HTML/CSS/JS served by nginx                     |
| Runtime   | Docker Compose (backend + nginx frontend)               |
| Storage   | SQLite database file bound-mounted at `./data/kiosk.db`; product images
              stored in `./data/product_images/` |

## Getting started

Requires Docker with the Compose plugin.

```bash
docker compose up --build
```

- Customer kiosk: http://localhost:8080
- Admin panel: http://localhost:8080/#admin
- Default admin login: `admin` / `admin123` (change before production)

The backend runs on http://localhost:8000 and the frontend proxies `/api/`
requests to it.

### Database

- Data lives in `./data/kiosk.db` (a bind mount, not baked into the image).
- Uploaded product images live in `./data/product_images/` (same bind mount, so
  they survive container rebuilds too).
- **Migrations run automatically** on backend startup — existing databases are
  upgraded in place, so updates never require a manual step or data wipe.
- Back up the DB (and product images) before updates:
  `cp -r data data.bak`

## Project layout

```
backend/            FastAPI application (models, routers, auth, seed, migrations)
  routers/          API route modules (auth, categories, customers, orders, ...)
frontend/           Static customer kiosk + admin panel (HTML/CSS/JS, nginx)
docker-compose.yml  Services: backend (8000) + frontend (8080)
build-offline.sh    Build images + bundle for an air-gapped target
deploy-offline.sh   Load + start the bundled images on an offline machine
```

## Air-gapped (offline) deployment

The app makes **no outbound network calls at runtime** and only talks to its own
backend over Docker's internal network. The internet is required only to *build*
the images. This makes it easy to ship to an isolated machine.

On an internet-connected machine:

```bash
./build-offline.sh [amd64|arm64] [--include-data]
```

This produces a single `offline/kiosk-app.tar.gz` containing the built images,
`docker-compose.yml`, and `deploy-offline.sh`.

On the offline target (with Docker installed):

```bash
./deploy-offline.sh kiosk-app.tar.gz
```

It unpacks the bundle, verifies checksums, backs up and preserves your live
database, loads the images, and starts the services. `--no-verify` skips the
checksum check. See the scripts for details.

> **First deploy:** pass `--include-data` to bundle your current DB. For
> **updates**, do not use `--include-data` — the live DB on the target is
> preserved and migrated automatically.

## Container images (GitHub Packages / GHCR)

On every `v*` release tag, GitHub Actions builds the two images and publishes
them to the GitHub Container Registry (GHCR):

- `ghcr.io/636b65/kiosk/backend`
- `ghcr.io/636b65/kiosk/frontend`

Images are tagged with the SEMVER version (`v1.0.1` -> `1.0.1`) and `latest`,
and are built for `linux/amd64`.

`docker-compose.yml` still builds from source locally, so GHCR is an optional
distribution channel rather than a hard dependency (useful for air-gapped
deployments where you pull once on a connected machine).

To pull images directly:

```bash
docker login ghcr.io -u <your-github-username> -G # or a PAT with read:packages
docker pull ghcr.io/636b65/kiosk/backend:1.0.1
docker pull ghcr.io/636b65/kiosk/frontend:1.0.1
```

Note: GHCR package names are lowercase regardless of the account spelling.

## Development

The backend uses FastAPI with pinned dependencies in `backend/requirements.txt`.
Run tests/verification with the FastAPI `TestClient` and Playwright browser
tests, or simply exercise `docker compose up --build`.

## Testing

GitHub Actions runs both suites automatically on push to `main` and on pull
requests (see `.github/workflows/ci.yml`). Run them locally:

**Backend API tests** (pytest + FastAPI TestClient):

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests -v
```

**End-to-end tests** (Playwright against a live backend + nginx-proxied
frontend, no Docker needed):

```bash
cd tests/e2e
npm install
# requires a Python 3.12 interpreter with backend deps installed
E2E_PYTHON=python CHROMIUM_PATH=/usr/bin/chromium npm test
```

The e2e harness spawns its own backend and a static/proxy server, then drives
`chromium`. Set `E2E_PYTHON` to a Python that can run the backend
(`requirements-dev.txt` installed), and `CHROMIUM_PATH` to a Chromium binary.
