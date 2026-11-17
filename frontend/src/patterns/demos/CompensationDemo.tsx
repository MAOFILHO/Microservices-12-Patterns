import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  HandledEvent,
  HoldRow,
  SagaRun,
  StockRow,
  asyncApi,
  compensationApi,
  savedToken,
} from "../../api/gatewayClient";
import { PILL, STEP_LABEL } from "./SagaDemo";

const DEMO_PRODUCT = 1;
const POLL_MS = 2000;

const MODES: { mode: string; label: string; what: string }[] = [
  { mode: "slow_reserve", label: "Hold arrives late", what: "Inventory takes the hold 6 s late. The saga waits 3 s, gives up, and sends a release, which arrives first." },
  { mode: "slow_release", label: "Release times out", what: "Inventory releases 6 s late. The saga's direct release times out after 3 s, so it also sends the release as an event. The event copy lands first (about 4 s), the direct call second (6 s): 2 copies, 1 release." },
  { mode: "healthy", label: "Healthy", what: "Inventory answers at once." },
];

/** Demo 14: compensation under timeouts and duplicate events. Does the stock end where it began? */
export default function CompensationDemo() {
  const token = savedToken();
  const [mode, setMode] = useState("unknown");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [before, setBefore] = useState<StockRow | null>(null);
  const [stock, setStock] = useState<StockRow | null>(null);
  const [saga, setSaga] = useState<SagaRun | null>(null);
  const [hold, setHold] = useState<HoldRow | null>(null);
  const [handled, setHandled] = useState<HandledEvent[]>([]);
  const [counts, setCounts] = useState<{ skipped: number; notHandled: number } | null>(null);
  const [replayed, setReplayed] = useState<{ count: number; skippedAt: number; notHandledAt: number } | null>(null);

  async function refresh(): Promise<StockRow | null> {
    if (!token) return null;
    const [history, view, holds, events, chaos] = await Promise.all([
      asyncApi.sagas(token).catch(() => null),
      asyncApi.events().catch(() => null),
      compensationApi.holds().catch(() => null),
      compensationApi.handled().catch(() => null),
      compensationApi.inventoryMode().catch(() => null),
    ]);
    const latest = history?.results[0] ?? null;
    const row = view?.stock?.find((s) => s.product_id === DEMO_PRODUCT) ?? null;
    setSaga(latest);
    setStock(row);
    setHold(latest ? holds?.results.find((h) => h.reservation_id === latest.saga_id) ?? null : null);
    setHandled(latest && events ? events.results.filter((e) => e.reservation_id === latest.saga_id) : []);
    if (events) setCounts({ skipped: events.duplicates_skipped, notHandled: events.not_handled });
    if (chaos) setMode(chaos.mode);
    return row;
  }

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
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

  async function switchInventory(next: string) {
    setError(null);
    const { status, body } = await compensationApi.setInventoryMode(next);
    if (status === 200 && body.mode) setMode(body.mode);
    else setError(body.message ?? `HTTP ${status}`);
  }

  async function buy(decline: boolean) {
    if (!token) return;
    setBusy(true);
    setAnswer(null);
    setReplayed(null);
    try {
      setBefore(await refresh());
      await asyncApi.addToCart(token, DEMO_PRODUCT, 2);
      const { status, body } = await asyncApi.checkout(token, decline);
      setAnswer(`HTTP ${status}: ${body.message ?? (status === 200 ? "Order placed." : "")}`);
    } catch (err) {
      setAnswer(String(err));
    } finally {
      await refresh();
      setBusy(false);
    }
  }

  async function replay() {
    if (!token || !saga) return;
    setError(null);
    const { status, body } = await compensationApi.replay(token, saga.saga_id);
    if (status === 200)
      setReplayed({ count: body.replayed ?? 0, skippedAt: counts?.skipped ?? 0, notHandledAt: counts?.notHandled ?? 0 });
    else setError(body.message ?? `HTTP ${status}`);
  }

  const restored = before && stock && stock.on_hand === before.on_hand && stock.reserved === before.reserved;
  const sold = before && stock && stock.on_hand === before.on_hand - 2 && stock.reserved === before.reserved;
  const verdict = !before || !stock
    ? null
    : restored
      ? "Back where it began: same mugs on hand, nothing held."
      : sold
        ? "Sold once: 2 mugs fewer on hand, nothing held."
        : `Not settled yet: on hand ${before.on_hand} -> ${stock.on_hand}, held ${before.reserved} -> ${stock.reserved}.`;

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div className="grid cols-2">
        <div>
          <h3>Step 1. Pick what goes wrong in inventory</h3>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {MODES.map((m) => (
              <button key={m.mode} className="btn" onClick={() => switchInventory(m.mode)} disabled={mode === m.mode}>
                {m.label}
              </button>
            ))}
          </div>
          <p className="muted">{MODES.find((m) => m.mode === mode)?.what ?? "Inventory mode unknown."}</p>
          {error && <p className="muted">{error}</p>}

          <h3 style={{ marginTop: "1rem" }}>Step 2. Buy 2 Contoso Mugs</h3>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button className="btn" onClick={() => buy(false)} disabled={busy}>
              Buy 2 mugs
            </button>
            <button className="btn" onClick={() => buy(true)} disabled={busy}>
              Buy 2 mugs, card declined
            </button>
          </div>
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            "Hold arrives late" goes with Buy. "Release times out" goes with card declined, so the saga has to undo.
          </p>
          {busy && <p className="muted">Checking out…</p>}
          {answer && <p>{answer}</p>}

          <h3 style={{ marginTop: "1rem" }}>Step 3. Send this checkout's events again</h3>
          <button className="btn" onClick={replay} disabled={!saga || busy}>
            Replay its events
          </button>
          {replayed && counts && (
            <p className="muted">
              Sent {replayed.count} event(s) again with the same ids. Since then, inventory skipped{" "}
              {counts.skipped - replayed.skippedAt} it had already acted on, and ignored{" "}
              {counts.notHandled - replayed.notHandledAt} that are not its business (counts include any other checkout
              running now).
            </p>
          )}
        </div>

        <div>
          <h3>Where the stock is</h3>
          <table className="data-table">
            <tbody>
              <tr>
                <td>Hold for this checkout</td>
                <td>{hold ? `${hold.status}${hold.items.length === 0 ? " (release came first, nothing held)" : ""}` : "none yet"}</td>
              </tr>
              <tr>
                <td>Release requests received</td>
                <td>{hold ? hold.releases_received : "–"}</td>
              </tr>
              <tr>
                <td>Mugs on hand</td>
                <td>{before && stock ? `${before.on_hand} -> ${stock.on_hand}` : stock?.on_hand ?? "?"}</td>
              </tr>
              <tr>
                <td>Mugs held for checkouts</td>
                <td>{before && stock ? `${before.reserved} -> ${stock.reserved}` : stock?.reserved ?? "?"}</td>
              </tr>
              <tr>
                <td>Events inventory acted on</td>
                <td>{handled.length === 0 ? "none" : handled.map((e) => `${e.type}: ${e.outcome}`).join("; ")}</td>
              </tr>
              <tr>
                <td>Duplicate events skipped (all checkouts)</td>
                <td>{counts?.skipped ?? "?"}</td>
              </tr>
            </tbody>
          </table>
          {verdict && <p className="muted">{verdict}</p>}
          <p className="muted" style={{ fontSize: "0.85rem" }}>Refreshes every 2 s. A slow step lands about 6 s after the click.</p>
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
