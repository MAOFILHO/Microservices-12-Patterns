import { Link } from "react-router-dom";
import { PATTERNS } from "../patterns/content";

export default function Patterns() {
  const patterns = PATTERNS.filter((p) => p.n <= 12); // demos 13-15 are bonuses, not patterns
  const liveCount = patterns.filter((p) => p.live).length;
  return (
    <div className="grid" style={{ gap: "1.5rem" }}>
      <section className="card">
        <h1>The 12 patterns, plus demos 13, 14 and 15</h1>
        <p className="muted">
          Each pattern has a page that explains it, says when not to use it, and runs a live demo against the real
          services. {liveCount} of {patterns.length} are live. Demo 13 puts patterns 4 and 8 under a slow payment; demo 14 puts the saga's undo under timeouts and duplicate events; demo 15 runs a flash sale under a replica cap of 3 and of 8.
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
