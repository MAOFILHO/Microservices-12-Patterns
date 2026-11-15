import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { RegistryInstance, resilienceApi, savedToken } from "../../api/gatewayClient";

interface Row {
  n: number;
  instance: string | null;
  status: number;
  items: number | null;
}

/** The middle part of a JWT is plain base64url JSON: anyone can read it, only the user service can sign it. */
function readClaims(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(part)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function StatelessDemo() {
  const token = savedToken();
  const [rows, setRows] = useState<Row[]>([]);
  const [replicas, setReplicas] = useState<RegistryInstance[]>([]);
  const [mode, setMode] = useState<string>("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function loadReplicas() {
    resilienceApi
      .registry()
      .then((view) => {
        setMode(view.mode);
        setReplicas(view.services.order ?? []);
      })
      .catch(() => setReplicas([]));
  }

  useEffect(() => {
    loadReplicas();
    const timer = setInterval(loadReplicas, 2000);
    return () => clearInterval(timer);
  }, []);

  if (!token) {
    return (
      <p>
        This demo reads your cart, so it needs a signed-in user. <Link to="/shop">Register or log in on the Shop
        page</Link>, add something to your cart, then come back.
      </p>
    );
  }

  async function askSixTimes() {
    if (!token) return;
    setBusy(true);
    const next: Row[] = [];
    for (let n = 1; n <= 6; n++) {
      try {
        const { status, instance, body } = await resilienceApi.cartFromAnyReplica(token);
        next.push({ n, instance, status, items: status === 200 ? (body.result?.items.reduce((sum, i) => sum + i.quantity, 0) ?? 0) : null });
      } catch {
        next.push({ n, instance: null, status: 0, items: null });
      }
      setRows([...next]);
    }
    setBusy(false);
  }

  async function stop(instanceId: string) {
    const { body } = await resilienceApi.stopReplica(instanceId);
    setMessage(body.stopping ? `${body.stopping} stopped. make run restarts it in about 20 seconds.` : body.message ?? null);
    setTimeout(loadReplicas, 500);
  }

  const claims = readClaims(token);
  const served = new Set(rows.filter((r) => r.instance).map((r) => r.instance));
  const sameCart = rows.length > 0 && new Set(rows.map((r) => r.items)).size === 1 && rows.every((r) => r.status === 200);

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div className="grid cols-2">
        <div>
          <h3>Step 1. Your login is a signed token, not a server session</h3>
          <p className="muted">
            Your browser holds this. Every service can check the signature with the user service's public key, so no
            server has to remember you.
          </p>
          <pre className="log-box">{JSON.stringify(claims, null, 2)}</pre>
        </div>
        <div>
          <h3>Order replicas running now</h3>
          {mode !== "registry" && (
            <p className="muted">No registry ({mode}): only one order replica is in use. Run the stack with make run.</p>
          )}
          <table className="data-table">
            <thead>
              <tr>
                <th>Replica</th>
                <th>Up for</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {replicas.map((r) => (
                <tr key={r.instance_id}>
                  <td>
                    <span className="svc-dot svc-order" />
                    {r.instance_id}
                  </td>
                  <td>{r.up_for_s === null ? "–" : `${Math.round(r.up_for_s)} s`}</td>
                  <td>
                    {mode === "registry" && (
                      <button className="btn secondary" onClick={() => stop(r.instance_id)} disabled={replicas.length < 2}>
                        Stop
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {message && <p className="muted" style={{ fontSize: "0.85rem" }}>{message}</p>}
        </div>
      </div>

      <div>
        <h3>Step 2. Ask for your cart 6 times</h3>
        <p className="muted">
          The gateway spreads the calls across the order replicas. Stop one replica above, then ask again: you stay
          logged in and your cart is unchanged, because neither lived in the replica.
        </p>
        <button className="btn" onClick={askSixTimes} disabled={busy}>
          {busy ? "Asking…" : "Ask for my cart 6 times"}
        </button>
        {rows.length > 0 && (
          <>
            <table className="data-table" style={{ marginTop: "0.75rem" }}>
              <thead>
                <tr>
                  <th>Call</th>
                  <th>Answered by</th>
                  <th>Status</th>
                  <th>Items in cart</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.n}>
                    <td>{r.n}</td>
                    <td>
                      <code>{r.instance ?? "no answer"}</code>
                    </td>
                    <td>{r.status || "failed"}</td>
                    <td>{r.items ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!busy && (
              <p>
                <span className={`pill ${sameCart ? "done" : "failed"}`}>
                  {sameCart ? "Same cart every time" : "Not every call succeeded"}
                </span>{" "}
                <span className="muted">
                  {served.size} replica{served.size === 1 ? "" : "s"} answered.
                </span>
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
