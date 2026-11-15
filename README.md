# Microservices 12 Patterns

A small Contoso e-commerce system that shows **12 microservices patterns working for real**.
Each pattern gets its own page with an explanation, when *not* to use it, and a live demo you
can click.

> **Status: M1a, layout.** Three services, a gateway and the frontend run end to end. The foundation is copied from
> [Azure-Ecommerce-Monolith-Microservices-Migration](https://github.com/MAOFILHO/Azure-Ecommerce-Monolith-Microservices-Migration).
> The patterns arrive in 3 milestones. See [docs/PLAN.md](docs/PLAN.md).

## The 12 patterns

| # | Pattern | What it does | Milestone |
|---|---|---|---|
| 1 | Database per Service | Gives each service its own database | M1 |
| 2 | Bounded Context | Splits one large domain into clear business domains | M1 |
| 3 | CI-CD Pipeline | Builds, tests and deploys every service automatically | M3 |
| 4 | Circuit Breaker | Stops calls to a failing service to prevent more failures | M2 |
| 5 | API Gateway | Routes client requests to the right service | M1 |
| 6 | Observability | Collects logs, metrics and traces from every service | M1 |
| 7 | Event-Driven Architecture | Services communicate by publishing and consuming events | M3 |
| 8 | Saga Pattern | Coordinates distributed transactions and rolls back failures safely | M3 |
| 9 | Containerization | Packages each service with all its dependencies | M3 |
| 10 | Stateless Services | Stores session data outside the service | M2 |
| 11 | Contract Testing | Checks that APIs stay compatible across services | M2 |
| 12 | Service Discovery | Finds service instances automatically at runtime | M2 |

## Planned architecture

- **5 Flask services**, each with its own database: `user`, `catalog`, `order`, `payment`, `inventory`.
- **FastAPI gateway**: single entry point, JWT check, aggregation, live demo feeds.
- **Service registry**: register, heartbeat, lookup (local); Azure Container Apps DNS in the cloud.
- **Redis Streams** event bus with a transactional outbox; a saga orchestrator for checkout.
- **OpenTelemetry** traces, JSON logs and metrics.
- **React + TypeScript** frontend with a page per pattern.

## Run locally (no Docker)

```bash
make setup
make run      # frontend http://127.0.0.1:5273, gateway http://127.0.0.1:8100
make test
```

## Cloud

Azure Container Apps + MySQL Flexible Server, provisioned with `make provision` and removed with
`make teardown`. About $0.21 for an 8-hour session. See [cost_estimate.md](cost_estimate.md).
