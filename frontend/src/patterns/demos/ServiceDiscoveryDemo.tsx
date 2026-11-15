import { useEffect, useState } from "react";
import { RegistryView, resilienceApi } from "../../api/gatewayClient";

export default function ServiceDiscoveryDemo() {
  const [view, setView] = useState<RegistryView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  function load() {
    resilienceApi
      .registry()
      .then((v) => {
        setView(v);
        setError(null);
      })
      .catch((err) => setError(String(err)));
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, []);

  async function stop(instanceId: string) {
    const { body } = await resilienceApi.stopReplica(instanceId);
    setMessage(
      body.stopping
        ? `${body.stopping} stopped without telling the registry. Watch its heartbeat age climb until it expires.`
        : body.message ?? null,
    );
  }

  const live = view?.mode === "registry";

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div>
        <h3>The registry, refreshed every 2 seconds</h3>
        {error && <p style={{ color: "var(--contoso-danger)" }}>{error}</p>}
        {view && !live && (
          <p className="muted">
            Mode: <strong>{view.mode}</strong>. The gateway is using its fixed URL list. Run the stack with make run to
            start the registry.
          </p>
        )}
        {live && (
          <p className="muted">
            Each instance re-registers every 2 s. One that is silent for more than {view?.ttl_seconds} s is dropped,
            and callers stop sending it traffic.
          </p>
        )}
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Service</th>
                <th>Instance</th>
                <th>Address</th>
                <th>Last heartbeat</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {view &&
                Object.entries(view.services).flatMap(([service, instances]) =>
                  instances.map((i) => {
                    const stale = i.last_heartbeat_s !== null && i.last_heartbeat_s > 3;
                    return (
                      <tr key={`${service}-${i.instance_id}`}>
                        <td>
                          <span className={`svc-dot svc-${service}`} />
                          {service}
                        </td>
                        <td>
                          <code>{i.instance_id}</code>
                        </td>
                        <td>
                          <code>{i.url}</code>
                        </td>
                        <td style={{ color: stale ? "var(--contoso-danger)" : undefined }}>
                          {i.last_heartbeat_s === null ? "–" : `${i.last_heartbeat_s.toFixed(1)} s ago`}
                        </td>
                        <td>
                          {live && (
                            <button className="btn secondary" onClick={() => stop(i.instance_id)}>
                              Stop
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  }),
                )}
            </tbody>
          </table>
        </div>
        {message && <p className="muted" style={{ fontSize: "0.85rem" }}>{message}</p>}
      </div>

      {live && (
        <div>
          <h3>What the registry saw</h3>
          <p className="muted">A stopped instance is marked expired by the registry itself. make run restarts it after 20 s, and it registers again.</p>
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Event</th>
                <th>Instance</th>
              </tr>
            </thead>
            <tbody>
              {view?.events.slice(0, 10).map((e, idx) => (
                <tr key={idx}>
                  <td>{new Date(e.at * 1000).toLocaleTimeString()}</td>
                  <td>
                    <span className={`pill ${e.event === "registered" ? "done" : "failed"}`}>{e.event}</span>
                  </td>
                  <td>
                    <code>{e.instance_id}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
