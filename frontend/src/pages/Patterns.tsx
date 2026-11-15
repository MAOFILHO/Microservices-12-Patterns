import { Link } from "react-router-dom";
import { PATTERNS } from "../patterns/content";

export default function Patterns() {
  const liveCount = PATTERNS.filter((p) => p.live).length;
  return (
    <div className="grid" style={{ gap: "1.5rem" }}>
      <section className="card">
        <h1>The 12 patterns</h1>
        <p className="muted">
          Each pattern has a page that explains it, says when not to use it, and runs a live demo against the real
          services. {liveCount} of 12 are live; every one has a working demo.
        </p>
      </section>
      <div className="grid cols-3">
        {PATTERNS.map((p) =>
          p.live ? (
            <Link key={p.n} to={`/patterns/${p.slug}`} className="card" style={{ textDecoration: "none", color: "inherit" }}>
              <h3>
                {p.n}. {p.name}
              </h3>
              <p className="muted">{p.what}</p>
              <span className="pill done">Live demo</span>
            </Link>
          ) : (
            <div key={p.n} className="card" style={{ opacity: 0.7 }}>
              <h3>
                {p.n}. {p.name}
              </h3>
              <p className="muted">{p.what}</p>
              <span className="pill pending">Coming in {p.milestone}</span>
            </div>
          ),
        )}
      </div>
    </div>
  );
}
