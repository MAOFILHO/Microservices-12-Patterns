export type Milestone = "M1" | "M2" | "M3";

export interface PatternInfo {
  n: number;
  slug: string;
  name: string;
  what: string;
  milestone: Milestone;
  live: boolean;
  problem?: string;
  inThisProject?: string[];
  whenNotToUse?: string[];
  source?: { label: string; url: string };
}

export const PATTERNS: PatternInfo[] = [
  {
    n: 1,
    slug: "database-per-service",
    name: "Database per Service",
    what: "Gives each service its own database.",
    milestone: "M1",
    live: true,
    problem:
      "When services share one database, any schema change can break a service you did not touch, and no service can be deployed or scaled on its own. The database becomes the real monolith.",
    inThisProject: [
      "Each of the 5 services has its own database: a SQLite file locally, a separate logical database on one MySQL server in Azure.",
      "A service reaches another service's data only through that service's API, never through SQL.",
      "The order service validates users by calling the user service over HTTP, not by joining the user table.",
    ],
    whenNotToUse: [
      "Small teams with one deployable: the cost of no joins and no cross-service transactions outweighs the benefit.",
      "Reporting that needs joins across domains: feed a separate read model or warehouse instead of querying service databases.",
      "One MySQL server with one database per service is a cost compromise. It isolates schemas, not load.",
    ],
    source: { label: "microservices.io — Database per service", url: "https://microservices.io/patterns/data/database-per-service.html" },
  },
  {
    n: 2,
    slug: "bounded-context",
    name: "Bounded Context",
    what: "Splits one large domain into clear business domains.",
    milestone: "M1",
    live: true,
    problem:
      "One shared model of \"Product\" ends up holding price, stock, images and warehouse data for every team. Every change needs every team's agreement, so nobody can change it.",
    inThisProject: [
      "Catalog owns what we sell: name, slug, price.",
      "Inventory owns how many we have: on hand, reserved, available. It knows a product only by its id.",
      "Order owns carts and orders. Payment owns charges and knows an order only by id and amount.",
      "The gateway translates between contexts when it builds a combined view.",
    ],
    whenNotToUse: [
      "Do not split one context per database table. That gives many tiny CRUD services that must all change together.",
      "Boundaries follow business capabilities and team ownership, not technical layers.",
    ],
    source: { label: "Martin Fowler — BoundedContext", url: "https://martinfowler.com/bliki/BoundedContext.html" },
  },
  { n: 3, slug: "ci-cd-pipeline", name: "CI-CD Pipeline", what: "Builds, tests and deploys every service automatically.", milestone: "M3", live: false },
  { n: 4, slug: "circuit-breaker", name: "Circuit Breaker", what: "Stops calls to a failing service to prevent more failures.", milestone: "M2", live: false },
  {
    n: 5,
    slug: "api-gateway",
    name: "API Gateway",
    what: "Routes client requests to the right service.",
    milestone: "M1",
    live: true,
    problem:
      "Without a gateway the browser must know every service's address, call several of them for one screen, and every service must handle CORS and request tracking on its own.",
    inThisProject: [
      "The browser talks only to the gateway. /api/shop/<path> is routed to the service that owns <path>.",
      "Every request gets an X-Request-Id, forwarded to every service and echoed back, so all logs for one click share one ID.",
      "/api/order-summary turns one browser call into 4 service calls (user, order, catalog, inventory) and returns one combined answer.",
      "Unknown paths return 404 and an unreachable service returns a clear 503, never a hung request. Only GET and POST are exposed.",
    ],
    whenNotToUse: [
      "Do not put business rules in the gateway. It routes, aggregates and handles cross-cutting concerns; it does not decide prices or stock.",
      "One shared gateway for many very different clients becomes a bottleneck team. Consider one backend-for-frontend per client type.",
    ],
    source: { label: "microservices.io — API gateway", url: "https://microservices.io/patterns/apigateway.html" },
  },
  {
    n: 6,
    slug: "observability",
    name: "Observability",
    what: "Collects logs, metrics and traces from every service.",
    milestone: "M1",
    live: true,
    problem:
      "A single click crosses several processes. When it is slow or fails, per-service logs alone cannot tell you which hop caused it.",
    inThisProject: [
      "Traces: OpenTelemetry in every service. The W3C traceparent header carries one trace across the gateway and every service, including database queries.",
      "Logs: one JSON line per request, carrying trace_id, span_id and request_id.",
      "Metrics: request count and latency per route at /metrics in Prometheus format.",
      "Each process keeps its last 2,000 spans in memory, so this page can draw a trace with no extra tool. Set OTEL_EXPORTER_OTLP_ENDPOINT to also send spans to a viewer or collector.",
    ],
    whenNotToUse: [
      "Never label metrics with raw URLs or user IDs: every distinct value becomes a new series. Use route templates.",
      "In production, sample traces. Keeping every span is fine for a demo, expensive at scale.",
      "The in-memory span store is a teaching aid, not a tracing backend: it forgets on restart and only holds recent spans.",
    ],
    source: { label: "OpenTelemetry — Python zero-code instrumentation", url: "https://opentelemetry.io/docs/zero-code/python/" },
  },
  { n: 7, slug: "event-driven-architecture", name: "Event-Driven Architecture", what: "Services communicate by publishing and consuming events.", milestone: "M3", live: false },
  { n: 8, slug: "saga", name: "Saga Pattern", what: "Coordinates distributed transactions and rolls back failures safely.", milestone: "M3", live: false },
  { n: 9, slug: "containerization", name: "Containerization", what: "Packages each service with all its dependencies.", milestone: "M3", live: false },
  { n: 10, slug: "stateless-services", name: "Stateless Services", what: "Stores session data outside the service.", milestone: "M2", live: false },
  { n: 11, slug: "contract-testing", name: "Contract Testing", what: "Checks that APIs stay compatible across services.", milestone: "M2", live: false },
  { n: 12, slug: "service-discovery", name: "Service Discovery", what: "Finds service instances automatically at runtime.", milestone: "M2", live: false },
];

export const SERVICE_NAMES = ["gateway", "user", "catalog", "order", "payment", "inventory"] as const;
