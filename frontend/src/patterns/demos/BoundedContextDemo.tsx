import { useEffect, useState } from "react";
import { BoundedContextView, Product, patternsApi, shopApi } from "../../api/gatewayClient";

const CONTEXTS = [
  { name: "Identity", service: "user", owns: ["User", "credentials", "API key"] },
  { name: "Catalog", service: "catalog", owns: ["Product: name, slug, price"] },
  { name: "Inventory", service: "inventory", owns: ["StockItem: on hand, reserved"] },
  { name: "Ordering", service: "order", owns: ["Order, OrderItem (product id + qty)"] },
  { name: "Payments", service: "payment", owns: ["Payment: order id, amount, status"] },
];

export default function BoundedContextDemo() {
  const [products, setProducts] = useState<Product[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [view, setView] = useState<BoundedContextView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    shopApi
      .listProducts()
      .then((data) => {
        setProducts(data.results);
        if (data.results.length) setSelected(data.results[0].id);
      })
      .catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (selected === null) return;
    patternsApi
      .boundedContext(selected)
      .then(({ body }) => setView(body))
      .catch((err) => setError(String(err)));
  }, [selected]);

  return (
    <div className="grid" style={{ gap: "1.25rem" }}>
      <div>
        <h3>Context map</h3>
        <p className="muted">Five business contexts, one service each. They share ids, never models.</p>
        <div className="context-map">
          {CONTEXTS.map((c) => (
            <div key={c.name} className="context-box">
              <h4>
                <span className={`svc-dot svc-${c.service}`} />
                {c.name}
              </h4>
              <p className="muted" style={{ margin: "0 0 0.35rem", fontSize: "0.8rem" }}>
                service: {c.service}
              </p>
              <ul>
                {c.owns.map((o) => (
                  <li key={o}>{o}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h3>One product, two contexts</h3>
        <p className="muted">
          Pick a product. The gateway asks Catalog and Inventory about the same product id. Each answers in its own
          words.
        </p>
        {error && <p style={{ color: "var(--contoso-danger)" }}>{error}</p>}
        <select
          value={selected ?? ""}
          onChange={(e) => setSelected(Number(e.target.value))}
          style={{ padding: "0.5rem", marginBottom: "0.75rem" }}
        >
          {products.map((p) => (
            <option key={p.id} value={p.id}>
              #{p.id} {p.name}
            </option>
          ))}
        </select>
        {view && (
          <div className="grid cols-2">
            <div className="context-box">
              <h4>
                <span className="svc-dot svc-catalog" />
                As Catalog sees it
              </h4>
              <pre className="log-box">{JSON.stringify(view.catalog, null, 2)}</pre>
              <p className="muted" style={{ fontSize: "0.85rem" }}>Knows the name and price. Has no idea how many exist.</p>
            </div>
            <div className="context-box">
              <h4>
                <span className="svc-dot svc-inventory" />
                As Inventory sees it
              </h4>
              <pre className="log-box">{view.inventory ? JSON.stringify(view.inventory, null, 2) : "No stock record for this product id."}</pre>
              <p className="muted" style={{ fontSize: "0.85rem" }}>Knows the counts. Has no idea what the product is called.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
