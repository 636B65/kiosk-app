# Kiosk App

A self-service retail kiosk with a customer-facing ordering screen and an admin
panel. Customers browse products, put them in a cart, and buy on a credit/tab
basis using a username. An admin user views sales, manages products, and tracks
customer balances.

The default deployment runs fully **offline (air-gapped)** via Docker Compose.
An optional PostgreSQL + Redis high-traffic stack is also available; it is never
enabled by default.

## Live demo

Try the frontend without a backend: **https://636b65.github.io/kiosk-app/**

GitHub Pages hosts the static frontend with an in-browser mock of the API
(`frontend/js/demo.js`), so the whole kiosk + admin panel is interactive with
sample data. Everything lives in your browser and **resets on reload**.

- Demo mode triggers automatically on GitHub Pages (or manually with `?demo=1`
  on any static server).
- Admin login for the demo: **`admin`** / `demo-password123`.

## Features

**Customer kiosk** (`/`)
- Browse products by category with live search
- Add/remove items in a cart with running totals
- Checkout by entering a username (auto-creates the customer on first purchase)
- Confetti celebration animation when an order is completed
- Purchases are added to the customer's balance (paid later at the counter)
- "User lookup" to view your balance, stats, and full monthly order history
  (typing a username suggests matching existing customers)
- All prices in **EUR** (admin can change the currency in Settings)
- Product photos uploaded by the admin (PNG/JPEG/WebP/GIF, up to 5 MB)
- Weekly specials: admin marks products with a special price and they appear at
  the top of the shop with the discounted price

**Admin panel** (`/#admin`)
- Dashboard: outstanding balance, today/week/month/all-time sales, low stock
- Products/Categories management, including product image upload and weekly
  specials (special price, listed at the top of the shop)
- Barcode-assisted product setup and kiosk checkout (a product can have multiple
  barcode aliases)
- Orders with paid/cancelled statuses and per-order item detail
- Customers: balances, per-customer stats, monthly history, reset payment
- Reports with outstanding balance, sales breakdown, customer/product leaderboards,
  recent payment insights, and CSV export of inventory, customer balances, and report data
  (inventory value is estimated using current selling prices, not product cost)
- User management (admin accounts)
- Optional customer self-service payment: when enabled in Settings, the kiosk lookup
  offers "I have paid everything" (off by default; it does not verify identity or payment)

## Architecture

The diagram compares the default single-host SQLite deployment with the
optional PostgreSQL + Redis high-traffic mode.

![Kiosk App system architecture](docs/kiosk-architecture.svg)

For a guided product overview, view the [sales presentation (PDF)](docs/kiosk-sales-presentation.pdf)
or open the [interactive HTML version](docs/kiosk-sales-presentation.html).
The editable source diagram is [available in draw.io format](docs/kiosk-architecture.drawio).

## Tech stack

| Layer     | Technology                                              |
|-----------|---------------------------------------------------------|
| Backend   | Python 3.12, FastAPI, SQLAlchemy, SQLite (default) or PostgreSQL, JWT auth |
| Frontend  | Vanilla HTML/CSS/JS served by nginx                     |
| Runtime   | Docker Compose (backend + nginx frontend)               |
| Storage   | SQLite database file bound-mounted at `./data/kiosk.db`; product images
              stored in `./data/product_images/` |

## Getting started

Requires Docker with the Compose plugin.

```bash
docker compose up --build
```

The same default mode is available through `./compose.sh`. Set
`HIGH_TRAFFIC=1` for the optional stack; see
[High-traffic mode](#high-traffic-mode) before switching a live installation.
`./compose.sh` also stamps the frontend footer with the current `git describe`
release and commit; a plain `docker compose up --build` shows `dev` unless
`APP_VERSION` / `GIT_COMMIT` are set. The footer's **Changelog** button opens
`CHANGELOG.md`.

- Customer kiosk: https://localhost
- Admin panel: https://localhost/#admin
- Plain HTTP on port 80 redirects to HTTPS (443).
- Default admin login: set the `ADMIN_PASSWORD` environment variable before
  first start; if unset a strong random password is generated and printed in
  the backend logs on first boot. **No hardcoded default credentials are used.**

The backend runs on http://localhost:8000 (bound to host loopback only; it is
**not** reachable from the LAN/WAN) and the frontend nginx proxies `/api/`
requests to it over Docker's internal network.

### Configuration

- **`SECRET_KEY`** (JWT signing key): set a strong, stable value before
  deployment, e.g. `docker compose run -e SECRET_KEY=$(openssl rand -hex 32) ...` or
  in your `.env` used by Compose. If unset, a random key is generated at startup
  (which invalidates existing sessions on restart). **Never use a hardcoded key.**
- **`ADMIN_PASSWORD`**: used to create the `admin` account on first boot. If unset,
  a random password is generated and printed in the backend logs.

### TLS / HTTPS

