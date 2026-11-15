import { useEffect, useState } from "react";
import { BreakerCall, BreakerState, resilienceApi } from "../../api/gatewayClient";

const MODES: { mode: string; label: string; help: string }[] = [
  { mode: "healthy", label: "Healthy", help: "answers at once" },
  { mode: "failing", label: "Failing", help: "every call returns 500" },
  { mode: "slow", label: "Slow", help: "every call takes 3 s; order gives up after 1 s" },
];

const PILL: Record<string, string> = { closed: "done", open: "failed", "half-open": "running", unreachable: "pending" };

interface LogRow extends BreakerCall {
  n: number;
}

export default function CircuitBreakerDemo() {
  const [breakers, setBreakers] = useState<BreakerState[]>([]);
  const [paymentMode, setPaymentMode] = useState<string>("");
  const [chaos, setChaos] = useState(true);
  const [log, setLog] = useState<LogRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function loadState() {
    resilienceApi
      .breakerState()
      .then((s) => {
        setBreakers(s.breakers);
        setPaymentMode(s.payment.mode);
        setChaos(s.chaos_enabled);
      })
      .catch((err) => setError(String(err)));
  }

  useEffect(() => {
    loadState();
    const timer = setInterval(loadState, 1000);
    return () => clearInterval(timer);
  }, []);

  async function setMode(mode: string) {
    const { status, body } = await resilienceApi.setPaymentMode(mode);
    setError(status === 200 ? null : body.message ?? `HTTP ${status}`);
    loadState();
  }

  async function send(count: number) {
    setBusy(true);
    let n = log.length ? log[0].n : 0;
    for (let i = 0; i < count; i++) {
      const { body } = await resilienceApi.breakerCall();
      n += 1;
      const row = { ...body, n };
      setLog((prev) => [row, ...prev].slice(0, 30));
    }
    setBusy(false);
    loadState();
  }

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div className="grid cols-2">
        <div>
          <h3>Step 1. Choose how the payment service behaves</h3>
          {!chaos && <p className="muted">Demo switches are off. Run the stack with make run to use them.</p>}
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {MODES.map((m) => (
              <button
                key={m.mode}
                className={`btn ${paymentMode === m.mode ? "" : "secondary"}`}
                onClick={() => setMode(m.mode)}
                disabled={!chaos}
                title={m.help}
              >
                {m.label}
              </button>
            ))}
          </div>
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            Payment is now <strong>{paymentMode || "unknown"}</strong>: {MODES.find((m) => m.mode === paymentMode)?.help ?? "–"}.
          </p>
          {error && <p style={{ color: "var(--contoso-danger)" }}>{error}</p>}
        </div>
        <div>
          <h3>Each order replica's breaker</h3>
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            Opens after 3 failed calls in a row. While open, calls fail at once without reaching payment. After 15 s,
            one trial call decides whether it closes again.
          </p>
          <table className="data-table">
            <thead>
              <tr>
                <th>Replica</th>
                <th>State</th>
                <th>Failures</th>
                <th>Retry in</th>
              </tr>
            </thead>
            <tbody>
              {breakers.map((b) => (
                <tr key={b.instance ?? "?"}>
                  <td>
                    <span className="svc-dot svc-order" />
                    {b.instance}
                  </td>
                  <td>
                    <span className={`pill ${PILL[b.state] ?? "pending"}`}>{b.state.toUpperCase()}</span>
                  </td>
                  <td>
                    {b.failures_in_a_row ?? "–"} / {b.fail_max ?? "–"}
                  </td>
                  <td>{b.retry_in_seconds ? `${Math.ceil(b.retry_in_seconds)} s` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h3>Step 2. Send calls from order to payment</h3>
        <p className="muted">
          The gateway sends each call to the next order replica, which calls payment through its breaker. Compare the
          time of a real failure with a call the open breaker stopped.
        </p>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button className="btn" onClick={() => send(1)} disabled={busy}>
            Send 1 call
          </button>
          <button className="btn" onClick={() => send(10)} disabled={busy}>
            {busy ? "Sending…" : "Send 10 calls"}
          </button>
          <button className="btn secondary" onClick={() => setLog([])} disabled={busy}>
            Clear
          </button>
        </div>
        {log.length > 0 && (
          <table className="data-table" style={{ marginTop: "0.75rem" }}>
            <thead>
              <tr>
                <th>Call</th>
                <th>Replica</th>
                <th>Outcome</th>
                <th>Time in order</th>
                <th>Breaker after</th>
              </tr>
            </thead>
            <tbody>
              {log.map((r) => (
                <tr key={r.n}>
                  <td>{r.n}</td>
                  <td>
                    <code>{r.instance ?? "–"}</code>
                  </td>
                  <td>
                    <span className={`pill ${r.outcome === "ok" ? "done" : r.outcome === "short-circuited" ? "running" : "failed"}`}>
                      {r.outcome}
                    </span>
                  </td>
                  <td>{r.ms !== undefined ? `${r.ms} ms` : "–"}</td>
                  <td>{r.breaker?.state ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
