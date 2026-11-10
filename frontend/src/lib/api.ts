/** The API client (SPEC 10): JSON in and out, Bearer token, and one error type for everything that can go wrong. */
import { clearToken, getToken } from "./token";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api").replace(/\/+$/, "");
const SIGNED_OUT_CODES = new Set(["UNAUTHENTICATED", "BAD_TOKEN"]);

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: unknown = {}) {
    super(message);
    this.name = "ApiError";
  }
  /** True when nothing reached the server at all (offline, asleep and not answering, blocked). */
  get isNetwork(): boolean {
    return this.status === 0;
  }
}

type Options = { method?: string; body?: unknown; signal?: AbortSignal; auth?: boolean };

function fromBody(status: number, body: unknown, fallback: string): ApiError {
  const b = body as { error?: { code?: string; message?: string; details?: unknown }; detail?: unknown } | null;
  if (b?.error?.code) return new ApiError(status, b.error.code, b.error.message ?? fallback, b.error.details ?? {});
  if (Array.isArray(b?.detail)) {                                       // FastAPI's own validation errors
    const first = b.detail[0] as { loc?: unknown[]; msg?: string } | undefined;
    const where = first?.loc?.filter((p) => p !== "body").join(".");
    return new ApiError(status, "VALIDATION", first?.msg ? `${where ? where + ": " : ""}${first.msg}` : fallback, b.detail);
  }
  if (typeof b?.detail === "string") return new ApiError(status, `HTTP_${status}`, b.detail);
  return new ApiError(status, `HTTP_${status}`, fallback);
}

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = opts.auth === false ? null : getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: opts.method ?? "GET", headers, signal: opts.signal,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "NETWORK", "The server could not be reached. If it was asleep it needs about a minute to wake up.");
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!res.ok) {
    const err = fromBody(res.status, body, res.statusText || "Something went wrong");
    if (res.status === 401 && SIGNED_OUT_CODES.has(err.code)) clearToken();
    throw err;
  }
  return body as T;
}

export function apiGet<T = unknown>(path: string): Promise<T> {
  return api<T>(path, { method: "GET" });
}

export function apiPost<T = unknown>(path: string, body?: unknown): Promise<T> {
  return api<T>(path, { method: "POST", body });
}
