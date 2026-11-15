# CLAUDE.md — re-entry context

## What this project is
A portfolio/teaching project that demonstrates **12 microservices patterns** in one small
Contoso e-commerce system, each with a live, clickable demo page:

1 Database per Service · 2 Bounded Context · 3 CI-CD Pipeline · 4 Circuit Breaker ·
5 API Gateway · 6 Observability · 7 Event-Driven Architecture · 8 Saga ·
9 Containerization · 10 Stateless Services · 11 Contract Testing · 12 Service Discovery

Bootstrapped from `../Azure-Ecommerce-Monolith-Microservices-Migration` (files copied, fresh git
history, monolith dropped). The full agreed plan is in [`docs/PLAN.md`](docs/PLAN.md).

## Ground rules (agreed with the owner)
- **No local Docker, ever.** Local = plain Python/Node processes + Homebrew single binaries
  (`redis`, `otel-desktop-viewer`). Images are built only cloud-side (`az acr build`) or in
  GitHub Actions, always `--platform linux/amd64` (owner's Mac is an M1).
- **Local + Azure.** `make provision` / `make teardown` / `make verify`, $25/mo budget alert.
  Nothing is deployed to Azure before milestone M3, and only with the owner's go-ahead.
- **Phased delivery**: M0 bootstrap, then M1 (patterns 1, 2, 5, 6), M2 (10, 12, 4, 11),
  M3 (7, 8, 9, 3 + Azure). One PR per milestone.
- Screenshots live in `docs/screenshots/` and are referenced by relative path. Never use GitHub
  `user-attachments` links (they went dead in the parent project).

## Azure naming (must not collide with the parent project)
- Resource group: `rg-microservices-12-patterns` (parent uses `rg-flask-monolith-microservices`).
- Name prefix: `ms12p` (parent uses `flaskms`). Teardown deletes the whole resource group, so a
  shared name would delete the other project.

## Current state (M1, foundation: patterns 1, 2, 5, 6 live)
- Folders: `services/{user,catalog,order,payment,inventory}/` (Flask, one DB each), `gateway/`
  (FastAPI), `shared/` (`shop_common`), `frontend/`, `infra/`, `scripts/`, `tests/`.
- **One service table**: `scripts/service_table.py` lists every local process, folder and port.
  `setup.py`, `run_local.py`, `provision.py` and the smoke tests all read it. Add a service there.
- Ports: user 5101, catalog 5102, order 5103, payment 5104, inventory 5105, gateway 8100,
  frontend 5273 (registry 8500 arrives in M2).
- **`shop_common`** (`shared/`): every service calls `shop_common.flask_support.install(app, name, db)`
  inside its app context. It adds `/health`, `/health/db`, `/debug/spans`, `/metrics`, OpenTelemetry
  tracing (Flask, requests, SQLAlchemy per engine), JSON logs with trace/request IDs, and metrics.
  The gateway uses `gateway/app/observability.py` (FastAPI + httpx). `setup.py` installs `shared/`
  editable into every venv; `provision.py` stages it as `<service>/_shared` for `az acr build`.
- Traces: each process keeps its last 2,000 spans in memory (`SPAN_STORE`); the gateway stitches a
  trace from every service's `/debug/spans`. Database span names are trimmed to the file name so
  no local path leaks. Containers run gunicorn with 1 worker + 4 threads so one process holds all
  spans. `OTEL_EXPORTER_OTLP_ENDPOINT` optionally exports too.
- Gotchas solved: FastAPI tracing middleware must be added AFTER the request-ID middleware (the
  last-added Starlette middleware runs outermost); Flask-SQLAlchemy's engine is missed by the
  global SQLAlchemy hook, so it is instrumented per engine; the httpx hook only loads where httpx
  is installed.
- Gateway: `/api/shop/<path>` (GET/POST only) routed by `ROUTE_OWNERS`; `/api/order-summary`
  aggregation; demo endpoints in `gateway/app/routers/patterns.py`. No auth check yet (JWT is M2).
- The catalog service keeps the `product` resource name in its API (`/api/product(s)`). The
  unauthenticated `DELETE /api/product/<slug>` was removed.
- Frontend: `/patterns` grid, `/patterns/:slug` page from `frontend/src/patterns/content.ts`, demos
  in `frontend/src/patterns/demos/`. Signed-in user is read from localStorage `shop_auth`.
- Smoke tests create users and products in the local SQLite DBs; delete `services/*/instance/`
  for a clean catalog.

## Stack
Python 3.12 (Flask 3.1 services, FastAPI gateway), Node 18+ (React 18, TypeScript 5, Vite 5),
SQLite locally, Azure MySQL Flexible Server (one server, one DB per service) in Azure.

## Collision note (inherited)
Every Flask service has a top-level `config.py`/`application` package and the gateway has `app`.
Each runs in its own venv. `tests/conftest.py` adds only `infra/`, `scripts/`, `gateway/` to
`sys.path`. M1 fixes this with a shared `shop_common` package.

## How to run
```bash
make setup     # venvs per service + frontend npm deps, no Docker
make run       # every service + gateway + frontend, health-gated
make test      # unit tests, each suite in its own venv
make smoke     # phased smoke tests, skip gracefully when not applicable
```
