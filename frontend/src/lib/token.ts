/**
 * Where the login token lives (D-009: a Bearer token, no cookies). Browser storage can be missing or throw (private windows,
 * blocked site data, server-side rendering), so every access is guarded and falls back to memory: the app must still work.
 */
const KEY = "briefpay.token";
let memory: string | null = null;
const listeners = new Set<() => void>();

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  try {
    return storage()?.getItem(KEY) ?? memory;
  } catch {
    return memory;
  }
}

export function setToken(token: string): void {
  memory = token;
  try {
    storage()?.setItem(KEY, token);
  } catch {
    /* kept in memory only */
  }
}

export function clearToken(): void {
  memory = null;
  try {
    storage()?.removeItem(KEY);
  } catch {
    /* nothing to remove */
  }
  listeners.forEach((fn) => fn());
}

/** Called when the server says the token is no longer good, so the app can show the signed-out state. */
export function onTokenCleared(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
