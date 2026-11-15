# Plan: Microservices-12-Patterns (new project)

## Context

Marco wants a brand-new portfolio project, built on the current
`Azure-Ecommerce-Monolith-Microservices-Migration` repo, that teaches 12 microservices patterns
with a **live, clickable demo per pattern**. The current repo already covers 4 of them well and
lacks 6 almost entirely (audit below), so the new project keeps the proven tooling and adds the
missing behaviour.

Decisions already agreed with Marco:
- Name: **`Microservices-12-Patterns`** (corrected spelling), local + GitHub.
- **No local Docker.** Plain Python/Node processes locally; images built cloud-side only.
- **Local + Azure**, same `make provision` / `make teardown` model and $25/mo budget alert.
- **Phased: 3 milestones**, each one a reviewable PR.

Assumptions to confirm at review (change any of these before approval):
- Local path `/Users/marco/K21/Microservices-12-Patterns`; GitHub `MAOFILHO/Microservices-12-Patterns`, **public**.
- Fresh git history (files copied, old history not carried over).
- The monolith is **not** carried over. This project is microservices-only.

## What the current repo gives us (audit)

| # | Pattern | Today | Work needed |
|---|---|---|---|
| 1 | Database per Service | Done (SQLite per service, 1 MySQL server with a DB each) | Extend to 5 services, add a demo page |
| 2 | Bounded Context | Done in code, not shown | Context map + same product seen by 2 services |
| 3 | CI-CD | CI only (`.github/workflows/ci.yml`) | Per-service path filter, deploy job |
| 4 | Circuit Breaker | Missing (one `requests.get`, 5s timeout) | New |
| 5 | API Gateway | Partial (BFF proxy, no auth, no aggregation) | Auth check, aggregation, request IDs |
| 6 | Observability | Missing (only `/health`) | New |
| 7 | Event-Driven | Missing | New |
| 8 | Saga | Missing (checkout is 1 local write) | New |
| 9 | Containerization | Done (5 Dockerfiles, `az acr build`) | Non-root user, pinned amd64, SHA tags |
| 10 | Stateless Services | Mixed (API key in DB, BFF state in memory) | JWT, 2 replicas |
| 11 | Contract Testing | Missing | New |
| 12 | Service Discovery | Static env vars | New |

## Target design (kept deliberately small)

**Domain:** the same Contoso shop. 5 Flask services, each with its own DB:
`user`, `catalog` (was product), `order`, `payment` (new), `inventory` (new).
Checkout becomes a real cross-service flow: order -> reserve stock -> charge payment.

**Supporting pieces:**
- `gateway/` — FastAPI, evolved from `bff/` (single entry point, JWT check, 1 aggregation endpoint, SSE feed for the demo pages).
- `registry/` — ~100-line FastAPI service registry (register, heartbeat, expire, lookup).
- `frontend/` — same React/Vite/Contoso theme. Pages: Home, Shop, **Patterns** (12 sub-pages, each with an explanation, "when NOT to use it", and a live demo panel), Learn.
- `shared/` — one small installable package (`shop_common`) for config, JWT verify, event bus, discovery client, telemetry setup. Removes today's copy-pasted `config.py`/validation files.

**One piece of infrastructure per need, shared across patterns:**
| Need | Local | Azure | Serves patterns |
|---|---|---|---|
| Message bus | Redis via `brew install redis` (Streams) | Redis as a Container App (image imported to ACR as `linux/amd64`) | 7, 8 |
| Database | SQLite file per service | Existing MySQL Flexible B1ms, 5 logical DBs | 1 |
| Traces/logs | `otel-desktop-viewer` (Homebrew binary) | Application Insights (5 GB/mo free) | 6, and visualises 4, 7, 8 |
| Discovery | `registry/` service | Container Apps built-in DNS (`DISCOVERY=registry|dns`) | 12 |

Same bus code runs locally and in Azure, which avoids local/cloud drift and avoids Service Bus
Standard (~$10/mo, no scale-to-zero).

