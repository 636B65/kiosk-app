# Changelog

All notable changes to this project are documented here. Versions follow
[Semantic Versioning](https://semver.org/); the newest `## [x.y.z]` heading is
what `release.yml` tags and publishes.

## [1.0.0] - 2026-11-11

First release of the kiosk as microservices (a rewrite of
[kiosk-app](https://github.com/636B65/kiosk-app) 1.x for Kubernetes).

### Services

- **auth-service**: admin users, login with per-IP rate limiting, JWT issuing,
  token introspection for the other services (password changes revoke tokens).
- **catalog-service**: categories, products (weekly specials, barcodes, cost
  prices hidden from the public, images), deliveries (restocks), inventory
  counts, and the atomic all-or-nothing stock reservation used by checkout.
- **customer-service**: customers, username rules, PINs (Argon2id over a
  peppered HMAC, lockout after 5 wrong PINs), public lookup with history/stats/
  favorites, reset payment, reset PIN, self-mark-paid.
- **order-service**: tab checkout (PIN -> overdue check -> stock reservation ->
  order), status changes with compare-and-set, stock restored on cancel,
  per-customer statistics and settlement.
- **settings-service**: store-wide settings (currency, payment due date, kiosk
  idle reset, barcode scanning, backup schedule).
- **audit-service**: the audit log, fed by every service through a
  transactional outbox.
- **report-service**: summary, margins, top products/customers, sales by day,
  shrinkage, reorder suggestions and the CSV exports (sales or paid basis).
- **system-service**: aggregated `/api/health`, the admin System page and
  backups (`pg_dump` of every service database into one archive, scheduled).
- **frontend**: the unchanged vanilla-JS kiosk/admin UI served by nginx, which
  is also the API gateway routing `/api/*` to the services.

### Platform

- Kustomize base with a dev and a prod overlay, Argo CD Applications and an
  ApplicationSet, NetworkPolicies, non-root pods with read-only root
  filesystems, liveness/readiness probes.
- One Postgres StatefulSet with a database per service (swap for a managed
  database by changing `DATABASE_URL`).
- docker compose stack for local development; GitHub Actions CI (lint, 40
  in-process integration tests across all services, manifest validation,
  image builds, compose smoke) and image publishing to GHCR. 53 tests in all.
