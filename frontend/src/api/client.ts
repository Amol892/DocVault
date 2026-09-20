// Thin, typed fetch wrapper. Deliberately dependency-free (no axios) — one place
// that attaches the auth token, the base URL, and turns non-2xx responses into
// thrown ApiClientError instances so every call site can just `await` and `catch`.
import { API_BASE_URL } from "@/config";
import type { ApiError } from "@/types";

export class ApiClientError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.name = "ApiClientError";
  }
}

const TOKEN_KEY = "docvault_token";

let authToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}
export function loadStoredAuthToken(): string | null {
  authToken = localStorage.getItem(TOKEN_KEY);
  return authToken;
}

/** Called once when an authenticated request comes back 401 (expired or revoked token). */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

/** A message that is safe to show to a user for any thrown value. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiClientError) return err.message;
  if (err instanceof TypeError)
    return "Can't reach the server. Check your connection and try again.";
  if (err instanceof Error && err.message) return err.message;
  return "Something went wrong. Try again.";
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | undefined>;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = new URL(API_BASE_URL + path, window.location.origin);
  if (opts.query) {
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }

  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

  const res = await fetch(url.toString(), {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  if (res.status === 204) return undefined as T;

  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json() : undefined;

  if (!res.ok) {
    // A 401 on a request that carried a token means the session is gone. (A wrong password on
    // /auth/login is also 401 but sends no token, so it is not treated as a session expiry.)
    if (res.status === 401 && authToken) {
      setAuthToken(null);
      onUnauthorized?.();
    }
    const err = data as ApiError | undefined;
    throw new ApiClientError(
      res.status,
      err?.error?.code ?? "UNKNOWN_ERROR",
      err?.error?.message ?? `Request failed with status ${res.status}`,
    );
  }
  return data as T;
}

export const apiClient = {
  get: <T>(path: string, query?: RequestOptions["query"]) =>
    request<T>(path, { method: "GET", query }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
