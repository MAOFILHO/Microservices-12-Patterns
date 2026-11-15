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

## Current state (M2: patterns 1, 2, 4, 5, 6, 10, 11, 12 live)
- Folders: `services/{user,catalog,order,payment,inventory}/` (Flask, one DB each), `gateway/`
  (FastAPI), `registry/` (FastAPI), `shared/` (`shop_common`), `contracts/`, `frontend/`, `infra/`,
  `scripts/`, `tests/`.
- **One service table**: `scripts/service_table.py` lists every local process, folder and port, plus
  `REPLICA_PORTS` (order also on 5113) and `CONTRACT_SUITES`. `setup.py`, `run_local.py`,
  `provision.py` and the smoke tests all read it. Add a service there.
- Ports: user 5101, catalog 5102, order 5103 + 5113, payment 5104, inventory 5105, gateway 8100,
  registry 8500, frontend 5273.
- **`shop_common`** (`shared/`): every service calls `shop_common.flask_support.install(app, name, db)`
  inside its app context. It adds `/health`, `/health/db`, `/debug/spans`, `/metrics`,
  `POST /debug/crash` (only with `CHAOS_ENABLED=1`), the `X-Instance-Id` header, tracing, JSON logs,
  metrics, and registry heartbeats when `SERVICE_PUBLIC_URL` and `REGISTRY_URL` are set.
  `auth.py` verifies RS256 tokens; `discovery.py` heartbeats and round-robins (urllib, so no spans);
  `contract_testing.py` runs Pact provider verification. `setup.py` installs `shared/` editable;
  `provision.py` stages it as `<service>/_shared` for `az acr build`.
- Tokens (pattern 10): the user service signs (key from `JWT_PRIVATE_KEY_PEM`, else
  `services/user/instance/jwt_private.pem`, git-ignored). Gateway and order verify with
  `/api/user/public-key`. Flask-Login and the `api_key` column are gone. Frontend sends `Bearer`.
- Gateway: rejects `order` paths with a bad token at the edge; `config.url_for()` round-robins via
  the registry, falls back to `SERVICE_BASE_URLS`; the shop proxy fails over to the next replica on a
  refused connection. Trace stitching and metrics read every replica (`config.urls_for()`).
- Circuit breaker (pattern 4): `services/order/application/order_api/api/clients.py`, pybreaker
  (3 failures, 15 s) + tenacity (1 retry, 1 s timeout), only 5xx/timeouts count. Checkout prices from
  catalog, charges payment, keeps the cart on 503. Payment has a `healthy|failing|slow` switch.
- Contracts (pattern 11): order's tests write `contracts/pacts/order-{payment,catalog}.json`; payment
  and catalog verify them. CI fails if the regenerated files differ. Pact (pact-python 4.2) is
  test-only, installed from `contracts/requirements.txt`, never in images.
- `make run` sets `REGISTRY_URL`, `CHAOS_ENABLED=1`, `INSTANCE_ID`, and restarts a stopped service
  after 20 s. Registry TTL 10 s, heartbeat 2 s. Azure uses Container Apps DNS (no registry yet).
- Gotchas solved: FastAPI tracing middleware must be added AFTER the request-ID middleware; Flask-
  SQLAlchemy's engine is instrumented per engine; Pact's `Verifier` needs `host="127.0.0.1"`; DB writes
  inside a Pact state handler deadlock on SQLite (seed before verifying instead).
- Smoke tests create users and products in the local SQLite DBs; delete `services/*/instance/`
  for a clean catalog (this also deletes the local signing key, which logs everyone out).

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
