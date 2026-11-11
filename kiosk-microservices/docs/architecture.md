# Architecture

## Principles

- **Database per service.** No service reads another service's tables. Postgres
  hosts six databases (`auth`, `catalog`, `customers`, `orders`, `settings`,
  `audit`); the report and system services have none.
- **One API contract.** The gateway (nginx in the frontend image) routes
  `/api/<prefix>` to the owning service; the public and admin routes are exactly
  the monolith's. Services call each other only on `/internal/*` routes, guarded
  by the shared `INTERNAL_TOKEN` header and never routed by the gateway.
- **Synchronous calls where a decision needs an answer now** (PIN check, stock
  reservation, due date), **asynchronous events where it does not** (audit
  entries, deferred stock releases) through a transactional outbox.
- **Fail closed on auth.** Every service verifies the JWT signature locally and
  asks the auth service whether the account is still active and the password
  unchanged (`pwv` claim). Positive answers are cached for `AUTH_CACHE_SECONDS`
  (60); an unreachable auth service means 401.

## Checkout (POST /api/orders)

```
kiosk ─► order-service
          1. customer-service  POST /internal/customers/resolve {username, pin}
             - normalises the username, creates the customer on first purchase
             - enforces the PIN: 428 PIN required / 403 Wrong PIN / 429 locked
               (failed attempts are committed even though the order fails)
          2. settings-service  GET /api/settings  -> payment_due_date
             - overdue (date passed) AND a pending order here -> 403 unpaid block
          3. catalog-service   POST /internal/stock/reserve {items}
             - one transaction, one `UPDATE ... SET stock = stock - q WHERE stock >= q`
               per line; any shortfall rolls back every line (400 with the
               product name and what is left) and returns the price snapshot
          4. order row + lines (unit_price, unit_cost snapshot) committed here
             - if the write fails the stock is released again (directly, or via
               the outbox when the catalog is unreachable)
```

Stock therefore never goes negative and simultaneous checkouts never oversell
(covered by `test_simultaneous_checkouts_never_oversell`). A customer row may
exist without an order (resolve succeeded, the stock reservation failed); that
is harmless and the same username is reused next time.

## Status changes, cancel and settle

`PATCH /api/orders/{id}/status` keeps the monolith's rules: pending -> paid /
cancelled, paid -> pending / cancelled, cancelled is final (409), compare-and-set
on the previous status, optional `expected_status` from the admin buttons. A
pending -> cancelled transition commits first and then asks the catalog to
release the stock; if the catalog is down, a `stock.release` outbox event retries
until it succeeds, so cancelled stock is always returned.

Reset payment (`POST /api/customers/{u}/reset-payment`) and self-mark-paid live in
the customer service, which delegates the settlement to
`POST /internal/orders/customers/{u}/settle` (compare-and-set per order, so an
order cancelled at the same moment never ends up paid).

## Audit log

`kiosk_common.audit.record()` writes the entry into the service's own `outbox`
table in the same transaction as the change. A relay thread in each service
(`OUTBOX_INTERVAL_SECONDS`, `SELECT ... FOR UPDATE SKIP LOCKED` on Postgres so
replicas never double-deliver) posts batches to
`POST /internal/audit/events` and marks them sent. The audit service is therefore
eventually consistent (seconds), but no entry is ever lost or written without
its change. The system service has no database and sends its two events
(`backup.create`, `backup.download`) directly.

## Customer lookups and statistics

The customer service owns the identity (username, PIN) and composes the lookup:
orders, balance, statistics and favourites come from
`GET /internal/orders/customers/{u}/history` in the order service, which in turn
asks the catalog which of the most-bought products are still active. The admin
customer list uses one bulk call (`/internal/orders/customers/stats`).

## Reports

The report service has no database: each report loads the orders (with lines
and cost snapshots), products, customers and settings over the internal APIs and
computes the figures in Python (`report_service/reports.py`), with the same
*sales* / *paid* basis rule as the monolith. For a small store this is a few
hundred rows per request; a read model fed by events would be the next step if
it ever grows.

## Backups

The system service runs `pg_dump --format=custom` for every database listed in
`BACKUP_DATABASE_URLS` and stores one `kiosk-<stamp>.tar.gz` on the `backups`
volume (SQLite files are copied with `VACUUM INTO` in local runs). The schedule
comes from the `backup_interval_hours` / `backup_keep` settings; the first
scheduled check is 10 minutes after start.

## Scaling notes

- Stateless services (auth, customers, orders, settings, audit, reports,
  frontend) scale horizontally; the login rate limiter is per replica, so add an
  ingress rate limit when running several.
- `catalog-service` (product images) and `system-service` (backups) use
  ReadWriteOnce volumes; use a ReadWriteMany class or object storage to scale them.
- `TRUSTED_PROXIES` tells the auth service which `X-Forwarded-For` entry is the
  client (ingress + gateway = 2 in Kubernetes, 1 in docker compose).
