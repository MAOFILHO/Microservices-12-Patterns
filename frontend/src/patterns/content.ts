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
      "The order service learns who you are from your signed token and prices orders by asking the catalog over HTTP, never by joining their tables.",
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
  {
    n: 4,
    slug: "circuit-breaker",
    name: "Circuit Breaker",
    what: "Stops calls to a failing service to prevent more failures.",
    milestone: "M2",
    live: true,
    problem:
      "When payment hangs, every checkout waits for it. Threads pile up in the order service until it stops answering too, and one sick service takes down the ones that call it.",
    inThisProject: [
      "Every order-to-payment call goes through one breaker (pybreaker). It opens after 3 failed calls in a row, fails calls at once for 15 s, then lets one trial call through.",
      "Each call waits at most 1 s and is retried once after 0.2 s (tenacity), so a single blip does not count as a failure.",
      "Only 5xx errors and timeouts count. A 400 is the caller's mistake, not a sick service.",
      "Checkout while the breaker is open returns a clear 503: nothing was charged, the cart is kept, try again in N seconds.",
      "Each order replica has its own breaker. They do not share state, which this page shows.",
    ],
    whenNotToUse: [
      "Not for calls that must not be skipped, such as writing an audit record. Queue those instead (event-driven, M3).",
      "Retries without a breaker multiply load on a struggling service. Always cap retries and pair them with a breaker.",
      "Per-replica breakers open at different times. For many replicas, a shared state store or a service mesh does this better.",
    ],
    source: { label: "Martin Fowler — CircuitBreaker", url: "https://martinfowler.com/bliki/CircuitBreaker.html" },
  },
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
  {
    n: 10,
    slug: "stateless-services",
    name: "Stateless Services",
    what: "Stores session data outside the service.",
    milestone: "M2",
    live: true,
    problem:
      "If a service keeps your login or cart in its own memory, every request must go back to that one process. Restarting or adding a copy logs people out and empties carts.",
    inThisProject: [
      "Login returns a token signed by the user service (RS256 JWT, 1 hour). Nothing is written to a database or a session.",
      "The gateway and the order service check the signature with the user service's public key, fetched once. No call to the user service per request.",
      "The cart lives in the order database, not in the order process.",
      "make run starts 2 order replicas. Every response says which one answered (X-Instance-Id), and either can serve you.",
    ],
    whenNotToUse: [
      "A JWT cannot be cancelled before it expires. Keep lifetimes short, or keep a deny-list if you need instant logout.",
      "Never put secrets or personal data in the token: anyone holding it can read the claims. Only the signature is protected.",
      "Stateless does not mean no state. The state moved to a database, which now has to scale and stay available.",
    ],
    source: { label: "The Twelve-Factor App — VI. Processes", url: "https://12factor.net/processes" },
  },
  {
    n: 11,
    slug: "contract-testing",
    name: "Contract Testing",
    what: "Checks that APIs stay compatible across services.",
    milestone: "M2",
    live: true,
    problem:
      "Each service's own tests pass, yet a renamed field in payment breaks checkout in production. End-to-end tests would catch it, but they are slow and need every service running.",
    inThisProject: [
      "The order service is the consumer. Its tests record what it sends to payment and catalog and which fields it reads back, as Pact contracts in contracts/pacts/.",
      "Payment and catalog are the providers. Their test suites start the real service and replay every request in the contract.",
      "Renaming amount_cents in payment fails the payment suite, so CI is red on that pull request.",
      "No Pact broker: the contracts are committed next to the code. pact-python 4.2.",
    ],
    whenNotToUse: [
      "Not a replacement for testing business logic. A contract checks the shape of messages, not that prices are right.",
      "Without a broker, consumer and provider must live in one repo. Across repos and teams, use a Pact broker and can-i-deploy.",
      "For a public API with unknown consumers, use a versioned schema (OpenAPI) and compatibility checks instead.",
    ],
    source: { label: "Pact documentation — How Pact works", url: "https://docs.pact.io/getting_started/how_pact_works" },
  },
  {
    n: 12,
    slug: "service-discovery",
    name: "Service Discovery",
    what: "Finds service instances automatically at runtime.",
    milestone: "M2",
    live: true,
    problem:
      "With fixed addresses in config, adding a replica means editing every caller, and callers keep sending traffic to an instance that has crashed.",
    inThisProject: [
      "A small registry (port 8500) holds every live instance. Each service re-registers every 2 s, a heartbeat.",
      "An instance silent for more than 10 s is dropped, so a crashed replica disappears without anyone telling the registry.",
      "The gateway and the order service keep a copy of the registry, refreshed every 2 s, and spread calls across the live instances.",
      "If the registry is not running, callers fall back to fixed URLs. In Azure, Container Apps' built-in DNS and load balancing do this job instead.",
    ],
    whenNotToUse: [
      "On Kubernetes or Container Apps, use the platform's DNS-based discovery. Running your own registry duplicates it.",
      "A registry is now a critical dependency. Callers must cache its answers and keep working when it is down, as these do.",
      "Heartbeat timing is a trade-off: a short TTL drops crashed instances fast but may drop slow ones by mistake.",
    ],
    source: { label: "microservices.io — Client-side service discovery", url: "https://microservices.io/patterns/client-side-discovery.html" },
  },
];

export const SERVICE_NAMES = ["gateway", "user", "catalog", "order", "payment", "inventory"] as const;
