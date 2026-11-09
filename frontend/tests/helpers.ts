import { vi } from "vitest";

export type Reply = { status?: number; body?: unknown; text?: string; delayMs?: number } | Error | DOMException;

/** A scripted `fetch`: routes are "METHOD /path" -> a reply (or a function giving one). Records every call. */
export function mockFetch(routes: Record<string, Reply | ((init: RequestInit) => Reply)>) {
  const calls: { method: string; path: string; init: RequestInit }[] = [];
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    const path = url.replace("http://api.test/api", "");
    const method = init.method ?? "GET";
    calls.push({ method, path, init });
    const route = routes[`${method} ${path}`];
    if (route === undefined) throw new Error(`unexpected request ${method} ${path}`);
    const reply = typeof route === "function" ? route(init) : route;
    if (reply instanceof Error || reply instanceof DOMException) throw reply;
    if (reply.delayMs) await new Promise((r) => setTimeout(r, reply.delayMs));
    const status = reply.status ?? 200;
    const text = reply.text ?? (reply.body === undefined ? "" : JSON.stringify(reply.body));
    return new Response(status === 204 ? null : text, { status, statusText: status === 200 ? "OK" : "Error" });
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

export const lakshmi = { id: 1, email: "lakshmi@velugu.example.com", display_name: "Lakshmi" };

export const project = (over: Record<string, unknown> = {}) => ({
  id: 1, title: "Velugu Cove tourism website", summary: "One website for the cove.", location_label: "Velugu Cove", state: "PLEDGING",
  budget_cents: 40000, currency: "USD",
  campaign: { id: 1, number: 1, state: "OPEN", goal_cents: 40000, pledged_cents: 15000, pledge_count: 1, deadline_at: null }, ...over,
});

export const ledgerRow = (over: Record<string, unknown> = {}) => ({
  seq: 1, created_at: "2026-11-10T12:00:00", bucket: "NONE", type: "STATE_CHANGE", counterparty: null, amount_cents: 0, running_balance_cents: 0, status: null,
  paypal_ref: null, actor: "system", actor_name: "BriefPay", ref_type: "project", ref_id: "1", paypal_match: null, alert: false, meta: { from: "DRAFT", to: "REQUIREMENTS" }, ...over,
}) as import("@/lib/types").LedgerRow;

export const ledger = (rows: import("@/lib/types").LedgerRow[], over: Record<string, unknown> = {}) => ({
  project_id: 1, public: false, rows, totals: { pool_in_cents: 0, pool_out_cents: 0, pool_balance_cents: 0, rows: rows.length }, ...over,
});