- The frontend serves HTTPS on port 443 and redirects port 80 to it.
- On **first** start (`docker compose up --build`) a **self-signed certificate**
  is generated into `./data/tls/server.crt` + `server.key` (bind-mounted to
  `/etc/nginx/certs` inside the container). Your browser will show a warning
  for self-signed certificates — accept it for local use.
- The certificate is **never overwritten** once it exists, so you can later
  replace it with a real (CA-signed) certificate by dropping your own
  `server.crt` / `server.key` into `./data/tls/` and restarting the frontend:
  `docker compose restart frontend`.

### Database

- Data lives in `./data/kiosk.db` (a bind mount, not baked into the image).
- Uploaded product images live in `./data/product_images/` (same bind mount, so
  they survive container rebuilds too).
- **Migrations run automatically** on backend startup — existing databases are
  upgraded in place, so updates never require a manual step or data wipe.
- Back up the DB (and product images) before updates:
  `cp -r data data.bak`

## High-traffic mode (optional)

The normal `docker compose up` / `./compose.sh up` command remains the single
SQLite + Nginx deployment. High-traffic mode is selected explicitly with
`HIGH_TRAFFIC=1 ./compose.sh ...`; it adds PostgreSQL, Redis, an HTTPS Nginx load
balancer, and internal Nginx/API services that can be scaled independently.
Redis caches public product, category, and settings GET responses for 30
seconds and invalidates them after successful write requests. PostgreSQL is the
shared database for API replicas. Product images remain in the shared `data`
volume.

This mode requires Docker Compose v2.24 or newer and a `.env` file containing
matching database credentials. URL-encode reserved characters in the password
inside `DATABASE_URL`:

```dotenv
POSTGRES_PASSWORD=replace-with-a-strong-password
DATABASE_URL=postgresql+psycopg://kiosk:replace-with-a-strong-password@postgres:5432/kiosk
SECRET_KEY=replace-with-a-stable-random-signing-key
```

**Switching from the default SQLite mode:** first back up `data/` and stop the
simple stack. Start only PostgreSQL and Redis, copy the SQLite contents to the
empty PostgreSQL database, then start the scaled stack. The migration command
refuses to overwrite a populated target unless `--replace-target` is explicitly
provided.

```bash
cp -r data data.before-high-traffic
./compose.sh down
HIGH_TRAFFIC=1 ./compose.sh up -d postgres redis
HIGH_TRAFFIC=1 ./compose.sh run --rm --no-deps backend \
  python migrate_database.py \
  --source sqlite:////app/data/kiosk.db \
  --target "$DATABASE_URL"
HIGH_TRAFFIC=1 ./compose.sh up -d --build --scale backend=3 --scale frontend=3
```

If `DATABASE_URL` is not exported in the shell, run the migration with the same
URL value as the one in `.env`. The original SQLite file is retained as a
pre-switch backup; after the copy, PostgreSQL is authoritative. Do not run
SQLite and PostgreSQL deployments concurrently against the same store.

**Switching back to SQLite:** stop all services that can accept writes, copy the
latest PostgreSQL data back into the SQLite file (replacing its now-stale
contents), then start the default stack. Back up both databases first.

```bash
cp -r data data.before-return-to-sqlite
HIGH_TRAFFIC=1 ./compose.sh stop backend frontend loadbalancer
HIGH_TRAFFIC=1 ./compose.sh run --rm --no-deps backend \
  python migrate_database.py \
  --source "$DATABASE_URL" \
  --target sqlite:////app/data/kiosk.db \
  --replace-target
HIGH_TRAFFIC=1 ./compose.sh down
./compose.sh up -d --build
```

Scale API and static frontend replicas with `--scale`. The Compose load
balancer resolves replica service names through Docker DNS, while Redis and
PostgreSQL remain shared services. This is a single-host Compose setup, not a
multi-host orchestrator; use an external load balancer/database or an
orchestrator if capacity needs to span hosts.

## Project layout

```
backend/            FastAPI application (models, routers, auth, seed, migrations)
  routers/          API route modules (auth, categories, customers, orders, ...)
frontend/           Static customer kiosk + admin panel (HTML/CSS/JS, nginx)
docker-compose.yml  Services: backend (8000) + frontend (80->443 HTTPS)
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
ruff check .
mypy
```

**End-to-end tests** (Playwright against a live backend + nginx-proxied
frontend, no Docker needed):

```bash
cd tests/e2e
npm install
# requires a Python 3.12 interpreter with backend deps installed
E2E_PYTHON=python CHROMIUM_PATH=/usr/bin/chromium npm test
```

**Docker + TLS smoke test** (the full delivered stack, incl. the self-signed
certificate, HTTP->HTTPS redirect, CSP header, and admin login over TLS):

```bash
docker compose up -d --build
cd tests/e2e && CHROMIUM_PATH=/usr/bin/chromium ADMIN_PASSWORD=smoke-test-password node https-smoke.js
```

The e2e harness spawns its own backend and a static/proxy server, then drives
`chromium`. Set `E2E_PYTHON` to a Python that can run the backend
(`requirements-dev.txt` installed), and `CHROMIUM_PATH` to a Chromium binary.
