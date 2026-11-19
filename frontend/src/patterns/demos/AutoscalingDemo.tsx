import { SERVICE_NAMES } from "../content";
import results from "./flashSaleResults.json";

interface AppUsage {
  replica_seconds: number;
  cooldown_replica_seconds: number;
  peak_replicas: number;
  requests: number;
}

interface FlashSaleRun {
  cap: number;
  buyers: number;
  seconds: number;
  region: string;
  ran_at: string;
  attempts: number;
  completed: number;
  success_rate: number;
  by_status: Record<string, number>;
  p50_ms: number;
  p95_ms: number;
  orders_per_minute: number;
  usage: Record<string, AppUsage>;
  cost_usd: { replicas: number; requests: number; mysql: number; total: number };
  cost_per_1k_usd: number | null;
}

const RUNS = results.runs as FlashSaleRun[];
const PRICES = results.prices;

function replicaMinutes(run: FlashSaleRun, key: "replica_seconds" | "cooldown_replica_seconds") {
  return Math.round(SERVICE_NAMES.reduce((sum, n) => sum + (run.usage[n]?.[key] ?? 0), 0) / 60);
}

function pct(share: number) {
  return `${(share * 100).toFixed(1)}%`;
}

function usd(value: number | null) {
  return value === null ? "–" : `$${value.toFixed(4)}`;
}

const STATUS_LABEL: Record<string, string> = {
  "202": "payment pending",
  "409": "sold out or pending",
  "503": "a service was down or its breaker open",
  "no answer": "no answer in 30 s",
};

function failures(run: FlashSaleRun) {
  const lost = Object.entries(run.by_status).filter(([status]) => status !== "200");
  return lost.length === 0
    ? "none"
    : lost.map(([status, n]) => `${n} × ${status} (${STATUS_LABEL[status] ?? "error"})`).join(", ");
}

/** Demo 15: the same flash sale twice in Azure, with a replica cap of 3 and of 8. Recorded, not live. */
export default function AutoscalingDemo() {
  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div>
        <h3>The experiment</h3>
        <p className="muted">
          Many buyers sign in, then each adds 1 item and checks out, again and again, for the same time. Azure Container
          Apps adds a replica when each replica of a service is handling more than 10 requests at once, up to the cap. Run 1 caps every service at
          3 replicas, run 2 at 8. Nothing else changes: the same 0.25 vCPU replicas, the same single MySQL server.
        </p>
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          Recorded in Azure with <code>make flash-sale CAP=3</code> and <code>CAP=8</code>, then torn down: the stack does
          not stay up, so this page shows the saved numbers.
        </p>
      </div>

      {RUNS.length === 0 ? (
        <p>No run recorded yet.</p>
      ) : (
        <>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th></th>
                  {RUNS.map((r) => (
                    <th key={r.cap}>Cap {r.cap}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Checkout success rate</td>
                  {RUNS.map((r) => (
                    <td key={r.cap}>
                      <strong>{pct(r.success_rate)}</strong> ({r.completed} of {r.attempts})
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Completed orders per minute</td>
                  {RUNS.map((r) => (
                    <td key={r.cap}>{r.orders_per_minute}</td>
                  ))}
                </tr>
                <tr>
                  <td>Checkout time, median / 95th percentile</td>
                  {RUNS.map((r) => (
                    <td key={r.cap}>
                      {Math.round(r.p50_ms)} ms / {Math.round(r.p95_ms)} ms
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Lost sales (HTTP status)</td>
                  {RUNS.map((r) => (
                    <td key={r.cap}>{failures(r)}</td>
                  ))}
                </tr>
                <tr>
                  <td>Peak replicas (gateway, order)</td>
                  {RUNS.map((r) => (
                    <td key={r.cap}>
                      {r.usage.gateway?.peak_replicas ?? "?"}, {r.usage.order?.peak_replicas ?? "?"}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Replica time, all 6 services: sale / cooldown</td>
                  {RUNS.map((r) => (
                    <td key={r.cap}>
                      {replicaMinutes(r, "replica_seconds")} / {replicaMinutes(r, "cooldown_replica_seconds")} replica-minutes
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>Cost of the run: replicas + requests + MySQL</td>
                  {RUNS.map((r) => (
                    <td key={r.cap}>
                      {usd(r.cost_usd.total)} = {usd(r.cost_usd.replicas)} + {usd(r.cost_usd.requests)} +{" "}
                      {usd(r.cost_usd.mysql)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>
                    <strong>Cost per 1,000 completed orders</strong>
                  </td>
                  {RUNS.map((r) => (
                    <td key={r.cap}>
                      <strong>{usd(r.cost_per_1k_usd)}</strong>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            {RUNS.map((r) => `Cap ${r.cap}: ${r.buyers} buyers for ${r.seconds} s in ${r.region}, ${r.ran_at}.`).join(" ")}{" "}
            Both runs start from 2,500 free units of each product. A buyer whose checkout fails pays for the same 1-item
            cart again, so every completed order is 1 item. Azure's list prices before the monthly free grant: replicas
            during the sale at the active rate (${PRICES.vcpu_second} per vCPU-second, ${PRICES.gib_second} per
            GiB-second), replicas in the 5-minute cooldown after it at the idle rate (${PRICES.idle_vcpu_second} per
            vCPU-second), ${PRICES.per_million_requests} per million requests, and the MySQL server at $
            {PRICES.mysql_hour} an hour for the same time.
          </p>
        </>
      )}
    </div>
  );
}
