---
name: kiosk-development
description: Implement and maintain kiosk-app features using its backend, frontend, demo, security, and business-rule conventions.
---

# Kiosk App development

Use this skill when implementing or changing application behavior in this repository.
Read the root `AGENTS.md` before editing; it is the shared source of project architecture
and business rules.

## Implementation guidance

- Inspect existing routes, schemas, models, UI patterns, and tests before adding new logic.
- Keep the backend on FastAPI, SQLAlchemy's classic `Column(...)` API, Pydantic v2, and
  SQLite. Put schema changes in idempotent startup migrations.
- Use `timeutil.utcnow()` for naive UTC timestamps. Preserve server-side validation and
  admin authorization; public customer and kiosk routes are intentional.
- Keep the frontend framework-free and use the existing global objects and fixed script
  load order. Route UI actions through `Actions` and `data-action`; do not add inline
  `onclick` handlers.
- Keep `frontend/js/demo.js` consistent with every changed public API behavior and schema.
- Preserve documented rules for tab checkout, payment, stock, order price snapshots,
  due dates, barcode uniqueness, and customer privacy. If behavior changes intentionally,
  update backend tests, e2e coverage, and `AGENTS.md`.
- Make the smallest complete change, use existing helpers and naming, and avoid unrelated
  formatting or dependency changes.

## Verify changes

Run the backend test suite, Ruff, mypy, and frontend JavaScript syntax checks described in
`AGENTS.md`. For customer-visible or admin UI behavior, run the end-to-end suite as well.
Report any environmental blocker rather than treating a skipped check as a pass.
