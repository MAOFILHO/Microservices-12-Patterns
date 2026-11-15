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
  M3a (8, 7, 9, local) and M3b (3 + Azure, owner go-ahead). One PR per milestone.
- Screenshots live in `docs/screenshots/` and are referenced by relative path. Never use GitHub
  `user-attachments` links (they went dead in the parent project).

## Azure naming (must not collide with the parent project)
- Resource group: `rg-microservices-12-patterns` (parent uses `rg-flask-monolith-microservices`).
- Name prefix: `ms12p` (parent uses `flaskms`). Teardown deletes the whole resource group, so a
  shared name would delete the other project.

## Current state (M3a: every pattern except 3 is live)
- Folders: `services/{user,catalog,order,payment,inventory}/` (Flask, one DB each), `gateway/`
  (FastAPI), `registry/` (FastAPI), `shared/` (`shop_common`), `contracts/`, `frontend/`, `infra/`,
  `scripts/`, `tests/`.
- **One service table**: `scripts/service_table.py` lists every local process, folder and port, plus
  `REPLICA_PORTS` (order also on 5113) and `CONTRACT_SUITES`. `setup.py`, `run_local.py`,
  `provision.py` and the smoke tests all read it. Add a service there.
- Ports: user 5101, catalog 5102, order 5103 + 5113, payment 5104, inventory 5105, gateway 8100,
  registry 8500, Redis 6390, frontend 5273.
- Saga (pattern 8): `services/order/application/saga.py`, orchestrated: price, reserve_stock,
  charge_payment, confirm; compensation releases the hold (or emits StockReleaseRequested). Steps in
  `saga_step`; holds keyed by saga id in inventory's `reservation`. `{"simulate_decline": true}` on
  checkout makes payment answer DECLINED (200, not a breaker failure).
- Events (pattern 7): `shop_common/events.py` (Redis Stream `shop.events`, consumer groups, at least
  once). Order writes `outbox_event` in the same transaction; `outbox.py` relays every 1 s; inventory's
  `consumer.py` commits the hold on OrderConfirmed and dedupes via `consumed_event`. `POST /debug/bus`
  (chaos) disconnects a replica's relay. Without `REDIS_URL` events just wait in the outbox.
- Background threads (heartbeat, relay, consumer) start only where `is_serving_process(app)` is true:
  Flask's debug reloader runs a watcher plus a worker, and both build the app.
- Containers (pattern 9): multi-stage Dockerfiles, uid 10001, `.dockerignore` per service, `GIT_SHA`
  build arg, `/debug/runtime`. CI job "Container image" builds, runs and checks all 7 images.
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
- Contracts (pattern 11): order's tests write `contracts/pacts/order-{payment,catalog,inventory}.json`;
  those 3 services verify them. CI fails if the regenerated files differ. Pact (pact-python 4.2) is
  test-only, installed from `contracts/requirements.txt`, never in images.
- `make run` sets `REGISTRY_URL`, `REDIS_URL`, `CHAOS_ENABLED=1`, `INSTANCE_ID`, and restarts a stopped
  service after 20 s. Inventory seeds stock for all 24 catalog products; `POST /api/inventory/<id>/restock`
  (chaos only) keeps smoke runs from running out. Registry TTL 10 s, heartbeat 2 s. Azure uses Container Apps DNS (no registry yet).
- Gotchas solved: FastAPI tracing middleware must be added AFTER the request-ID middleware; Flask-
  SQLAlchemy's engine is instrumented per engine; Pact's `Verifier` needs `host="127.0.0.1"`; Pact state
  handlers run on another thread, so end the test's DB transaction first or SQLite deadlocks; two
  replicas racing `create_all()` (use `shop_common.db_setup.create_tables`).
- Smoke tests create users and products in the local SQLite DBs; delete `services/*/instance/`
  for a clean catalog (this also deletes the local signing key, which logs everyone out).

## How to build (owner's preference)
Follow the Matt Pocock `implement` skill (read it from the mattpocock-skills plugin folder): TDD at
agreed seams, red test first; then `mattpocock-skills:code-review`; then commit.

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
