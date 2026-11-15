// Every call goes through the API gateway (pattern 5), never straight to a service.
const GATEWAY_BASE_URL = import.meta.env.VITE_GATEWAY_BASE_URL || "http://127.0.0.1:8100";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${GATEWAY_BASE_URL}${path}`, options);
  if (!response.ok) {
    const body = await response.text();
    let message = body;
    try {
      message = (JSON.parse(body) as { message?: string }).message ?? body;
    } catch {
      // not JSON: keep the raw text
    }
    throw new Error(`${response.status}: ${message}`);
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

// Pattern 10: the signed login token travels with every request; no server keeps a session.
function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
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
    request<{ token: string; expires_in: number }>(`/api/shop/user/login`, {
      method: "POST",
      body: toForm({ username, password }),
    }),

  addToCart: (token: string, productId: number, qty: number) =>
    request<{ result: Order }>(`/api/shop/order/add-item`, {
      method: "POST",
      headers: authHeaders(token),
      body: toForm({ product_id: productId, qty }),
    }),

  getCart: (token: string) =>
    request<{ result?: Order; message?: string }>(`/api/shop/order`, {
      headers: authHeaders(token),
    }),

  checkout: (token: string) =>
    request<{ result: Order }>(`/api/shop/order/checkout`, {
      method: "POST",
      headers: authHeaders(token),
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
  orderSummary: (token: string) => requestWithIds<OrderSummary>("/api/order-summary", { headers: authHeaders(token) }),
  trace: (traceId: string) => request<{ trace_id: string; spans: Span[] }>(`/api/observability/trace/${traceId}`),
  metrics: () => request<{ services: ServiceMetrics[] }>("/api/observability/metrics"),
};

/** The Shop page stores the signed-in user here; demos that need a login reuse it. */
export function savedToken(): string | null {
  try {
    const raw = localStorage.getItem("shop_auth");
    return raw ? ((JSON.parse(raw) as { token?: string }).token ?? null) : null;
  } catch {
    return null;
  }
}

// --- M2 demo endpoints (patterns 4, 10, 12) ------------------------------------------------------

export interface RegistryInstance {
  instance_id: string;
  url: string;
  last_heartbeat_s: number | null;
  up_for_s: number | null;
}

export interface RegistryView {
  mode: "registry" | "static" | "registry-unreachable";
  ttl_seconds: number | null;
  services: Record<string, RegistryInstance[]>;
  events: { at: number; event: string; service: string; instance_id: string }[];
}

export interface BreakerState {
  instance: string | null;
  state: "closed" | "open" | "half-open" | "unreachable";
  failures_in_a_row?: number;
  fail_max?: number;
  reset_seconds?: number;
  retry_in_seconds?: number | null;
}

export interface BreakerCall {
  outcome: "ok" | "failed" | "short-circuited" | string;
  ms?: number;
  total_ms?: number;
  instance: string | null;
  breaker?: BreakerState;
}

/** GET with the token, returning the status and which replica answered (X-Instance-Id). */
async function getWithInstance<T>(path: string, token: string): Promise<{ status: number; instance: string | null; body: T }> {
  const response = await fetch(`${GATEWAY_BASE_URL}${path}`, { headers: authHeaders(token) });
  return { status: response.status, instance: response.headers.get("X-Instance-Id"), body: (await response.json()) as T };
}

async function getAny<T>(path: string, options: RequestInit = {}): Promise<{ status: number; body: T }> {
  const response = await fetch(`${GATEWAY_BASE_URL}${path}`, options);
  return { status: response.status, body: (await response.json()) as T };
}

export const resilienceApi = {
  registry: () => request<RegistryView>("/api/patterns/registry"),
  stopReplica: (instanceId: string) =>
    getAny<{ stopping?: string; message?: string }>(`/api/patterns/replicas/${encodeURIComponent(instanceId)}/stop`, { method: "POST" }),
  cartFromAnyReplica: (token: string) => getWithInstance<{ result?: Order; message?: string }>("/api/shop/order", token),
  breakerCall: () => getAny<BreakerCall>("/api/patterns/breaker/call"),
  breakerState: () =>
    request<{ breakers: BreakerState[]; payment: { mode: string; enabled?: boolean }; chaos_enabled: boolean }>("/api/patterns/breaker/state"),
  setPaymentMode: (mode: string) =>
    getAny<{ mode?: string; message?: string }>("/api/patterns/breaker/payment-mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    }),
};

// --- M3a demo endpoints (patterns 8, 7, 9) -------------------------------------------------------

export interface SagaStep {
  step: string;
  status: "done" | "failed" | "compensated" | string;
  detail: string | null;
  at: string | null;
}

export interface SagaRun {
  saga_id: string;
  order_id: number;
  outcome: "completed" | "compensated" | "failed";
  steps: SagaStep[];
}

export interface OutboxRow {
  event_id: string;
  type: string;
  payload: Record<string, unknown>;
  created_at: string | null;
  published_at: string | null;
  attempts: number;
  last_error: string | null;
}

export interface StockRow {
  product_id: number;
  on_hand: number;
  reserved: number;
  available: number;
}

export interface EventsView {
  outbox: { pending: number; results: OutboxRow[]; bus_connected: boolean } | null;
  consumed: { event_id: string; type: string; reservation_id: string | null; outcome: string; handled_at: string | null }[] | null;
  stock: StockRow[] | null;
  reservations: { reservation_id: string; order_id: number; status: string; items: { product_id: number; quantity: number }[] }[] | null;
  bus_connected: boolean[] | null;
  chaos_enabled: boolean;
}

export interface RuntimeInfo {
  service: string;
  instance: string;
  uid?: number | null;
  root?: boolean;
  in_container?: boolean;
  os?: string;
  arch?: string;
  python?: string;
  git_sha?: string;
  image_size_mb?: number | null;
  unreachable?: boolean;
}

export const asyncApi = {
  checkout: (token: string, simulateDecline: boolean) =>
    getAny<{ message?: string; saga_id?: string; failed_step?: string }>("/api/shop/order/checkout", {
      method: "POST",
      headers: { ...authHeaders(token), "Content-Type": "application/json" },
      body: JSON.stringify({ simulate_decline: simulateDecline }),
    }),
  sagas: (token: string) => request<{ results: SagaRun[] }>("/api/shop/order/sagas", { headers: authHeaders(token) }),
  addToCart: (token: string, productId: number, qty: number) => shopApi.addToCart(token, productId, qty),
  events: () => request<EventsView>("/api/patterns/events"),
  setBus: (connected: boolean) =>
    getAny<{ bus_connected?: boolean; message?: string }>("/api/patterns/events/bus", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ connected }),
    }),
  runtime: () => request<{ processes: RuntimeInfo[] }>("/api/patterns/runtime"),
};

// --- M3b demo endpoint (pattern 3) ---------------------------------------------------------------

export interface WorkflowRun {
  workflow: string;
  status: string;
  conclusion: string | null;
  commit: string;
  url: string;
  created_at: string;
}

export interface DeliveryView {
  repo: string;
  main: { sha: string; short: string; url: string } | null;
  services: { service: string; instance: string; git_sha: string | null; status: "current" | "behind" | "local" | "unknown" }[];
  runs: { ci: WorkflowRun | null; deploy: WorkflowRun | null };
}

export const deliveryApi = {
  view: () => request<DeliveryView>("/api/patterns/delivery"),
};
