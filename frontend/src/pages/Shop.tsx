import { FormEvent, useEffect, useState } from "react";
import { Order, Product, shopApi } from "../api/gatewayClient";

interface Auth {
  username: string;
  token: string;
}

const AUTH_KEY = "shop_auth";

function loadAuth(): Auth | null {
  const raw = localStorage.getItem(AUTH_KEY);
  const auth = raw ? (JSON.parse(raw) as Partial<Auth>) : null;
  // Sign-ins saved before M2 hold an old API key, not a token: treat them as signed out.
  return auth?.token && auth.username ? (auth as Auth) : null;
}

function saveAuth(auth: Auth | null) {
  if (auth) localStorage.setItem(AUTH_KEY, JSON.stringify(auth));
  else localStorage.removeItem(AUTH_KEY);
}

export default function Shop() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [auth, setAuth] = useState<Auth | null>(() => loadAuth());
  const [authMode, setAuthMode] = useState<"login" | "register">("register");
  const [authError, setAuthError] = useState<string | null>(null);
  const [authBusy, setAuthBusy] = useState(false);

  const [cart, setCart] = useState<Order | null>(null);
  const [cartError, setCartError] = useState<string | null>(null);
  const [checkoutMessage, setCheckoutMessage] = useState<string | null>(null);

  const [seedStatus, setSeedStatus] = useState<string | null>(null);

  async function refreshProducts(attempt = 1) {
    if (attempt === 1) {
      setLoading(true);
      setError(null);
    }
    try {
      const data = await shopApi.listProducts();
      setProducts(data.results);
      setLoading(false);
    } catch (err) {
      // Azure Container Apps scale to zero when idle, and a cold start can reset the first
      // connection. Retry twice before showing an error.
      if (attempt < 3) {
        await new Promise((resolve) => setTimeout(resolve, 2000 * attempt));
        return refreshProducts(attempt + 1);
      }
      setError(String(err));
      setLoading(false);
    }
  }

  function refreshCart(currentAuth: Auth | null) {
    if (!currentAuth) {
      setCart(null);
      return;
    }
    shopApi
      .getCart(currentAuth.token)
      .then((data) => setCart(data.result ?? null))
      .catch(() => setCart(null));
  }

  useEffect(() => {
    refreshProducts();
    refreshCart(auth);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleAuthSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setAuthError(null);
    setAuthBusy(true);
    const form = new FormData(e.currentTarget);
    const username = String(form.get("username") || "");
    const password = String(form.get("password") || "");
    const email = String(form.get("email") || "");

    try {
      if (authMode === "register") {
        await shopApi.register(username, email, password);
      }
      const { token } = await shopApi.login(username, password);
      const newAuth = { username, token };
      setAuth(newAuth);
      saveAuth(newAuth);
      refreshCart(newAuth);
    } catch (err) {
      setAuthError(String(err));
    } finally {
      setAuthBusy(false);
    }
  }

  function logout() {
    setAuth(null);
    saveAuth(null);
    setCart(null);
  }

  async function addToCart(productId: number) {
    if (!auth) return;
    setCartError(null);
    try {
      const { result } = await shopApi.addToCart(auth.token, productId, 1);
      setCart(result);
    } catch (err) {
      setCartError(String(err));
    }
  }

  async function checkout() {
    if (!auth) return;
    setCartError(null);
    setCheckoutMessage(null);
    try {
      const { result } = await shopApi.checkout(auth.token);
      setCart(result);
      setCheckoutMessage("Order placed! Thank you.");
    } catch (err) {
      setCartError(String(err));
    }
  }

  async function seedSampleProducts() {
    setSeedStatus("Adding sample products…");
    const samples: [string, string, number][] = [
      ["Contoso Mug", "contoso-mug", 1299],
      ["Contoso T-Shirt", "contoso-tshirt", 2499],
      ["Contoso Notebook", "contoso-notebook", 899],
    ];
    try {
      for (const [name, slug, price] of samples) {
        await shopApi.createProduct(name, slug, price);
      }
      setSeedStatus(null);
      refreshProducts();
    } catch (err) {
      setSeedStatus(`Could not add sample products: ${err}`);
    }
  }

  const cartQtyByProduct = new Map((cart?.items ?? []).map((i) => [i.product_id, i.quantity]));
  const cartTotalCents = (cart?.items ?? []).reduce((sum, item) => {
    const product = products.find((p) => p.id === item.product_id);
    return sum + (product?.price ?? 0) * item.quantity;
  }, 0);

  return (
    <div className="grid" style={{ gap: "1.5rem" }}>
      <section className="card">
        <h1>Shop</h1>
        <p className="muted">
          Every request goes through the API gateway, which routes it to the service that owns it:
          accounts to <code>user</code>, products to <code>catalog</code>, cart and checkout to{" "}
          <code>order</code>.
        </p>
      </section>

      <section className="card">
        {auth ? (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>
              Signed in as <strong>{auth.username}</strong>
            </span>
            <button className="btn secondary" onClick={logout}>
              Log out
            </button>
          </div>
        ) : (
          <>
            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <button className={authMode === "register" ? "btn" : "btn secondary"} onClick={() => setAuthMode("register")}>
                Register
              </button>
              <button className={authMode === "login" ? "btn" : "btn secondary"} onClick={() => setAuthMode("login")}>
                Log in
              </button>
            </div>
            <form onSubmit={handleAuthSubmit} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <input name="username" placeholder="Username" required style={{ padding: "0.5rem" }} />
              {authMode === "register" && (
                <input name="email" type="email" placeholder="Email" required style={{ padding: "0.5rem" }} />
              )}
              <input name="password" type="password" placeholder="Password" required style={{ padding: "0.5rem" }} />
              <button className="btn" type="submit" disabled={authBusy}>
                {authMode === "register" ? "Create account & log in" : "Log in"}
              </button>
            </form>
            {authError && <p style={{ color: "var(--contoso-danger)" }}>{authError}</p>}
          </>
        )}
      </section>

      {loading && <p className="muted">Loading products…</p>}
      {error && (
        <div className="card" style={{ borderColor: "var(--contoso-danger)" }}>
          <strong>Could not reach the shop.</strong>
          <p className="muted">{error}</p>
          <p className="muted">Make sure `make run` is running the gateway and all services.</p>
        </div>
      )}

      {!loading && !error && (
        <section className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <h2 style={{ margin: 0 }}>Products</h2>
            {products.length === 0 && (
              <button className="btn secondary" onClick={seedSampleProducts}>
                Add sample products
              </button>
            )}
          </div>
          {seedStatus && <p className="muted">{seedStatus}</p>}
          <div className="grid cols-3">
            {products.length === 0 && !seedStatus && <p className="muted">No products yet.</p>}
            {products.map((p) => (
              <div key={p.id} className="card">
                <h3>{p.name}</h3>
                <p className="muted">${(p.price / 100).toFixed(2)}</p>
                {cartQtyByProduct.has(p.id) && (
                  <p className="pill done" style={{ marginBottom: "0.5rem" }}>
                    {cartQtyByProduct.get(p.id)} in cart
                  </p>
                )}
                <button className="btn" disabled={!auth} onClick={() => addToCart(p.id)}>
                  {auth ? "Add to cart" : "Log in to buy"}
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {auth && (
        <section className="card">
          <h2>Cart</h2>
          {cartError && <p style={{ color: "var(--contoso-danger)" }}>{cartError}</p>}
          {checkoutMessage && <p style={{ color: "var(--contoso-success)" }}>{checkoutMessage}</p>}
          {!cart || cart.items.length === 0 ? (
            <p className="muted">Your cart is empty.</p>
          ) : (
            <>
              <ul className="timeline">
                {cart.items.map((item) => {
                  const product = products.find((p) => p.id === item.product_id);
                  const lineTotalCents = (product?.price ?? 0) * item.quantity;
                  return (
                    <li key={item.product_id}>
                      <span>
                        {product?.name ?? `Product #${item.product_id}`}
                        <span className="muted"> × {item.quantity}</span>
                      </span>
                      <span>${(lineTotalCents / 100).toFixed(2)}</span>
                    </li>
                  );
                })}
              </ul>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1rem", fontSize: "1.1rem" }}>
                <strong>Total</strong>
                <strong>${(cartTotalCents / 100).toFixed(2)}</strong>
              </div>
              <button className="btn" style={{ marginTop: "1rem" }} disabled={!cart.is_open} onClick={checkout}>
                {cart.is_open ? `Checkout — $${(cartTotalCents / 100).toFixed(2)}` : "Order placed"}
              </button>
            </>
          )}
        </section>
      )}
    </div>
  );
}