**How each pattern is implemented and shown:**
1. **Database per Service** — page lists each service's own DB (from `/health/db`); a button shows `order` cannot read `catalog` tables.
2. **Bounded Context** — Mermaid context map; side-by-side JSON of one product as `catalog` sees it (name, price) and as `inventory` sees it (stock).
3. **CI-CD** — `dorny/paths-filter` + matrix: a commit touching one service builds only that leg. Deploy job is **manual trigger only** (`workflow_dispatch`), logs in with OIDC (no stored secrets). Each service exposes `/version` (git SHA).
4. **Circuit Breaker** — `pybreaker` (maintained, 1.4.1) + `tenacity` on `order -> payment`. "Break payment service" toggle; live badge CLOSED / OPEN / HALF-OPEN; checkout fails fast with a clear message while open.
5. **API Gateway** — gateway verifies JWT once, adds `X-Request-Id`, and serves `/api/order-summary/{id}` that fans out to 3 services. Page shows 1 browser call -> 3 backend calls.
6. **Observability** — OpenTelemetry auto-instrumentation (Flask, FastAPI, requests, httpx), JSON logs with trace ID, `/metrics` via `prometheus-client`. Page shows the trace ID of your last order and a link to the viewer.
7. **Event-Driven** — `OrderPlaced`, `StockReserved`, `PaymentFailed`... published through a **transactional outbox** table. Live event log panel; "stop the bus" demo shows events queue as PENDING and drain on restart.
8. **Saga** — hand-written orchestrator in `order` with a persisted `saga_log`. "Force payment decline" checkbox; timeline shows reserve -> charge fails -> **stock released, order cancelled**.
9. **Containerization** — multi-stage `python:3.12-slim` Dockerfiles, non-root user, `az acr build --platform linux/amd64`, SHA tags. Page shows image size and `/whoami` (non-root UID).
10. **Stateless Services** — `PyJWT` RS256 (user signs, gateway verifies); cart lives in the order DB. 2 replicas of `order`; every response carries `X-Instance-Id`; "kill one replica" keeps you logged in with cart intact.
11. **Contract Testing** — `pact-python` v3 (stable since Dec 2025), pact files committed, no broker. `order` is the consumer of `user`/`payment`. A documented failing example (rename `price`) turns CI red.
12. **Service Discovery** — services register + heartbeat; callers look up by name (replaces hard-coded URLs in `UserClient.py`). Dashboard shows instances appear, and vanish ~15s after a kill.

## Reuse from the current repo (copy, then adapt)

- `scripts/setup.py`, `scripts/run_local.py`, `scripts/_procutil.py` — venv setup, health-gated launch, safe port cleanup. Change: one service table in one place (today it is repeated in 6 files).
- `infra/provision.py`, `teardown.py`, `verify_teardown.py`, `pause.py`, `resume.py`, `name_resolver.py`, and `infra/bicep/` (esp. generic `modules/container-app.bicep`, `mysql.bicep`, `log-analytics.bicep`).
- `Makefile` targets, `tests/smoke/` phase layout, `.github/workflows/ci.yml` matrix.
- `microservices/{user,product,order}-service/` as the starting point for 3 of the 5 services.
- `bff/app/routers/shop.py` (proxy) and the SSE snapshot pattern in `bff/app/routers/migration.py` -> gateway + live demo feeds. `migration_engine.py` `Step`/`StepStatus` -> saga timeline model.
- `frontend/src/api/bffClient.ts`, `theme/contoso.css`, `App.tsx`/`NavBar.tsx`, `ArchitectureDiagram.tsx`.
- `docs/screenshots/` convention (images in the repo, never GitHub attachment links).

Known flaws fixed on the way in: hard-coded `http://127.0.0.1:8000` in `metrics.py`, default `SECRET_KEY`, unauthenticated `DELETE /api/product/<slug>`, top-level `app`/`config` name collisions.

**Ports** (offset so both projects can run together): gateway 8100, registry 8500, services 5101-5105, frontend 5273.

## Milestones

**M0 — Bootstrap (first, about 15 min)**
1. Create `/Users/marco/K21/Microservices-12-Patterns`, `git init`, copy the reuse list, strip the monolith.
2. `gh repo create MAOFILHO/Microservices-12-Patterns --public`, first commit, push.
3. Switch this Claude Code session's working directory to the new folder.
4. Write `CLAUDE.md`, `README.md` skeleton, `.env.example`, `.gitignore`.

**M1 — Foundation: patterns 1, 2, 5, 6** (PR 1)
5 services + gateway + shared package + frontend Patterns shell. Observability goes in early so every later pattern is visible in traces.

