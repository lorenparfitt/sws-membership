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

export interface Waiver {
  template_id: number | null;
  version: number | null;
  title: string | null;
  body_text: string | null;
  document_hash: string | null;
  signed: boolean;
  signed_at: string | null;
  needs_guardian: boolean;
}

export interface WaiverSignature {
  template_id: number;
  signer_name: string;
  signature_png: string;
  guardian_name?: string;
  guardian_signature_png?: string;
}

export interface GateMember {
  id: number;
  member_number: number;
  first_name: string;
  last_name: string;
  email: string;
  date_of_birth: string | null;
  photo_key: string | null;
  waiver_current: boolean;
  passes: Entitlement[];
  today: { station: string; checked_in_at: string; product_name: string }[];
}

export interface CheckInResult {
  admitted: boolean;
  new_today: boolean;
  message: string;
  member: GateMember;
}

export interface Profile {
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  date_of_birth: string | null;
  address_line_1: string | null;
  address_line_2: string | null;
  city: string | null;
  province: string | null;
  postal_code: string | null;
  sports: string[];
  has_photo: boolean;
  missing: string[];
}

export interface ProfileBody {
  first_name: string;
  last_name: string;
  phone: string;
  date_of_birth: string | null;
  address_line_1: string;
  address_line_2: string;
  city: string;
  province: string;
  postal_code: string;
  sports: string[];
}

async function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("photo", file);
  const response = await fetch(path, { method: "POST", credentials: "same-origin", body: form });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body?.detail ?? body);
  return body as T;
}

export interface StaffOrder {
  id: number;
  status: string;
  payment_method: string;
  total_cents: number;
  created_at: string;
  paid_at: string | null;
  lines: { product_name: string; amount_cents: number }[];
}

export interface MemberDetail {
  id: number;
  member_number: number;
  roles: string[];
  has_photo: boolean;
  profile: Profile;
  waiver_current: boolean;
  waiver_signed_at: string | null;
  passes: Entitlement[];
  today: { station: string; checked_in_at: string; product_name: string }[];
  orders: StaffOrder[];
  catalog: Product[];
}

export interface StaffProfileBody extends ProfileBody {
  email: string;
}

export interface AdminPrice {
  id: number;
  label: string;
  amount_cents: number;
  starts_at: string;
  ends_at: string | null;
  members_only: boolean;
}
export interface AdminGrant {
  id: number;
  kind: string;
  valid_from: string;
  valid_to: string;
  visit_count: number | null;
}
export interface AdminRule {
  id: number;
  kind: string;
  parameters: Record<string, unknown>;
  failure_message: string;
}
export interface AdminProduct {
  id: number;
  name: string;
  description: string;
  season_year: number;
  sort_order: number;
  active: boolean;
  prices: AdminPrice[];
  grants: AdminGrant[];
  rules: AdminRule[];
}
export interface CatalogOptions {
  entitlement_kinds: string[];
  rule_kinds: { kind: string; parameters: Record<string, string> }[];
}
export interface ReportInfo {
  name: string;
  title: string;
  description: string;
  parameters: { name: string; label: string; kind: string; default: unknown }[];
}
export interface ReportOutput {
  title: string;
  columns: string[];
  rows: unknown[][];
}
export interface WaiverHistory {
  templates: { id: number; version: number; title: string; body_text: string; published_at: string }[];
  resets: { reset_at: string; reason: string }[];
}

const json = (body: unknown) => ({ method: "POST", body: JSON.stringify(body) });

