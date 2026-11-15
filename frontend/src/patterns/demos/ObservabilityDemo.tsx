import { useEffect, useState } from "react";
import { ServiceMetrics, Span, patternsApi, savedToken } from "../../api/gatewayClient";

function Waterfall({ spans }: { spans: Span[] }) {
  if (spans.length === 0) return <p className="muted">No spans found for this trace yet.</p>;
  const start = Math.min(...spans.map((s) => s.start_ns));
  const end = Math.max(...spans.map((s) => s.end_ns));
  const total = Math.max(end - start, 1);
  return (
    <div className="waterfall">
      {spans.map((s) => {
        const left = ((s.start_ns - start) / total) * 100;
        const width = ((s.end_ns - s.start_ns) / total) * 100;
        const ms = ((s.end_ns - s.start_ns) / 1e6).toFixed(1);
        return (
          <div key={s.span_id} className="waterfall-row" title={`${s.service}: ${s.name} (${ms} ms)`}>
            <span className="waterfall-label">
              <span className={`svc-dot svc-${s.service}`} />
              {s.service} · {s.name}
            </span>
            <span className="waterfall-track">
              <span className={`waterfall-bar svc-${s.service}`} style={{ left: `${left}%`, width: `${width}%` }} />
            </span>
          </div>
        );
      })}
      <p className="muted" style={{ fontSize: "0.8rem", marginBottom: 0 }}>
        {spans.length} spans across {new Set(spans.map((s) => s.service)).size} processes, {(total / 1e6).toFixed(1)} ms
        end to end.
      </p>
    </div>
  );
}

export default function ObservabilityDemo() {
  const [traceId, setTraceId] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [spans, setSpans] = useState<Span[]>([]);
  const [metrics, setMetrics] = useState<ServiceMetrics[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const token = savedToken();

  function loadMetrics() {
    patternsApi
      .metrics()
      .then((data) => setMetrics(data.services))
      .catch((err) => setError(String(err)));
  }

  useEffect(loadMetrics, []);

  async function sendTracedRequest() {
    setBusy(true);
    setError(null);
    try {
      // Signed in: the 4-service order summary. Otherwise: the 2-service bounded-context view.
      const result = token ? await patternsApi.orderSummary(token) : await patternsApi.boundedContext(1);
      setTraceId(result.traceId);
      setRequestId(result.requestId);
      if (result.traceId) {
        const data = await patternsApi.trace(result.traceId);
        setSpans(data.spans);
      }
      loadMetrics();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div>
        <h3>Traces: follow one click through every service</h3>
        <p className="muted">
          {token
            ? "Sends GET /api/order-summary (gateway, user, order, catalog, inventory), then collects that trace's spans from every process."
            : "Sends GET /api/patterns/bounded-context/1 (gateway, catalog, inventory). Log in on the Shop page to trace the bigger 4-service order summary."}
        </p>
        <button className="btn" onClick={sendTracedRequest} disabled={busy}>
          {busy ? "Tracing…" : "Send a traced request"}
        </button>
        {error && <p style={{ color: "var(--contoso-danger)" }}>{error}</p>}
        {traceId && (
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            trace_id <code>{traceId}</code> · request_id <code>{requestId}</code>. Every service's JSON log line for this
            click carries both.
          </p>
        )}
        {traceId && <Waterfall spans={spans} />}
      </div>

      <div>
        <h3>Metrics: requests and latency per service</h3>
        <p className="muted">Read live from each service's Prometheus <code>/metrics</code> endpoint.</p>
        <table className="data-table">
          <thead>
            <tr>
              <th>Service</th>
              <th>Requests</th>
              <th>5xx errors</th>
              <th>Avg latency</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <tr key={m.service}>
                <td>
                  <span className={`svc-dot svc-${m.service}`} />
                  {m.service}
                </td>
                {m.reachable ? (
                  <>
                    <td>{m.requests}</td>
                    <td>{m.errors_5xx}</td>
                    <td>{m.avg_ms === null || m.avg_ms === undefined ? "–" : `${m.avg_ms} ms`}</td>
                  </>
                ) : (
                  <td colSpan={3} style={{ color: "var(--contoso-danger)" }}>
                    unreachable
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        <button className="btn secondary" style={{ marginTop: "0.75rem" }} onClick={loadMetrics}>
          Refresh metrics
        </button>
      </div>
    </div>
  );
}
