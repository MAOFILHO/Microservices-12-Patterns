import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { SagaRun, StockRow, asyncApi, savedToken } from "../../api/gatewayClient";

export const STEP_LABEL: Record<string, string> = {
  price: "1. Price the cart (catalog)",
  reserve_stock: "2. Hold the stock (inventory)",
  charge_payment: "3. Charge the card (payment)",
  check_payment: "3b. Ask payment what happened (demo 13)",
  confirm: "4. Confirm the order",
  release_stock: "Undo step 2: release the stock",
};

export const PILL: Record<string, string> = { done: "done", failed: "failed", compensated: "running", timed_out: "failed" };
const DEMO_PRODUCT = 1;

export default function SagaDemo() {
  const token = savedToken();
  const [decline, setDecline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [sagas, setSagas] = useState<SagaRun[]>([]);
  const [stock, setStock] = useState<StockRow | null>(null);

  async function refresh() {
    if (!token) return;
    const [history, view] = await Promise.all([asyncApi.sagas(token).catch(() => null), asyncApi.events().catch(() => null)]);
    if (history) setSagas(history.results);
    setStock(view?.stock?.find((s) => s.product_id === DEMO_PRODUCT) ?? null);
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!token) {
    return (
      <p>
        This demo checks out a real cart, so it needs a signed-in user. <Link to="/shop">Register or log in on the Shop
        page</Link>, then come back.
      </p>
    );
  }

  async function buy() {
    if (!token) return;
    setBusy(true);
    setResult(null);
    try {
      await asyncApi.addToCart(token, DEMO_PRODUCT, 2);
      const { status, body } = await asyncApi.checkout(token, decline);
      setResult({ ok: status === 200, message: status === 200 ? "Order placed. Payment approved." : body.message ?? `HTTP ${status}` });
    } catch (err) {
      setResult({ ok: false, message: String(err) });
    } finally {
      await refresh();
      setTimeout(refresh, 1500); // inventory sells the hold a moment later, when it reads the event
      setBusy(false);
    }
  }

  const latest = sagas[0];

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div className="grid cols-2">
        <div>
          <h3>Step 1. Buy 2 Contoso Mugs</h3>
          <p className="muted">Adds 2 mugs to your cart and checks out. The order service runs the saga below.</p>
          <label style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "0.75rem" }}>
            <input type="checkbox" checked={decline} onChange={(e) => setDecline(e.target.checked)} />
            Make the bank decline the card
          </label>
          <button className="btn" onClick={buy} disabled={busy}>
            {busy ? "Checking out…" : "Buy 2 mugs"}
          </button>
          {result && (
            <p>
              <span className={`pill ${result.ok ? "done" : "failed"}`}>{result.ok ? "Completed" : "Rolled back"}</span>{" "}
              {result.message}
            </p>
          )}
        </div>
        <div>
          <h3>Mug stock in inventory</h3>
          {stock ? (
            <table className="data-table">
              <tbody>
                <tr>
                  <td>On hand</td>
                  <td>{stock.on_hand}</td>
                </tr>
                <tr>
                  <td>Held for checkouts in progress</td>
                  <td>{stock.reserved}</td>
                </tr>
                <tr>
                  <td>Available to sell</td>
                  <td>{stock.available}</td>
                </tr>
              </tbody>
            </table>
          ) : (
            <p className="muted">Inventory is unreachable.</p>
          )}
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            A declined card leaves all 3 numbers as they were. An approved one lowers on hand by 2, once inventory reads
            the OrderConfirmed event.
          </p>
        </div>
      </div>

      {latest && (
        <div>
          <h3>Step 2. What the saga did</h3>
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            Saga <code>{latest.saga_id.slice(0, 8)}</code> for order #{latest.order_id}:{" "}
            <span className={`pill ${latest.outcome === "completed" ? "done" : latest.outcome === "compensated" || latest.outcome === "pending" ? "running" : "failed"}`}>
              {latest.outcome}
            </span>
          </p>
          <ol className="saga-timeline">
            {latest.steps.map((s, i) => (
              <li key={i} className={`saga-step ${s.status}`}>
                <span className={`pill ${PILL[s.status] ?? "pending"}`}>{s.status}</span>
                <strong>{STEP_LABEL[s.step] ?? s.step}</strong>
                {s.detail && <span className="muted"> · {s.detail}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}

      {sagas.length > 1 && (
        <div>
          <h3>Your earlier checkouts</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Saga</th>
                <th>Order</th>
                <th>Outcome</th>
                <th>Stopped at</th>
              </tr>
            </thead>
            <tbody>
              {sagas.slice(1).map((s) => (
                <tr key={s.saga_id}>
                  <td>
                    <code>{s.saga_id.slice(0, 8)}</code>
                  </td>
                  <td>#{s.order_id}</td>
                  <td>{s.outcome}</td>
                  <td>{s.steps.find((x) => x.status === "failed")?.step ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
