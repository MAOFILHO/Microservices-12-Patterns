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
  {
    n: 3,
    slug: "ci-cd-pipeline",
    name: "CI-CD Pipeline",
    what: "Builds, tests and deploys every service automatically.",
    milestone: "M3",
    live: true,
    problem:
      "With 5 services and a gateway, building and testing everything on every change is slow, and deploying by hand from a laptop is error-prone: nobody knows which version runs where, and one tired evening ships the wrong one.",
    inThisProject: [
      "Every pull request first plans its jobs from the changed files and the service table: a change to the payment service runs payment's tests and image only.",
      "Shared code, CI itself or the service table run everything. Changing the contract consumer also runs every provider's contract check.",
      "Every image is built for linux/amd64 in CI, started, health-checked, and rejected if it runs as root.",
      "Deploy is a manual workflow on main. It signs in to Azure with OIDC (no stored password), rebuilds only the services that changed since the commit they run, and waits until each answers with the new commit.",
      "Every running service reports the commit it was built from. This page marks a service behind main only when main changed its code since that build, the same rule Deploy uses.",
    ],
    whenNotToUse: [
      "Path-based skipping trusts the folder layout. Code that one service imports from another folder must be declared, or a change can skip a test it should run.",
      "Manual deploys suit a demo. A busy team usually deploys every merge automatically, behind tests and feature flags.",
      "Rebuilding only what changed assumes services are independent. Breaking API changes still need contract tests and a deploy order.",
    ],
    source: { label: "Martin Fowler — Continuous Delivery", url: "https://martinfowler.com/bliki/ContinuousDelivery.html" },
  },
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
  {
    n: 7,
    slug: "event-driven-architecture",
    name: "Event-Driven Architecture",
    what: "Services communicate by publishing and consuming events.",
    milestone: "M3",
    live: true,
    problem:
      "If the order service had to call inventory, shipping and email directly to finish every sale, it would wait on all of them and fail whenever any one is down. Every new listener means changing the order service.",
    inThisProject: [
      "The order service saves OrderConfirmed in an outbox table, in the same database transaction as the order. The event exists if and only if the order does.",
      "A relay publishes outbox events to one Redis Stream, shop.events, once a second. If Redis is down, they wait in the table.",
      "Inventory reads the stream in its own consumer group and turns the stock hold into a sale. It acknowledges an event only after handling it.",
      "Delivery is at least once, so inventory records every event id it handled and skips duplicates.",
    ],
    whenNotToUse: [
      "When the caller needs the answer now, such as \"is this in stock?\", call the service directly. An event cannot answer a question.",
      "Events make the system eventually consistent: for a moment, stock shows as held, not sold. The UI and the business must accept that.",
      "Tracing a flow through events is harder than through calls. Carry IDs in every event, as these do.",
    ],
    source: { label: "microservices.io — Transactional outbox", url: "https://microservices.io/patterns/data/transactional-outbox.html" },
  },
  {
    n: 8,
    slug: "saga",
    name: "Saga Pattern",
    what: "Coordinates distributed transactions and rolls back failures safely.",
    milestone: "M3",
    live: true,
    problem:
      "Checkout touches 3 databases: stock, payment and orders. No transaction spans them. If the card is declined after stock was held, something must put the stock back, or it is lost for good.",
    inThisProject: [
      "The order service orchestrates the saga: price (catalog), hold stock (inventory), charge (payment), confirm.",
      "If a step fails, it undoes the earlier ones in reverse order. Only the stock hold changed another service, so the undo is releasing it.",
      "If the release call itself fails, a StockReleaseRequested event goes through the outbox, so inventory releases it later.",
      "Every step is logged in saga_step. Holds are keyed by the saga id, so a retried request never holds stock twice.",
      "A declined card is a normal answer, not a failure, so it does not trip the M2 circuit breaker. The cart is kept for another try.",
    ],
    whenNotToUse: [
      "If the data can live in one database, use one local transaction. A saga is the price of splitting data, not a goal.",
      "Every step needs an undo, and the undo must be safe to run twice. Steps that cannot be undone, such as sending an email, go last.",
      "Between steps, other users can see the half-done state (held stock). Design for it.",
    ],
    source: { label: "microservices.io — Saga", url: "https://microservices.io/patterns/data/saga.html" },
  },
  {
    n: 9,
    slug: "containerization",
    name: "Containerization",
    what: "Packages each service with all its dependencies.",
    milestone: "M3",
    live: true,
    problem:
      "\"It works on my machine\": each server needs the right Python, libraries and settings. The owner's Mac is arm64 and Azure runs amd64, so even the processor differs.",
    inThisProject: [
      "One image per service, plus the gateway and the registry: 7 Dockerfiles.",
      "Multi-stage builds: dependencies are installed in a first stage, and only the virtualenv and source are copied into the final image.",
      "Every image runs as uid 10001, never root, and carries the git commit it was built from.",
      "Images are built only in the cloud (az acr build) or in GitHub Actions, always for linux/amd64. Never on the Mac.",
      "CI builds every image on every pull request, starts it, checks /health, and fails if it runs as root.",
    ],
    whenNotToUse: [
      "A container is not a security boundary on its own. Non-root, small images and patched base images still matter.",
      "Do not put secrets in images. Here, keys and passwords come from Container Apps secrets at run time.",
      "For a single small app, a managed platform that builds from source can be simpler than owning Dockerfiles.",
    ],
    source: { label: "Docker docs — Multi-stage builds", url: "https://docs.docker.com/build/building/multi-stage/" },
  },
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
  {
    n: 13,
    slug: "slow-payment",
    name: "Saga under a slow payment",
    what: "Follows the money and the stock when payment times out mid-checkout.",
    milestone: "M3",
    live: true,
    problem:
      "A declined card is the easy case: the answer is clear and the stock goes back. A timeout is the hard one. The charge call runs long, the breaker counts a failure, the saga releases the stock, and the customer was charged anyway. A retry can even charge them twice.",
    inThisProject: [
      "Every charge carries an idempotency key: the saga id, one per checkout attempt. The retry sends the same key, so payment returns the first charge instead of making a second one.",
      "Payment records a charge as PROCESSING when it arrives, before the slow part, so a check made meanwhile sees it in flight. A reused key with a different amount is refused.",
      "Before any undo, the saga voids the key with payment, which answers how the charge stands. APPROVED confirms the order. DECLINED releases the stock. A charge payment never saw is recorded as VOIDED, so a late copy of it can never be charged.",
      "PROCESSING or no answer: the order waits as pending, with the stock held. It cannot be checked out again or changed, so a second attempt cannot charge.",
      "Every 5 s, each order replica asks payment about pending orders and settles them by the same rules. Deleting the pending row is the claim, so 2 replicas cannot settle one twice. A charge stuck in PROCESSING for 30 s lost its process, so payment voids it and no order waits forever.",
      "Raised by a reader of the project's LinkedIn post, who named both fixes.",
    ],
    whenNotToUse: [
      "Idempotency keys are not optional for anything that moves money. What varies is the key: one per attempt (as here) lets a declined card be retried.",
      "A pending state is honest but costs the shopper a wait. Use it only where guessing is worse, as with money.",
      "\"Never seen\" is final only because payment records a charge on arrival. A provider that does not must also offer a way to refuse a key before the saga releases the stock.",
    ],
    source: { label: "Stripe — Idempotent requests", url: "https://docs.stripe.com/api/idempotent_requests" },
  },
];

export const SERVICE_NAMES = ["gateway", "user", "catalog", "order", "payment", "inventory"] as const;
