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

## Current state (M1a, layout)
- Folders: `services/{user,catalog,order}/` (Flask, one DB each), `gateway/` (FastAPI),
  `frontend/`, `infra/`, `scripts/`, `tests/`. The monolith and the old migration engine are gone.
- **One service table**: `scripts/service_table.py` lists every local process, folder and port.
  `setup.py`, `run_local.py`, `provision.py` and the smoke tests all read it. Add a service there.
- Ports: user 5101, catalog 5102, order 5103, gateway 8100, frontend 5273 (registry 8500 and
  payment/inventory 5104-5105 arrive in later milestones).
- Gateway routes `/api/shop/<path>` to `/api/<path>` on the owning service by first path segment
  (`gateway/app/config.py` `ROUTE_OWNERS`). No auth or aggregation yet (M1).
- The catalog service keeps the `product` resource name in its API (`/api/product(s)`) and its
  `product_api` package. Only the service, its env vars (`CATALOG_*`) and its DB (`catalog_db`) are
  named catalog.
- Azure: one Container App per service plus the gateway, all external ingress, images built with
  `az acr build --platform linux/amd64`.

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
