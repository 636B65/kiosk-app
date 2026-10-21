---
name: kiosk-testing
description: Choose and run the correct kiosk-app backend, browser, frontend syntax, and Docker/TLS checks; diagnose failures without masking them.
---

# Kiosk App testing

Use this skill to validate changes or diagnose a failing check. Read `AGENTS.md` first for
test fixtures, environment requirements, and repository-specific gotchas.

## Checks

- Backend API and unit suite: `cd backend && pytest tests -v`
- Python lint and configured types: `cd backend && ruff check . && mypy`
- Frontend syntax: `node --check frontend/js/*.js`
- Browser behavior: from `tests/e2e`, run
  `CHROMIUM_PATH=/usr/bin/chromium E2E_PYTHON=python3.12 npm test`
  (use an installed Python interpreter with backend requirements if `python3.12` is not
  available; say which interpreter was used).
- Docker/TLS integration: run the `integration-tls` job in `.github/workflows/ci.yml`, or
  locally use Docker Compose and `tests/e2e/https-smoke.js`.

## Test discipline

- Run the smallest relevant check while iterating, then all three required repository
  checks before finishing; add e2e when user-facing behavior or UI changes.
- E2E and pytest use SQLite state. Follow the harness fixtures and use a dedicated
  temporary database/ports for local concurrent runs to avoid contaminating other work.
- Diagnose failures from their first meaningful error. Fix failures caused by the change;
  do not hide them, weaken assertions, or report partial runs as passing.
- The e2e harness fails on any browser console/page error not listed in its
  `expectedErrors` allowlist (intentional 403/404 steps). Fix unexpected errors instead of
  widening the allowlist; add a narrow pattern only for a new intentional error step.
- Summarize which checks passed and disclose skipped or unavailable checks.
