import { useEffect, useState } from "react";
import { EventsView, asyncApi, savedToken } from "../../api/gatewayClient";

function time(iso: string | null): string {
  return iso ? new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`).toLocaleTimeString() : "–";
}

export default function EventDrivenDemo() {
  const token = savedToken();
  const [view, setView] = useState<EventsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function load() {
    asyncApi
      .events()
      .then((v) => {
        setView(v);
        setError(null);
      })
      .catch((err) => setError(String(err)));
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 1500);
    return () => clearInterval(timer);
  }, []);

  async function setBus(connected: boolean) {
    const { status, body } = await asyncApi.setBus(connected);
    setMessage(status === 200 ? (connected ? "Bus reconnected. Watch the waiting events go out." : "Bus disconnected. Buy something and watch the event wait.") : body.message ?? `HTTP ${status}`);
    load();
  }

  async function buyOne() {
    if (!token) return;
    setBusy(true);
    try {
      await asyncApi.addToCart(token, 1, 1);
      const { status, body } = await asyncApi.checkout(token, false);
      setMessage(status === 200 ? "Bought 1 mug. OrderConfirmed is in the outbox." : body.message ?? `HTTP ${status}`);
    } finally {
      setBusy(false);
      load();
    }
  }

  const connected = view?.bus_connected?.every(Boolean) ?? true;
  const mug = view?.stock?.find((s) => s.product_id === 1);

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      {error && <p style={{ color: "var(--contoso-danger)" }}>{error}</p>}
      <div className="grid cols-2">
        <div>
          <h3>The bus</h3>
          <p>
            <span className={`pill ${connected ? "done" : "failed"}`}>{connected ? "connected" : "disconnected"}</span>{" "}
            <span className="muted">
              {view?.outbox ? `${view.outbox.pending} event(s) waiting in the outbox` : "order service unreachable"}
            </span>
          </p>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button className="btn secondary" onClick={() => setBus(false)} disabled={!view?.chaos_enabled || !connected}>
              Disconnect the bus
            </button>
            <button className="btn secondary" onClick={() => setBus(true)} disabled={!view?.chaos_enabled || connected}>
              Reconnect
            </button>
            {token && (
              <button className="btn" onClick={buyOne} disabled={busy}>
                {busy ? "Buying…" : "Buy 1 mug"}
              </button>
            )}
          </div>
          {!view?.chaos_enabled && <p className="muted">Demo switches are off. Run the stack with make run to use them.</p>}
          {message && <p className="muted" style={{ fontSize: "0.85rem" }}>{message}</p>}
        </div>
        <div>
          <h3>Mug stock in inventory</h3>
          {mug && (
            <table className="data-table">
              <tbody>
                <tr>
                  <td>On hand</td>
                  <td>{mug.on_hand}</td>
                </tr>
                <tr>
                  <td>Held, waiting for OrderConfirmed</td>
                  <td>{mug.reserved}</td>
                </tr>
              </tbody>
            </table>
          )}
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            While the bus is down, a sale stays "held". Inventory sells it as soon as the event arrives.
          </p>
        </div>
      </div>

      <div className="grid cols-2">
        <div>
          <h3>Order's outbox (publisher)</h3>
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            Saved in the same database transaction as the order. A relay publishes it to Redis, once a second.
          </p>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Saved</th>
                  <th>Status</th>
                  <th>Tries</th>
                </tr>
              </thead>
              <tbody>
                {view?.outbox?.results.slice(0, 8).map((e) => (
                  <tr key={e.event_id}>
                    <td>
                      <code>{e.type}</code>
                    </td>
                    <td>{time(e.created_at)}</td>
                    <td>
                      <span className={`pill ${e.published_at ? "done" : "pending"}`}>
                        {e.published_at ? `published ${time(e.published_at)}` : "waiting"}
                      </span>
                    </td>
                    <td>{e.attempts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h3>What inventory did (consumer)</h3>
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            Reads the stream in the "inventory" consumer group. Each event is acted on once, even if delivered twice.
          </p>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Handled</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {view?.consumed?.slice(0, 8).map((e) => (
                  <tr key={e.event_id}>
                    <td>
                      <code>{e.type}</code>
                    </td>
                    <td>{time(e.handled_at)}</td>
                    <td>{e.outcome}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
