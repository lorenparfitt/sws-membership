// The one place the browser talks to the API. Same origin in production,
// proxied by Vite in development; the session cookie rides along.

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `request failed (${status})`);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
    ...init,
  });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body?.detail ?? body);
  return body as T;
}

export interface Me {
  id: number;
  member_number: number;
  first_name: string;
  last_name: string;
  email: string;
  roles: string[];
  has_password: boolean;
}

export interface Price {
  id: number;
  label: string;
  amount_cents: number;
  currency: string;
  members_only: boolean;
  ends_at: string | null;
}

export interface Product {
  id: number;
  name: string;
  description: string;
  season_year: number;
  grants: string[];
  price: Price | null;
  purchasable: boolean;
  locked_because: string[];
}

export interface Checkout {
  processor: string;
  session_token: string;
  parameters: Record<string, string>;
}

export interface Order {
  id: number;
  status: string;
  payment_method: string;
  total_cents: number;
  currency: string;
  lines: { product_name: string; amount_cents: number }[];
  checkout: Checkout | null;
}

export interface Entitlement {
  id: number;
  kind: string;
  product_name: string;
  valid_from: string;
  valid_to: string;
  visits_remaining: number | null;
  active: boolean;
}

export const api = {
  me: () => request<Me>("/api/auth/me"),
  requestLink: (email: string) =>
    request<void>("/api/auth/request-link", { method: "POST", body: JSON.stringify({ email }) }),
  redeem: (token: string) =>
    request<Me>("/api/auth/redeem", { method: "POST", body: JSON.stringify({ token }) }),
  signOut: () => request<void>("/api/auth/sign-out", { method: "POST" }),
  signInWithPassword: (email: string, password: string) =>
    request<Me>("/api/auth/password", { method: "POST", body: JSON.stringify({ email, password }) }),
  setPassword: (password: string) =>
    request<void>("/api/auth/set-password", { method: "POST", body: JSON.stringify({ password }) }),
  catalog: () => request<Product[]>("/api/catalog"),
  placeOrder: (productIds: number[]) =>
    request<Order>("/api/orders", { method: "POST", body: JSON.stringify({ product_ids: productIds }) }),
  order: (id: number) => request<Order>(`/api/orders/${id}`),
  fakeApprove: (id: number) => request<{ status: string }>(`/api/payments/fake/approve/${id}`, { method: "POST" }),
  entitlements: () => request<Entitlement[]>("/api/entitlements"),
};

export function money(cents: number, currency = "CAD"): string {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency }).format(cents / 100);
}
