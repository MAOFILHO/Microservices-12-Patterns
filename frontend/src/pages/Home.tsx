import { Link } from "react-router-dom";

export default function Home() {
  return (
    <div className="grid" style={{ gap: "1.5rem" }}>
      <section className="card">
        <h1>12 microservices patterns, working for real.</h1>
        <p className="muted">
          A small Contoso shop built from independent services. Each pattern has its own page that
          explains it, says when not to use it, and lets you trigger it live.
        </p>
      </section>

      <div className="grid cols-3">
        <Link to="/shop" className="card" style={{ textDecoration: "none", color: "inherit" }}>
          <h3>Shop</h3>
          <p className="muted">Register, browse, add to cart and check out, all through the gateway.</p>
        </Link>
        <Link to="/patterns" className="card" style={{ textDecoration: "none", color: "inherit" }}>
          <h3>Patterns</h3>
          <p className="muted">The 12 patterns. 8 are live now, from Database per Service to Service Discovery; the last 4 arrive in M3.</p>
        </Link>
      </div>

      <section className="card">
        <h2>Architecture today</h2>
        <pre style={{ overflowX: "auto" }}>{`
Browser → API gateway ──┬──► user       → user_db
  (request IDs,         ├──► catalog    → catalog_db
   tracing, metrics,    ├──► order      → order_db ──HTTP──► user (validates the caller)
   aggregation)         ├──► payment    → payment_db
                        └──► inventory  → inventory_db
`}</pre>
      </section>
    </div>
  );
}
