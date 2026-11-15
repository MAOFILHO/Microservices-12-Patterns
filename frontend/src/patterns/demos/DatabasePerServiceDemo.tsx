import { useEffect, useState } from "react";
import { IsolationResult, ServiceDatabase, patternsApi } from "../../api/gatewayClient";

const FOREIGN_TABLES: { table: string; owner: string }[] = [
  { table: "product", owner: "catalog" },
  { table: "stock_item", owner: "inventory" },
  { table: "payment", owner: "payment" },
  { table: "user", owner: "user" },
];

export default function DatabasePerServiceDemo() {
  const [services, setServices] = useState<ServiceDatabase[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isolation, setIsolation] = useState<IsolationResult | null>(null);
  const [busyTable, setBusyTable] = useState<string | null>(null);

  function load() {
    setError(null);
    patternsApi
      .databases()
      .then((data) => setServices(data.services))
      .catch((err) => setError(String(err)));
  }

  useEffect(load, []);

  async function tryRead(table: string) {
    setBusyTable(table);
    try {
      setIsolation(await patternsApi.isolationTest(table));
    } catch (err) {
      setError(String(err));
    } finally {
      setBusyTable(null);
    }
  }

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div>
        <h3>Step 1. Each service reports the database it owns</h3>
        <p className="muted">
          The gateway asks every service for <code>/health/db</code>. Each answer lists only that service's own tables.
        </p>
        {error && <p style={{ color: "var(--contoso-danger)" }}>{error}</p>}
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Service</th>
                <th>Engine</th>
                <th>Database</th>
                <th>Tables it owns</th>
              </tr>
            </thead>
            <tbody>
              {services?.map((s) => (
                <tr key={s.service}>
                  <td>
                    <span className={`svc-dot svc-${s.service}`} />
                    {s.service}
                  </td>
                  {s.reachable ? (
                    <>
                      <td>{s.engine}</td>
                      <td>
                        <code>{s.database}</code>
                      </td>
                      <td>{s.tables?.join(", ")}</td>
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
        </div>
        <button className="btn secondary" style={{ marginTop: "0.75rem" }} onClick={load}>
          Refresh
        </button>
      </div>

      <div>
        <h3>Step 2. Make the order service read another service's table</h3>
        <p className="muted">
          This runs real SQL through the order service's own connection. It fails because that table lives in another
          database.
        </p>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {FOREIGN_TABLES.map(({ table, owner }) => (
            <button key={table} className="btn" disabled={busyTable !== null} onClick={() => tryRead(table)}>
              Read {owner}'s <code style={{ color: "inherit" }}>{table}</code>
            </button>
          ))}
        </div>
        {isolation && (
          <div className="card" style={{ marginTop: "0.75rem", borderColor: isolation.blocked ? "var(--contoso-success)" : "var(--contoso-danger)" }}>
            <p style={{ margin: 0 }}>
              <span className={`pill ${isolation.blocked ? "done" : "failed"}`}>
                {isolation.blocked ? "Blocked, as designed" : "Not blocked"}
              </span>
            </p>
            <p>
              Ran <code>{isolation.attempted}</code> in the order database.
            </p>
            {isolation.error && (
              <p>
                Database said: <code>{isolation.error}</code>
              </p>
            )}
            <p className="muted" style={{ marginBottom: 0 }}>
              The order database only has: {isolation.order_tables.join(", ")}. To get {isolation.owner} data, the order
              service must call the {isolation.owner} service's API.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