**M2 — Resilience and independence: patterns 10, 12, 4, 11** (PR 2)
JWT + 2 replicas, registry, circuit breaker with chaos toggle, Pact tests in CI.

**M3 — Async and delivery: patterns 7, 8, 9, 3 + Azure** (PR 3)
Redis bus + outbox, saga with forced failure, hardened Dockerfiles, path-filtered CI + manual deploy job, one real `make provision` -> screenshots -> `make teardown` + `make verify`.

Each milestone ends with: tests green, a click-through of its 4 pattern pages, screenshots saved to `docs/screenshots/`, README section updated.

## Cost

- Local: $0. Two Homebrew installs (`redis`, `otel-desktop-viewer`).
- Azure: same shape as today, **~$0.21 per 8-hour session, ~$19.51/mo if left running** (MySQL is the only always-on charge). Redis runs as a Container App, Application Insights stays inside the free 5 GB. Budget alert stays at $25/mo.
- Nothing is deployed to Azure before M3, and only with Marco's go-ahead at that point.
- The OIDC deploy job needs a one-time Azure app registration + federated credential. That is a separate approval in M3.

## Risks called out by the research

1. **Pattern theatre** — a small shop does not need 12 patterns. Every page states when not to use it.
2. **Async is invisible** — events and sagas need the live log/timeline UI; that UI is budgeted in M1's shell.
3. **Cold starts trip the breaker in Azure** — warm-up call before the demo; breaker thresholds set for it.
4. **Local vs cloud drift** — only 2 seams differ (DB engine, discovery mode); CI tests both discovery modes.
5. **Forgotten cloud resources** — single resource group, teardown + verify after every Azure session.

## Verification

- `make setup && make run-all` starts 5 services (order x2), gateway, registry, frontend; all `/health` green.
- `make test` — unit suites per service + Pact consumer and provider verification.
- `make smoke` — existing phased smoke tests, extended with: full checkout (saga success), forced decline (saga compensation leaves stock unchanged), payment down (breaker opens, then closes), kill one `order` replica (session survives), stop Redis (outbox drains on restart).
- Manual click-through of all 12 pattern pages in the browser pane, with a trace visible in `otel-desktop-viewer` for one order.
- CI: a commit touching only `services/order/` runs only that matrix leg; the documented contract-break branch goes red.
- M3 only: `make provision`, repeat the smoke flow against Azure, `make teardown`, `make verify` returns PASS.

## M3 review (2026-11-15, after M1 and M2 shipped)

What changed since this plan was written: checkout already prices from catalog and charges payment
behind the circuit breaker (M2), checkout does not reserve stock yet, the registry is local only,
the login signing key has no Azure home yet, and Redis is not installed locally yet.

Decisions:
1. **Saga style: orchestrated.** The order service calls inventory (reserve), then payment (charge),
   then confirms. If payment fails or its breaker is open, it releases the stock and cancels the
   order. Each step also publishes an event through the outbox for pattern 7. Chosen over a fully
   event-driven saga: checkout answers in about 1 s and reuses the M2 breaker.
2. **Event consumer: inventory finishes the sale.** The saga only reserves stock. Inventory reads
   `OrderConfirmed` from Redis and moves the units from reserved to sold (on hand goes down).
   "Stop the bus" leaves stock reserved with events waiting in the outbox, then it settles when Redis
   is back. Chosen over a new notifications service: no 6th service, and the effect is visible stock.
3. **Pipeline reach: GitHub deploys to Azure.** A manual "Deploy" workflow builds the changed images
   and updates the Container Apps, logging in with OIDC (no Azure secret stored in GitHub). One Azure
   identity for this repo, with access to `rg-microservices-12-patterns` only; `make provision`
   re-grants it after each teardown. One-time setup done together with the owner.
   Settled without a decision: Redis in Azure is one more Container App (1 replica while provisioned,
   about $0.05 per 8-hour session; Azure Cache for Redis starts near $16/mo). `make provision` creates
   the JWT signing key and stores it as a Container Apps secret.
4. **Delivery: M3 splits into 2 PRs.** M3a = patterns 8, 7, 9 (saga, outbox events, inventory
   consumer, hardened containers), all local, about 2 days. M3b = pattern 3 (path-filtered CI, OIDC
   Deploy workflow, Azure identity setup) plus the one real Azure run, about 1 day, started only on the
   owner's go-ahead after M3a merges.