export const admin = {
  options: () => request<CatalogOptions>("/api/admin/catalog/options"),
  products: () => request<AdminProduct[]>("/api/admin/catalog/products"),
  createProduct: (body: Partial<AdminProduct>) => request<AdminProduct>("/api/admin/catalog/products", json(body)),
  updateProduct: (id: number, body: Partial<AdminProduct>) =>
    request<AdminProduct>(`/api/admin/catalog/products/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  addPrice: (id: number, body: Omit<AdminPrice, "id">) => request<AdminProduct>(`/api/admin/catalog/products/${id}/prices`, json(body)),
  removePrice: (id: number, priceId: number) =>
    request<AdminProduct>(`/api/admin/catalog/products/${id}/prices/${priceId}`, { method: "DELETE" }),
  addGrant: (id: number, body: Omit<AdminGrant, "id">) => request<AdminProduct>(`/api/admin/catalog/products/${id}/grants`, json(body)),
  removeGrant: (id: number, grantId: number) =>
    request<AdminProduct>(`/api/admin/catalog/products/${id}/grants/${grantId}`, { method: "DELETE" }),
  addRule: (id: number, body: Omit<AdminRule, "id">) => request<AdminProduct>(`/api/admin/catalog/products/${id}/rules`, json(body)),
  removeRule: (id: number, ruleId: number) =>
    request<AdminProduct>(`/api/admin/catalog/products/${id}/rules/${ruleId}`, { method: "DELETE" }),
  rollover: (from_year: number, to_year: number) => request<AdminProduct[]>("/api/admin/catalog/rollover", json({ from_year, to_year })),
  reports: () => request<ReportInfo[]>("/api/admin/reports"),
  runReport: (name: string, parameters: Record<string, unknown>) =>
    request<ReportOutput>(`/api/admin/reports/${name}/run`, json({ parameters })),
  reportCsv: async (name: string, parameters: Record<string, unknown>): Promise<Blob> => {
    const response = await fetch(`/api/admin/reports/${name}/csv`, {
      ...json({ parameters }),
      credentials: "same-origin",
      headers: { "content-type": "application/json" },
    });
    if (!response.ok) throw new ApiError(response.status, await response.text());
    return response.blob();
  },
  waiverHistory: () => request<WaiverHistory>("/api/admin/waiver/history"),
  publishWaiver: (title: string, body_text: string) => request<{ version: number }>("/api/admin/waiver/publish", json({ title, body_text })),
  resetWaivers: (reason: string) => request<{ reset_at: string }>("/api/admin/waiver/reset", json({ reason })),
};

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
  waiver: () => request<Waiver>("/api/waiver"),
  sports: () => request<{ value: string; label: string }[]>("/api/sports"),
  profile: () => request<Profile>("/api/me/profile"),
  updateProfile: (body: ProfileBody) =>
    request<Profile>("/api/me/profile", { method: "PUT", body: JSON.stringify(body) }),
  uploadMyPhoto: (file: File) => upload<Profile>("/api/me/photo", file),
  uploadMemberPhoto: (memberId: number, file: File) =>
    upload<Profile>(`/api/staff/members/${memberId}/photo`, file),
  kioskLookup: (q: string) => request<GateMember[]>(`/api/staff/kiosk/lookup?q=${encodeURIComponent(q)}`),
  kioskCheckIn: (memberId: number, station: "spit" | "shuttle") =>
    request<CheckInResult>("/api/staff/kiosk/check-in", {
      method: "POST",
      body: JSON.stringify({ member_id: memberId, station }),
    }),
  kioskToday: () => request<Record<string, number>>("/api/staff/kiosk/today"),
  memberDetail: (id: number) => request<MemberDetail>(`/api/staff/members/${id}`),
  staffUpdateProfile: (id: number, body: StaffProfileBody) =>
    request<MemberDetail>(`/api/staff/members/${id}/profile`, { method: "PUT", body: JSON.stringify(body) }),
  setRoles: (id: number, roles: string[]) =>
    request<MemberDetail>(`/api/staff/members/${id}/roles`, { method: "PUT", body: JSON.stringify({ roles }) }),
  staffOrderStatus: (id: number) => request<Order>(`/api/staff/orders/${id}`),
  staffOrder: (memberId: number, productIds: number[], paymentMethod: "cash" | "free" | "card") =>
    request<Order>("/api/staff/orders", {
      method: "POST",
      body: JSON.stringify({ member_id: memberId, product_ids: productIds, payment_method: paymentMethod }),
    }),
  printCards: async (memberIds: number[]): Promise<Blob> => {
    const response = await fetch("/api/staff/cards/print", {
      method: "POST",
      credentials: "same-origin",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ member_ids: memberIds }),
    });
    if (!response.ok) throw new ApiError(response.status, await response.text());
    return response.blob();
  },
  signWaiver: (body: WaiverSignature) =>
    request<Waiver>("/api/waiver/sign", { method: "POST", body: JSON.stringify(body) }),
};

export function money(cents: number, currency = "CAD"): string {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency }).format(cents / 100);
}
