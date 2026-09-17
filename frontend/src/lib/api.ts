/**
 * Fetch wrapper.
 *
 * The access token is kept in memory only; the refresh token lives in an httpOnly
 * cookie the browser sends on its own. A 401 triggers one refresh attempt, then the
 * original request is retried once.
 */

/** Every backend route lives under /api; the dev server proxies that prefix. */
export const API_BASE = "/api";

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }

  /** Field errors from a 422, as { "body.email": "value is not a valid email" }. */
  get fieldErrors(): Record<string, string> {
    if (!Array.isArray(this.details)) return {};
    const out: Record<string, string> = {};
    for (const item of this.details as { field?: string; message?: string }[]) {
      if (item.field && item.message) out[item.field.replace(/^body\./, "")] = item.message;
    }
    return out;
  }
}

let accessToken: string | null = null;
let onSignedOut: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function onUnauthenticated(handler: () => void) {
  onSignedOut = handler;
}

let refreshing: Promise<SessionResponse | null> | null = null;

export interface SessionResponse {
  access_token: string;
  expires_in: number;
  user: unknown;
}

/**
 * Single-flight refresh. Every caller shares one request: the backend rotates the
 * refresh token on use and treats a reused one as stolen, so two parallel refreshes
 * would end the session.
 */
export function refreshSession(): Promise<SessionResponse | null> {
  refreshing ??= (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) return null;
      const data = (await res.json()) as SessionResponse;
      accessToken = data.access_token;
      return data;
    } catch {
      return null;
    } finally {
      setTimeout(() => (refreshing = null), 0);
    }
  })();
  return refreshing;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | string[] | undefined | null>;
  retryOn401?: boolean;
}

export function buildQuery(params: RequestOptions["params"] = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, String(v)));
    else search.append(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, params, retryOn401 = true } = options;

  const res = await fetch(`${API_BASE}${path}${buildQuery(params)}`, {
    method,
    credentials: "include",
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && retryOn401) {
    if (await refreshSession()) {
      return api<T>(path, { ...options, retryOn401: false });
    }
    accessToken = null;
    onSignedOut?.();
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const error = (data?.error as ApiErrorBody) ?? {
      code: "error",
      message: res.statusText || "Something went wrong",
    };
    throw new ApiError(res.status, error);
  }
  return data as T;
}

export const get = <T>(path: string, params?: RequestOptions["params"]) => api<T>(path, { params });
export const post = <T>(path: string, body?: unknown) => api<T>(path, { method: "POST", body });
export const patch = <T>(path: string, body?: unknown) => api<T>(path, { method: "PATCH", body });
export const put = <T>(path: string, body?: unknown) => api<T>(path, { method: "PUT", body });
export const del = <T>(path: string) => api<T>(path, { method: "DELETE" });
