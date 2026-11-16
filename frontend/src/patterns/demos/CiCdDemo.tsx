import { useEffect, useState } from "react";
import { DeliveryStatus, DeliveryView, WorkflowRun, deliveryApi } from "../../api/gatewayClient";

const PILL: Record<DeliveryStatus, string> = {
  current: "done",
  unchanged: "done",
  behind: "failed",
  local: "pending",
  unknown: "pending",
};
const LABEL: Record<DeliveryStatus, string> = {
  current: "on latest main",
  unchanged: "no changes since its build",
  behind: "behind main: Deploy rebuilds it",
  local: "local build",
  unknown: "unknown",
};

function Run({ title, run }: { title: string; run: WorkflowRun | null }) {
  return (
    <div className="context-box">
      <h4>{title}</h4>
      {run ? (
        <p style={{ margin: 0 }}>
          <span className={`pill ${run.conclusion === "success" ? "done" : run.conclusion ? "failed" : "running"}`}>
            {run.conclusion ?? run.status}
          </span>{" "}
          commit <code>{run.commit}</code> · {new Date(run.created_at).toLocaleString()} ·{" "}
          <a href={run.url} target="_blank" rel="noreferrer">
            open the run
          </a>
        </p>
      ) : (
        <p className="muted" style={{ margin: 0 }}>
          No run on main yet, or GitHub is unreachable.
        </p>
      )}
    </div>
  );
}

export default function CiCdDemo() {
  const [view, setView] = useState<DeliveryView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    deliveryApi
      .view()
      .then((v) => active && setView(v))
      .catch((err) => active && setError(String(err)));
    return () => {
      active = false;
    };
  }, []);

  if (!view && !error) return <p className="muted">Reading the running services and GitHub…</p>;

  const behind = view?.services.filter((s) => s.status === "behind").length ?? 0;

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      {error && <p style={{ color: "var(--contoso-danger)" }}>{error}</p>}
      <div>
        <h3>What each running service was built from</h3>
        <p className="muted">
          Latest commit on main:{" "}
          {view?.main ? (
            <a href={view.main.url} target="_blank" rel="noreferrer">
              <code>{view.main.short}</code>
            </a>
          ) : (
            "unknown (GitHub unreachable)"
          )}
          . {behind > 0 ? `${behind} service(s) are behind main: the Deploy button rebuilds exactly those.` : ""}
        </p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Service</th>
                <th>Built from</th>
                <th>Compared with main</th>
              </tr>
            </thead>
            <tbody>
              {view?.services.map((s) => (
                <tr key={s.instance}>
                  <td>
                    <span className={`svc-dot svc-${s.service}`} />
                    {s.instance}
                  </td>
                  <td>
                    <code>{s.git_sha ?? "–"}</code>
                  </td>
                  <td>
                    <span className={`pill ${PILL[s.status]}`}>{LABEL[s.status]}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          Locally every process says "local build": make run starts the code from your working copy. In Azure, each
          image carries the commit it was built from.
        </p>
      </div>

      <div className="grid cols-2">
        <Run title="Latest CI run on main" run={view?.runs.ci ?? null} />
        <Run title="Latest Deploy run" run={view?.runs.deploy ?? null} />
      </div>

      <div>
        <h3>The pipeline</h3>
        <ol>
          <li>
            <strong>Pull request:</strong> a planning job reads the changed files and the service table, then runs only
            the unit tests, contract checks and container builds that change touches. Shared code runs everything.
          </li>
          <li>
            <strong>Merge to main:</strong> everything runs once more. One job, "CI ok", sums it all up.
          </li>
          <li>
            <strong>Deploy (a person presses the button):</strong> signs in to Azure with OIDC (no stored password),
            rebuilds only the services whose code changed since the commit they run, rolls them out, and waits until
            each one answers with the new commit.
          </li>
        </ol>
      </div>
    </div>
  );
}
