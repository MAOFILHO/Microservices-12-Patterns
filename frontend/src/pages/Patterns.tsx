const PATTERNS: { n: number; name: string; what: string; milestone: "M1" | "M2" | "M3" }[] = [
  { n: 1, name: "Database per Service", what: "Gives each service its own database.", milestone: "M1" },
  { n: 2, name: "Bounded Context", what: "Splits one large domain into clear business domains.", milestone: "M1" },
  { n: 3, name: "CI-CD Pipeline", what: "Builds, tests and deploys every service automatically.", milestone: "M3" },
  { n: 4, name: "Circuit Breaker", what: "Stops calls to a failing service to prevent more failures.", milestone: "M2" },
  { n: 5, name: "API Gateway", what: "Routes client requests to the right service.", milestone: "M1" },
  { n: 6, name: "Observability", what: "Collects logs, metrics and traces from every service.", milestone: "M1" },
  { n: 7, name: "Event-Driven Architecture", what: "Services communicate by publishing and consuming events.", milestone: "M3" },
  { n: 8, name: "Saga Pattern", what: "Coordinates distributed transactions and rolls back failures safely.", milestone: "M3" },
  { n: 9, name: "Containerization", what: "Packages each service with all its dependencies.", milestone: "M3" },
  { n: 10, name: "Stateless Services", what: "Stores session data outside the service.", milestone: "M2" },
  { n: 11, name: "Contract Testing", what: "Checks that APIs stay compatible across services.", milestone: "M2" },
  { n: 12, name: "Service Discovery", what: "Finds service instances automatically at runtime.", milestone: "M2" },
];

export default function Patterns() {
  return (
    <div className="grid" style={{ gap: "1.5rem" }}>
      <section className="card">
        <h1>The 12 patterns</h1>
        <p className="muted">
          Each pattern gets its own page with an explanation, when not to use it, and a live demo.
          They arrive in three milestones.
        </p>
      </section>
      <div className="grid cols-3">
        {PATTERNS.map((p) => (
          <div key={p.n} className="card">
            <h3>
              {p.n}. {p.name}
            </h3>
            <p className="muted">{p.what}</p>
            <span className="pill">Coming in {p.milestone}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
