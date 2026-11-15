// Every call goes through the API gateway (pattern 5), never straight to a service.
const GATEWAY_BASE_URL = import.meta.env.VITE_GATEWAY_BASE_URL || "http://127.0.0.1:8100";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${GATEWAY_BASE_URL}${path}`, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
  return response.json() as Promise<T>;
}

/** Same as request(), but also returns the gateway's request and trace IDs for this call. */
async function requestWithIds<T>(path: string, options: RequestInit = {}): Promise<{ body: T; requestId: string | null; traceId: string | null }> {
  const response = await fetch(`${GATEWAY_BASE_URL}${path}`, options);
  const body = (await response.json()) as T;
  if (!response.ok) {
    throw Object.assign(new Error(`${response.status} ${response.statusText}`), { body });
  }
  return { body, requestId: response.headers.get("X-Request-Id"), traceId: response.headers.get("X-Trace-Id") };
}

function toForm(fields: Record<string, string | number>): URLSearchParams {
  const form = new URLSearchParams();
  for (const [key, value] of Object.entries(fields)) form.append(key, String(value));
  return form;
}

function authHeaders(apiKey: string): HeadersInit {
  return { Authorization: `Basic ${apiKey}` };
}

export interface Product {
  id: number;
  name: string;
  slug: string;
  price: number;
  image: string | null;
}

export interface OrderItem {
  product_id: number;
  quantity: number;
}

export interface Order {
  id?: number;
  user_id?: number;
  is_open: boolean;
  items: OrderItem[];
}

export const shopApi = {
  listProducts: () => request<{ results: Product[] }>(`/api/shop/products`),

  createProduct: (name: string, slug: string, priceCents: number) =>
    request<{ product: Product }>(`/api/shop/product/create`, {
      method: "POST",
      body: toForm({ name, slug, price: priceCents }),
    }),

  register: (username: string, email: string, password: string) =>
    request<{ result: { username: string } }>(`/api/shop/user/create`, {
      method: "POST",
      body: toForm({ username, email, password }),
    }),

  login: (username: string, password: string) =>
    request<{ api_key: string }>(`/api/shop/user/login`, {
      method: "POST",
      body: toForm({ username, password }),
    }),

  addToCart: (apiKey: string, productId: number, qty: number) =>
    request<{ result: Order }>(`/api/shop/order/add-item`, {
      method: "POST",
      headers: authHeaders(apiKey),
      body: toForm({ product_id: productId, qty }),
    }),

  getCart: (apiKey: string) =>
    request<{ result?: Order; message?: string }>(`/api/shop/order`, {
      headers: authHeaders(apiKey),
    }),

  checkout: (apiKey: string) =>
    request<{ result: Order }>(`/api/shop/order/checkout`, {
      method: "POST",
      headers: authHeaders(apiKey),
    }),
};

// --- Pattern demo endpoints --------------------------------------------------------------------

export interface ServiceCall {
  service: string;
  path: string;
  status: number | string;
  ms: number;
}

export interface ServiceDatabase {
  service: string;
  reachable: boolean;
  engine?: string;
  database?: string;
  tables?: string[];
}

export interface IsolationResult {
  attempted: string;
  owner: string;
  order_tables: string[];
  blocked: boolean;
  error: string | null;
}

export interface BoundedContextView {
  product_id: number;
  catalog: Product | null;
  inventory: { product_id: number; on_hand: number; reserved: number; available: number } | null;
  calls: ServiceCall[];
}

export interface OrderSummary {
  user: { username: string };
  lines: { product_id: number; name: string | null; unit_price_cents: number | null; quantity: number; available: number | null }[];
  total_cents: number;
  calls: ServiceCall[];
  request_id: string;
  trace_id: string | null;
}

export interface Span {
  trace_id: string;
  span_id: string;
  parent_id: string | null;
  name: string;
  service: string;
  kind: string;
  start_ns: number;
  end_ns: number;
  status: string;
}

export interface ServiceMetrics {
  service: string;
  reachable: boolean;
  requests?: number;
  errors_5xx?: number;
  avg_ms?: number | null;
}

export const patternsApi = {
  databases: () => request<{ services: ServiceDatabase[] }>("/api/patterns/databases"),
  isolationTest: (table: string) => request<IsolationResult>(`/api/patterns/isolation-test?table=${encodeURIComponent(table)}`),
  boundedContext: (productId: number) => requestWithIds<BoundedContextView>(`/api/patterns/bounded-context/${productId}`),
  orderSummary: (apiKey: string) => requestWithIds<OrderSummary>("/api/order-summary", { headers: authHeaders(apiKey) }),
  trace: (traceId: string) => request<{ trace_id: string; spans: Span[] }>(`/api/observability/trace/${traceId}`),
  metrics: () => request<{ services: ServiceMetrics[] }>("/api/observability/metrics"),
};

/** The Shop page stores the signed-in user here; demos that need a login reuse it. */
export function savedApiKey(): string | null {
  try {
    const raw = localStorage.getItem("shop_auth");
    return raw ? (JSON.parse(raw) as { apiKey: string }).apiKey : null;
  } catch {
    return null;
  }
}
