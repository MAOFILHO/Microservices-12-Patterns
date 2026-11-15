import { useState } from "react";
import { Link } from "react-router-dom";
import { OrderSummary, ServiceCall, patternsApi, savedApiKey } from "../../api/gatewayClient";

export default function ApiGatewayDemo() {
  const [summary, setSummary] = useState<OrderSummary | null>(null);
  const [calls, setCalls] = useState<ServiceCall[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const apiKey = savedApiKey();

  async function run() {
    if (!apiKey) return;
    setBusy(true);
    setError(null);
    try {
      const { body } = await patternsApi.orderSummary(apiKey);
      setSummary(body);
      setCalls(body.calls);
    } catch (err) {
      const body = (err as { body?: { message?: string; calls?: ServiceCall[] } }).body;
      setError(body?.message ?? String(err));
      setCalls(body?.calls ?? []);
      setSummary(null);
    } finally {
      setBusy(false);
    }
  }

  if (!apiKey) {
    return (
      <p>
        This demo builds your order summary, so it needs a signed-in user. <Link to="/shop">Register or log in on the
        Shop page</Link>, add something to your cart, then come back.
      </p>
    );
  }

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <p className="muted" style={{ margin: 0 }}>
        The browser makes <strong>one</strong> call: <code>GET /api/order-summary</code>. The gateway fans it out to
        the services that own each piece, then returns one combined answer.
      </p>
      <div>
        <button className="btn" onClick={run} disabled={busy}>
          {busy ? "Calling…" : "Build my order summary"}
        </button>
      </div>
      {error && <p style={{ color: "var(--contoso-danger)" }}>{error}</p>}

      {calls.length > 0 && (
        <div className="grid cols-2">
          <div>
            <h3>What the gateway called</h3>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Path</th>
                  <th>Status</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((c, i) => (
                  <tr key={i}>
                    <td>
                      <span className={`svc-dot svc-${c.service}`} />
                      {c.service}
                    </td>
                    <td>
                      <code>{c.path}</code>
                    </td>
                    <td>{c.status}</td>
                    <td>{c.ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {summary && (
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                Request ID <code>{summary.request_id}</code> was forwarded to every call above, so their logs share it.
              </p>
            )}
          </div>
          {summary && (
            <div>
              <h3>What the browser got back</h3>
              <p>
                Signed in as <strong>{summary.user.username}</strong>
              </p>
              {summary.lines.length === 0 ? (
                <p className="muted">Your cart is empty. Add something on the Shop page and run this again.</p>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Product (catalog)</th>
                      <th>Qty (order)</th>
                      <th>In stock (inventory)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.lines.map((l) => (
                      <tr key={l.product_id}>
                        <td>
                          {l.name ?? `#${l.product_id}`} · ${((l.unit_price_cents ?? 0) / 100).toFixed(2)}
                        </td>
                        <td>{l.quantity}</td>
                        <td>{l.available ?? "unknown"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p>
                <strong>Total ${(summary.total_cents / 100).toFixed(2)}</strong>
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
