# AGENTS.md

Guidance for AI coding agents working on this repo. Read this before editing.

## What this is

The [kiosk-app](https://github.com/636B65/kiosk-app) store kiosk as **microservices
on Kubernetes**: eight FastAPI services + the unchanged vanilla-JS frontend (which
doubles as the nginx API gateway), Kustomize manifests, Argo CD applications.
The business rules are the monolith's; `docs/architecture.md` explains how each is
enforced across service borders. The public HTTP API must stay compatible with
the frontend in `frontend/js/`.

## Quick commands

```bash
pip install -r requirements-dev.txt -e libs/kiosk_common
ruff check .                                   # lint (isort rules included)
pytest -v                                      # all services in one process, SQLite
node --check frontend/js/*.js
kubectl kustomize deploy/overlays/dev | kubeconform -strict -ignore-missing-schemas
docker compose up -d --build                   # full stack with Postgres on :8080
```

Run all four checks before finishing a change.

## Layout

- `libs/kiosk_common/` shared package: `config` (ServiceConfig), `db` (Database,
  get_db), `auth` (AuthVerifier, get_current_user/get_optional_user, Principal),
  `internal` (require_internal), `http` (ServiceClient, UpstreamError), `outbox`
  (OutboxRelay, publish), `audit` (record, describe_changes), `app`
  (create_base_app: CORS, /healthz, /readyz, UpstreamError handler), `testing`.
- `services/<name>/<name_with_underscores>/`: `config.py`, `models.py` (own
  declarative Base + `Outbox = make_outbox_model(Base)`), `schemas.py`,
  `routers*.py`, `main.py` with `create_app(config=None)` (uvicorn `--factory`).
- `frontend/nginx/default.conf.template`: the gateway route table. Keep it in
  lockstep with `ROUTES` in `tests/integration/conftest.py`.
- `deploy/base` + `deploy/overlays/{dev,prod}` + `deploy/argocd`.
- `docker/service.Dockerfile` builds every Python service (`SERVICE` build arg).

## Conventions

- Services never share tables. Cross-service reads/writes go through
  `/internal/*` routes with `dependencies=[Depends(require_internal)]`; the
  gateway never routes `/internal`. Add new internal routes to the owning service
  and call them with `request.app.state.clients["<name>"]`.
- Admin routes: `Depends(get_current_user)`. Public routes are listed in
  `PUBLIC_ENDPOINTS` (`tests/integration/test_route_sweep.py`); the sweep fails
  for any other route that answers without a token.
- Audit: `audit.record(db, Outbox, actor, action, entity, entity_id, details)`
  inside the same transaction, never a direct HTTP call (except system-service).
- Stock changes are single SQL statements in the catalog service, never
  read-modify-write; checkout reserves all lines or none.
- 4xx from another service pass through unchanged (`UpstreamError` handler);
  unreachable/5xx become 502.
- `timeutil.utcnow()` only; naive UTC timestamps; `money()` for amounts.
- No build step in the frontend; event handling through the `Actions` registry.
- Versions: SemVer in `CHANGELOG.md`; all images share one version.

## Testing notes

- `tests/integration` builds every app with `create_app(Config(...))` on its own
  SQLite file, wires `ServiceClient`s through `InProcessTransport`, and sends
  requests through a `Gateway` with the nginx route table. Tests share one stack
  (session scope) and run in file order (`test_0_smoke.py` first).
- Outbox delivery is explicit in tests: `stack.flush_outboxes()` before reading
  the audit log.
- Docker compose smoke runs in CI only (needs a Docker daemon).
