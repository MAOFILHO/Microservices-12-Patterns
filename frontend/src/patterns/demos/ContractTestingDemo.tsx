// The real contract files, written by the order service's tests and committed in contracts/pacts/.
import orderCatalog from "../../../../contracts/pacts/order-catalog.json";
import orderPayment from "../../../../contracts/pacts/order-payment.json";

interface Body {
  content?: unknown;
}

interface Interaction {
  description: string;
  providerStates?: { name: string }[];
  request: { method: string; path: string; body?: Body };
  response: { status: number; body?: Body };
}

interface PactFile {
  consumer: { name: string };
  provider: { name: string };
  interactions: Interaction[];
}

const CONTRACTS = [orderPayment, orderCatalog] as unknown as PactFile[];

const BREAK_OUTPUT = `$ make contracts      (payment renamed "amount_cents" to "amount")

Verifying a pact between order and payment
  a charge for an order
    returns a response which
      has status code 200 (OK)
      has a matching body (FAILED)

Failures:
  $.result -> Actual map is missing the following keys: amount_cents

There were 1 pact failures
FAILED services/payment/tests/test_contract_provider.py`;

export default function ContractTestingDemo() {
  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div>
        <h3>The contracts in this repo</h3>
        <p className="muted">
          The order service's tests record exactly what it sends and what it reads back. Payment and catalog then
          replay those requests against themselves in CI. These tables are read from the committed contract files.
        </p>
        {CONTRACTS.map((c) => (
          <div key={c.provider.name} style={{ marginBottom: "1rem" }}>
            <h4>
              <span className={`svc-dot svc-${c.consumer.name}`} />
              {c.consumer.name} needs from <span className={`svc-dot svc-${c.provider.name}`} />
              {c.provider.name}
            </h4>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Interaction</th>
                    <th>Request</th>
                    <th>Response the consumer relies on</th>
                  </tr>
                </thead>
                <tbody>
                  {c.interactions.map((i) => (
                    <tr key={i.description}>
                      <td>
                        {i.description}
                        {i.providerStates?.length ? (
                          <div className="muted" style={{ fontSize: "0.8rem" }}>
                            given: {i.providerStates.map((s) => s.name).join(", ")}
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <code>
                          {i.request.method} {i.request.path}
                        </code>
                        {i.request.body?.content !== undefined && (
                          <pre className="log-box" style={{ marginTop: "0.35rem" }}>
                            {JSON.stringify(i.request.body.content, null, 2)}
                          </pre>
                        )}
                      </td>
                      <td>
                        <code>{i.response.status}</code>
                        <pre className="log-box" style={{ marginTop: "0.35rem" }}>
                          {JSON.stringify(i.response.body?.content, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          Values are examples. The contract checks types (any integer id, any integer price) and exact values only
          where they matter, such as <code>"status": "APPROVED"</code>. Fields the consumer does not read, like{" "}
          <code>created_at</code>, are left out on purpose, so the provider can change them freely.
        </p>
      </div>

      <div className="grid cols-2">
        <div>
          <h3>When a provider breaks the contract</h3>
          <p className="muted">
            Real output from renaming one field in the payment service. The payment suite fails, so CI turns red on
            that pull request, before checkout ever breaks.
          </p>
          <pre className="log-box">{BREAK_OUTPUT}</pre>
        </div>
        <div>
          <h3>How CI runs it</h3>
          <ol>
            <li>
              The <strong>order</strong> suite runs its client code against a Pact mock and rewrites the contract
              files. CI fails if they differ from the committed ones.
            </li>
            <li>
              The <strong>payment</strong> and <strong>catalog</strong> suites start the real service and replay
              every interaction in its contract.
            </li>
            <li>No broker: the contracts live in the repo, next to the code, and change in the same pull request.</li>
          </ol>
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            Run it yourself: <code>make contracts</code>
          </p>
        </div>
      </div>
    </div>
  );
}
