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

## Current state (M0)
The code is still the parent project's microservices + BFF + frontend, with the monolith
removed from setup, tests and CI only. Remaining monolith references in `bff/`, `frontend/`,
`scripts/run_local.py`, `scripts/benchmark.py` and `infra/` are replaced in M1, when `bff/`
becomes `gateway/`, services move to `services/<name>/`, and ports move to the new range
(gateway 8100, registry 8500, services 5101-5105, frontend 5273).

## Stack
Python 3.12 (Flask 3.1 services, FastAPI gateway), Node 18+ (React 18, TypeScript 5, Vite 5),
SQLite locally, Azure MySQL Flexible Server (one server, one DB per service) in Azure.

## Collision note (inherited)
Every Flask service has a top-level `config.py`/`application` package and the BFF has `app`.
Each runs in its own venv. `tests/conftest.py` adds only `infra/`, `scripts/`, `bff/` to
`sys.path`. M1 fixes this with a shared `shop_common` package.

## How to run
```bash
make setup     # venvs per service + frontend npm deps, no Docker
make test      # unit tests, each suite in its own venv
make smoke     # phased smoke tests, skip gracefully when not applicable
```
