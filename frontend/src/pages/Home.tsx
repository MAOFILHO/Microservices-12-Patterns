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
          <p className="muted">The 12 patterns. All 12 are live, each with a working demo, plus demo 13 (a slow payment in the middle of checkout), demo 14 (the saga's undo under timeouts and duplicate events) and demo 15 (a flash sale under a replica cap of 3 and of 8).</p>
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
