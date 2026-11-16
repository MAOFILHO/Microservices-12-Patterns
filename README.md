# Microservices 12 Patterns

A small Contoso e-commerce system that shows **12 microservices patterns working for real**.
Each pattern gets its own page with an explanation, when *not* to use it, and a live demo you
can click.

> **Status: complete.** All 12 patterns are live, each with a working demo, locally and in one
> real Azure run: provision, deploy through GitHub Actions with OIDC, smoke tests, screenshots,
> teardown. The foundation is copied from
> [Azure-Ecommerce-Monolith-Microservices-Migration](https://github.com/MAOFILHO/Azure-Ecommerce-Monolith-Microservices-Migration).

## Project summary

**What was built.** 5 Flask services (user, catalog, order, payment, inventory), each owning its
own database, behind one FastAPI gateway; a small service registry; Redis as the event bus; and a
React frontend with one page per pattern. Every demo calls the real services: nothing is mocked.

**How it was delivered.** In milestones, one reviewable pull request each, following
[docs/PLAN.md](docs/PLAN.md):

| Milestone | Patterns | Pull requests |
|---|---|---|
| M0, M1a: bootstrap and layout | (foundation) | [#1](https://github.com/MAOFILHO/Microservices-12-Patterns/pull/1) |
| M1: foundation | 1, 2, 5, 6 | [#2](https://github.com/MAOFILHO/Microservices-12-Patterns/pull/2) |
| M2: resilience and independence | 4, 10, 11, 12 | [#3](https://github.com/MAOFILHO/Microservices-12-Patterns/pull/3) |
| M3a: async and packaging | 7, 8, 9 | [#4](https://github.com/MAOFILHO/Microservices-12-Patterns/pull/4) |
| M3b: delivery and the Azure run | 3 | [#12](https://github.com/MAOFILHO/Microservices-12-Patterns/pull/12), [#13](https://github.com/MAOFILHO/Microservices-12-Patterns/pull/13), [#14](https://github.com/MAOFILHO/Microservices-12-Patterns/pull/14) |

M3b was planned as 7 GitHub issues ([#5 to #11](https://github.com/MAOFILHO/Microservices-12-Patterns/issues?q=is%3Aissue)),
all closed.

**How it was checked.**
- **155 unit tests** across 8 suites, each in its own virtualenv, built test-first from M3a on.
- **Pact contract tests**: the order service's contracts with payment, catalog and inventory,
  verified against the real providers in CI.
- **23 local smoke tests** against the running stack, and **4 Azure smoke tests** against the real
  deployment.
- **CI on every pull request** runs only what the change touches; every image is built for
  linux/amd64, started, and rejected if it runs as root. `main` requires the "CI ok" check.
- A two-axis code review (coding standards, and the spec) before every milestone PR.

**What it cost.** Locally: $0, no Docker. In Azure: one session of about 1.5 hours, on free tiers
or the cheapest SKUs, with a $25/month budget alert, then torn down and verified empty. See
[cost_estimate.md](cost_estimate.md).

## The 12 patterns

| # | Pattern | What it does | Milestone |
|---|---|---|---|
| 1 | [Database per Service](#1-database-per-service) | Gives each service its own database | M1 |
| 2 | [Bounded Context](#2-bounded-context) | Splits one large domain into clear business domains | M1 |
| 3 | [CI-CD Pipeline](#3-ci-cd-pipeline) | Builds, tests and deploys every service automatically | M3b |
| 4 | [Circuit Breaker](#4-circuit-breaker) | Stops calls to a failing service to prevent more failures | M2 |
| 5 | [API Gateway](#5-api-gateway) | Routes client requests to the right service | M1 |
| 6 | [Observability](#6-observability) | Collects logs, metrics and traces from every service | M1 |
| 7 | [Event-Driven Architecture](#7-event-driven-architecture) | Services communicate by publishing and consuming events | M3a |
| 8 | [Saga Pattern](#8-saga-pattern) | Coordinates distributed transactions and rolls back failures safely | M3a |
| 9 | [Containerization](#9-containerization) | Packages each service with all its dependencies | M3a |
| 10 | [Stateless Services](#10-stateless-services) | Stores session data outside the service | M2 |
| 11 | [Contract Testing](#11-contract-testing) | Checks that APIs stay compatible across services | M2 |
| 12 | [Service Discovery](#12-service-discovery) | Finds service instances automatically at runtime | M2 |

## Architecture

```
Browser → API gateway ──┬──► user        → user_db      (signs login tokens)
  (checks tokens,       ├──► catalog     → catalog_db
   request IDs,         ├──► order ×2    → order_db     checkout saga: price → hold stock →
   tracing, metrics,    │                               charge (circuit breaker) → confirm
   aggregation,         ├──► payment     → payment_db
   failover)            └──► inventory   → inventory_db

order_db outbox ──relay──► Redis Stream "shop.events" ──► inventory (sells the held stock)
Every service heartbeats into the registry (:8500); callers look each other up there.
```

- **5 Flask services** (`services/`), each with its own database: SQLite locally, one logical
  MySQL database each in Azure. Locally the order service runs as 2 replicas.
- **FastAPI gateway** (`gateway/`): the only thing the browser talks to. Routes `/api/shop/*` to
  the owning service, adds request IDs, aggregates `/api/order-summary`, serves the demo endpoints.
- **`shop_common`** (`shared/`): OpenTelemetry tracing, JSON logs with trace IDs, Prometheus
  metrics, the `/health/db`, `/debug/spans`, `/metrics` endpoints, token checks, the discovery
  client and the event bus helpers.
- **Service registry** (`registry/`): about 90 lines of FastAPI. Local only; Azure uses Container Apps DNS.
- **Contracts** (`contracts/pacts/`): the Pact files the order service needs payment, catalog and
  inventory to honour.
- **Redis** (Homebrew `redis-server` locally, an internal Container App in Azure): the event bus.
- **Dockerfiles**: one per service plus gateway and registry, multi-stage, non-root, built only in
  the cloud or CI for `linux/amd64`.
- **React + TypeScript** frontend (`frontend/`) with a page per pattern.
- **One service table** (`scripts/service_table.py`): every process, folder and port. Setup, the
  local launcher, CI, provision and the Deploy workflow all read it.

## The live demos

### 1. Database per Service
Each service reports the database it owns. Then the order service tries to read the catalog's
`product` table through its own connection, and the database refuses: `no such table: product`.

<img width="100%" alt="Database per Service demo: 5 services each own their tables; the order service is blocked from reading the catalog's product table" src="docs/screenshots/p01-database-per-service.jpg" />

### 2. Bounded Context
A context map of the 5 business contexts, and one product as two contexts see it: Catalog knows
its name and price, Inventory knows how many are on hand.

<img width="100%" alt="Bounded Context demo: context map and one product seen by Catalog and by Inventory" src="docs/screenshots/p02-bounded-context.jpg" />

### 3. CI-CD Pipeline
Which commit each running service was built from, compared with the latest commit on main, and
the latest CI and Deploy runs, read from GitHub. A service shows "behind main" only when main
changed its own code since its build, the same rule the Deploy button uses.

- **CI on every pull request** runs only what the change touches (`scripts/ci_changes.py`, driven
  by the service table): a change to one service runs its tests and its image; a change to shared
  code, CI or the service table runs everything. Pushes to main run everything.
- **Deploy** is a manual workflow on main. It signs in to Azure with OIDC (no password stored),
  rebuilds only services whose code changed since the commit they run, tags each image with the
  commit, and waits until each service answers with the new commit.

Locally, every process is a "local build":

<img width="100%" alt="CI-CD demo locally: each service is a local build, with the latest CI run on main" src="docs/screenshots/p03-ci-cd.jpg" />

In Azure, every service runs the latest commit of main:

<img width="100%" alt="CI-CD page in Azure: every service on the latest commit of main" src="docs/screenshots/azure-p03-ci-cd.jpg" />

### 4. Circuit Breaker
Switch payment to slow and send 10 calls. Each order replica's breaker opens after 3 failures.
A real failure took 2,215 ms; a call the open breaker stopped took 0 ms. After 15 s with payment
healthy again, both breakers close.

<img width="100%" alt="Circuit Breaker demo: both order replicas' breakers open; failed calls take 2.2 s, short-circuited calls 0 ms" src="docs/screenshots/p04-circuit-breaker.jpg" />

### 5. API Gateway
One browser call to `/api/order-summary` becomes 4 service calls. The page shows each call, its
status and timing, and the one request ID forwarded to all of them.

<img width="100%" alt="API Gateway demo: one browser call fans out to user, order, catalog and inventory" src="docs/screenshots/p05-api-gateway.jpg" />

### 6. Observability
One click, traced through every process: 25 spans across 5 processes, including each service's
database queries, drawn as a waterfall. Metrics per service come from each `/metrics` endpoint.

<img width="100%" alt="Observability demo: a trace waterfall across gateway, user, order, catalog and inventory" src="docs/screenshots/p06-observability.jpg" />

### 7. Event-Driven Architecture
Disconnect the bus and buy a mug: its 3 events (StockReserved, PaymentCharged, OrderConfirmed)
wait in the order service's outbox, and the mug stays held in inventory. Reconnect: the events go
out and inventory turns the hold into a sale.

<img width="100%" alt="Event-Driven demo: bus disconnected, 3 events waiting in the outbox, one mug held" src="docs/screenshots/p07-event-driven.jpg" />

In Azure, the same 3 events were published within a second through the Redis Container App, and
inventory sold the reservation:

<img width="100%" alt="Event-Driven page in Azure: 3 events published within a second; inventory sold the reservation" src="docs/screenshots/azure-p07-event-driven.jpg" />

### 8. Saga Pattern
Buy 2 mugs with "make the bank decline the card" ticked. The saga prices the cart, holds the stock,
the charge fails, and it releases the stock. Stock ends exactly where it started; the cart is kept.

<img width="100%" alt="Saga demo: a declined card, with the stock hold released by the compensation step" src="docs/screenshots/p08-saga.jpg" />

### 9. Containerization
How each process runs: uid, container or not, platform, build and image size. Locally they are
plain processes; CI builds and runs every image for linux/amd64 and fails any that runs as root.

<img width="100%" alt="Containerization demo locally: every process, its uid and platform, and the Dockerfile shape" src="docs/screenshots/p09-containerization.jpg" />

In Azure, all 6 run in containers as uid 10001 on linux/x86_64, built from one commit, 67-69 MB each:

<img width="100%" alt="Containerization page in Azure: 6 containers, uid 10001, linux/x86_64, built from one commit, 67-69 MB" src="docs/screenshots/azure-p09-containerization.jpg" />

### 10. Stateless Services
Your login is a signed token, readable by anyone, signed only by the user service. Ask for your
cart 6 times: both order replicas answer. Stop one: all 6 calls still succeed, same cart, still
logged in.

<img width="100%" alt="Stateless Services demo: one order replica stopped, all 6 cart requests still succeed on the other" src="docs/screenshots/p10-stateless-services.jpg" />

### 11. Contract Testing
The order service's contracts with payment, catalog and inventory, read from the committed Pact
files, and the real CI output when payment renames one field the order service relies on.

<img width="100%" alt="Contract Testing demo: the contract break output and how CI runs consumer and provider checks" src="docs/screenshots/p11-contract-testing.jpg" />

### 12. Service Discovery
The live registry. Stop an instance: its heartbeat stops, the registry expires it after 10 s, and
`make run` restarts it 20 s later, when it registers again.

<img width="100%" alt="Service Discovery demo: registry table and an expired then re-registered order replica" src="docs/screenshots/p12-service-discovery.jpg" />

## Run locally (no Docker)

```bash
brew install redis   # once: the event bus (patterns 7 and 8)
make setup           # one venv per service + gateway, shop_common, frontend packages
make run             # frontend :5273, gateway :8100, registry :8500, Redis :6390
make test            # unit tests, each suite in its own venv
make contracts       # Pact: order writes its contracts; payment, catalog and inventory verify them
make smoke           # end-to-end checks against the running stack
```

Optional: set `OTEL_EXPORTER_OTLP_ENDPOINT` to also send spans to an OpenTelemetry viewer or
collector. Without it, traces stay in each process's memory and the Observability page draws them.

## Run in Azure

Azure Container Apps (one app per service plus the gateway, all scale-to-zero; Redis as an
always-on internal bus) + MySQL Flexible Server, on free tiers or the cheapest SKUs. About $0.21
for an 8-hour session; see [cost_estimate.md](cost_estimate.md). In Azure, discovery uses Container
Apps DNS (no registry), and the demo switches stay off. Redis is reachable only from apps inside the
environment and has no password, which is fine for a demo where every app is ours.

```bash
make github-identity   # once: the Azure identity the Deploy workflow uses (OIDC, no secret)
make provision BUDGET_EMAIL=you@example.com   # everything, images tagged with the current commit
# then GitHub → Actions → Deploy → Run workflow: rebuilds only the services that changed
make teardown && make verify                    # remove everything, then prove nothing is left
```

### The Azure run
`make provision` built 6 images in the cloud (67-69 MB each, tagged with the commit), deployed them
plus Redis, and created the $25 budget alert. The Azure smoke tests
(`tests/smoke/test_post_provision_azure.py`) passed 4 of 4: a sale settled through Redis, demo
switches answered 403, every container ran as uid 10001 on the deployed commit, and the CI-CD page
saw every service on main. The Deploy button then signed in with OIDC and correctly rebuilt
nothing. Everything was removed with `make teardown` the same evening, and `make verify` passed.
The screenshots from Azure are in patterns [3](#3-ci-cd-pipeline), [7](#7-event-driven-architecture)
and [9](#9-containerization) above. Details: [issue #11](https://github.com/MAOFILHO/Microservices-12-Patterns/issues/11).

Lessons from the run: GitHub now presents an OIDC subject with account and repo ids, so the
identity trusts both forms ([PR #14](https://github.com/MAOFILHO/Microservices-12-Patterns/pull/14));
`make verify` can time out while Azure removes an empty Container Apps environment, which takes
longer than everything else and bills nothing.

## Project docs

- [docs/PLAN.md](docs/PLAN.md): the agreed plan, the M3 review decisions and the code review outcomes.
- [cost_estimate.md](cost_estimate.md): every Azure resource, its SKU and its cost.
- [CLAUDE.md](CLAUDE.md): the project's working notes, ground rules and gotchas.
- [Issues](https://github.com/MAOFILHO/Microservices-12-Patterns/issues?q=is%3Aissue): the M3b tickets, all closed.
