import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PaymentRow, SagaRun, StockRow, asyncApi, resilienceApi, savedToken } from "../../api/gatewayClient";
import { PILL, STEP_LABEL } from "./SagaDemo";

const DEMO_PRODUCT = 1;
const POLL_MS = 2000;

/** Demo 13: slow payment down mid-checkout, then follow where the money and the stock end up. */
export default function SlowPaymentDemo() {
  const token = savedToken();
  const [mode, setMode] = useState<string>("unknown");
  const [modeError, setModeError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ kind: "done" | "running" | "failed"; label: string; message: string } | null>(null);
  const [saga, setSaga] = useState<SagaRun | null>(null);
  const [charges, setCharges] = useState<PaymentRow[]>([]);
  const [stock, setStock] = useState<StockRow | null>(null);

  async function refresh() {
    if (!token) return;
    const [history, payments, view, breaker] = await Promise.all([
      asyncApi.sagas(token).catch(() => null),
      asyncApi.payments().catch(() => null),
      asyncApi.events().catch(() => null),
      resilienceApi.breakerState().catch(() => null),
    ]);
    const latest = history?.results[0] ?? null;
    setSaga(latest);
    setCharges(latest && payments ? payments.results.filter((p) => p.idempotency_key === latest.saga_id) : []);
    setStock(view?.stock?.find((s) => s.product_id === DEMO_PRODUCT) ?? null);
    if (breaker) setMode(breaker.payment.mode);
  }

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS); // the reconciler settles pending orders every 5 s
    return () => clearInterval(timer);
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

  async function switchPayment(next: string) {
    setModeError(null);
    const { status, body } = await resilienceApi.setPaymentMode(next);
    if (status === 200 && body.mode) setMode(body.mode);
    else setModeError(body.message ?? `HTTP ${status}`);
  }

  async function buy() {
    if (!token) return;
    setBusy(true);
    setResult(null);
    try {
      await asyncApi.addToCart(token, DEMO_PRODUCT, 2);
      const { status, body } = await asyncApi.checkout(token, false);
      if (status === 200) setResult({ kind: "done", label: "Completed", message: "Order placed. Payment approved." });
      else if (status === 202) setResult({ kind: "running", label: "Pending", message: body.message ?? "Waiting for payment." });
      else setResult({ kind: "failed", label: "Not placed", message: body.message ?? `HTTP ${status}` });
    } catch (err) {
      setResult({ kind: "failed", label: "Error", message: String(err) });
    } finally {
      await refresh();
      setBusy(false);
    }
  }

  // A pending answer goes stale once the reconciler settles the order: show what it settled to.
  const shown =
    result?.kind === "running" && saga && saga.outcome !== "pending"
      ? saga.outcome === "completed"
        ? { kind: "done" as const, label: "Confirmed", message: "Payment answered APPROVED, so the order was confirmed." }
        : { kind: "failed" as const, label: "Released", message: "Payment declined or voided the charge, so the stock went back." }
      : result;
  const approved = charges.filter((c) => c.status === "APPROVED").length;
  const verdict = !saga
    ? null
    : saga.outcome === "pending"
      ? "Waiting: payment has not said yet. The mugs stay held, and the order cannot be paid for again."
      : saga.outcome === "completed"
        ? `Settled: ${approved} charge, 1 order, 2 mugs sold.`
        : `Settled: ${approved} charges, no order, the mugs went back to stock.`;

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div className="grid cols-2">
        <div>
          <h3>Step 1. Slow payment down</h3>
          <p className="muted">
            Payment now answers {mode === "slow" ? "after 3 s" : "at once"}. The order service waits 1 s, retries once,
            then gives up on the call.
          </p>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button className="btn" onClick={() => switchPayment("slow")} disabled={mode === "slow"}>
              Make payment slow
            </button>
            <button className="btn" onClick={() => switchPayment("healthy")} disabled={mode === "healthy"}>
              Make payment healthy
            </button>
          </div>
          {modeError && <p className="muted">{modeError}</p>}

          <h3 style={{ marginTop: "1rem" }}>Step 2. Buy 2 Contoso Mugs</h3>
          <button className="btn" onClick={buy} disabled={busy}>
            {busy ? "Checking out… (payment is slow)" : "Buy 2 mugs"}
          </button>
          {shown && (
            <p>
              <span className={`pill ${shown.kind}`}>{shown.label}</span> {shown.message}
            </p>
          )}
        </div>

        <div>
          <h3>Step 3. Where the money and the stock are</h3>
          <table className="data-table">
            <tbody>
              <tr>
                <td>Charges for this checkout</td>
                <td>
                  {charges.length === 0
                    ? "none"
                    : charges.map((c) => `#${c.id} ${c.status} ${(c.amount_cents / 100).toFixed(2)}`).join(", ")}
                </td>
              </tr>
              <tr>
                <td>Mugs on hand</td>
                <td>{stock?.on_hand ?? "?"}</td>
              </tr>
              <tr>
                <td>Mugs held for checkouts</td>
                <td>{stock?.reserved ?? "?"}</td>
              </tr>
              <tr>
                <td>Order</td>
                <td>{saga ? `#${saga.order_id} ${saga.outcome}` : "–"}</td>
              </tr>
            </tbody>
          </table>
          {verdict && <p className="muted">{verdict}</p>}
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            Refreshes every 2 s. A pending order settles within about 5 s of payment finishing.
          </p>
        </div>
      </div>

      {saga && (
        <div>
          <h3>What the saga did</h3>
          <ol className="saga-timeline">
            {saga.steps.map((s, i) => (
              <li key={i} className={`saga-step ${s.status}`}>
                <span className={`pill ${PILL[s.status] ?? "pending"}`}>{s.status}</span>
                <strong>{STEP_LABEL[s.step] ?? s.step}</strong>
                {s.detail && <span className="muted"> · {s.detail}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
