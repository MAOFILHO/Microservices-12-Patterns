import { useEffect, useState } from "react";
import { RuntimeInfo, asyncApi } from "../../api/gatewayClient";

const DOCKERFILE = `FROM python:3.12-slim AS build          # stage 1: install dependencies
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY _shared ./_shared
RUN pip install --no-cache-dir "./_shared[flask]"

FROM python:3.12-slim                    # stage 2: only what runs
ARG GIT_SHA=unknown
ENV RUN_MODE=azure GIT_SHA=$GIT_SHA ...
RUN useradd --uid 10001 --no-create-home app
COPY --from=build /opt/venv /opt/venv    # no pip cache, no build files
COPY --chown=10001:10001 . .
USER 10001                               # never root
CMD ["gunicorn", "--workers", "1", "--threads", "4", ...]`;

export default function ContainerizationDemo() {
  const [processes, setProcesses] = useState<RuntimeInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    asyncApi
      .runtime()
      .then((r) => setProcesses(r.processes))
      .catch((err) => setError(String(err)));
  }, []);

  const anyContainer = processes.some((p) => p.in_container);

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div>
        <h3>How each process is running right now</h3>
        <p className="muted">
          {anyContainer
            ? "These processes run in containers built from the Dockerfiles below."
            : "Locally, make run starts plain processes, no containers (this project never uses Docker on the Mac). In Azure and in CI the same code runs in the images below, as uid 10001."}
        </p>
        {error && <p style={{ color: "var(--contoso-danger)" }}>{error}</p>}
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Process</th>
                <th>Container</th>
                <th>Runs as</th>
                <th>Platform</th>
                <th>Python</th>
                <th>Build</th>
                <th>Image</th>
              </tr>
            </thead>
            <tbody>
              {processes.map((p) => (
                <tr key={p.instance}>
                  <td>
                    <span className={`svc-dot svc-${p.service}`} />
                    {p.instance}
                  </td>
                  {p.unreachable ? (
                    <td colSpan={6} style={{ color: "var(--contoso-danger)" }}>
                      unreachable
                    </td>
                  ) : (
                    <>
                      <td>{p.in_container ? "yes" : "no"}</td>
                      <td>
                        <span className={`pill ${p.root ? "failed" : "done"}`}>{p.root ? "root" : `uid ${p.uid}`}</span>
                      </td>
                      <td>
                        {p.os?.toLowerCase()}/{p.arch}
                      </td>
                      <td>{p.python}</td>
                      <td>
                        <code>{p.git_sha === "local" ? "local" : p.git_sha?.slice(0, 7)}</code>
                      </td>
                      <td>{p.image_size_mb ? `${p.image_size_mb} MB` : "–"}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid cols-2">
        <div>
          <h3>Every service's Dockerfile, in short</h3>
          <pre className="log-box">{DOCKERFILE}</pre>
        </div>
        <div>
          <h3>What CI checks on every pull request</h3>
          <ol>
            <li>
              Builds all 7 images (5 services, gateway, registry) for <code>linux/amd64</code>, the platform Azure
              Container Apps runs. The owner's Mac is arm64, so images are never built on it.
            </li>
            <li>Starts each image and waits for <code>/health</code> to answer.</li>
            <li>Fails if the process inside runs as root (uid 0).</li>
            <li>Writes each image's size to the run summary.</li>
            <li>
              The manual Deploy workflow records each image's compressed size in the app, shown in the Image column in
              Azure.
            </li>
          </ol>
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            A <code>.dockerignore</code> in each service keeps local virtualenvs, databases and keys out of the build.
            The image is labelled with the git commit it was built from, shown in the Build column in Azure.
          </p>
        </div>
      </div>
    </div>
  );
}
