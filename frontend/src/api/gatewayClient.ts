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
