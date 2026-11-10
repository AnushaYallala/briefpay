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

export const run = (over: Record<string, unknown> = {}) => ({
  id: 1, created_at: "2026-11-10T12:00:00", agent: "BA_SCORE", provider: "gemini", model: "gemini-2.5-flash", prompt_version: "v1",
  input_hash: "abcdef1234567890abcdef", latency_ms: 420, input_tokens: 100, output_tokens: 50, status: "OK", output: { score: 80 }, error: null, ...over,
}) as import("@/lib/types").AgentRun;

export const planItem = (over: Record<string, unknown> = {}) => ({
  id: 1, project_id: 1, campaign_id: 1, kind: "FREELANCER_PAYOUT", state: "PROPOSED", reason: null, plan_hash: "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
  release_policy: "HUMAN", proposed_by: "user:1", created_at: "2026-11-10T12:00:00", decision: null, ...over,
}) as import("@/lib/types").PlanListItem;

export const rule = (over: Record<string, unknown> = {}) => ({ id: "G-01", title: "Plan binding", status: "PASS", detail: "rebuilding from the database gives exactly this plan hash", paypal_verified: false, ...over });

export const review = (over: Record<string, unknown> = {}) => ({
  id: 11, plan_hash: "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90", decision: "ALLOW", simulated: false,
  rules: [rule(), rule({ id: "G-06", title: "PayPal-side proof", paypal_verified: true, detail: "1 PayPal object(s) match our records" }), rule({ id: "G-12", title: "Work and recipient binding", detail: "VERIFIED report, locked recipient" })],
  soft_flags: [], llm: { status: "OK", risk_level: "low", explanation_for_sponsors: "Nothing unusual.", findings: [] }, agent_run_id: 5, created_at: "2026-11-10T12:05:00", ...over,
}) as import("@/lib/types").GuardianReview;

export const step = (over: Record<string, unknown> = {}) => ({
  seq: 1, phase: 1, op: "PAYOUT_ITEM", target_type: "CONTRACT", target_id: 1, amount_cents: 40000, bucket: "POOL", receiver_email: "arjun-sandbox@velugu.example.com",
  state: "PENDING", paypal_ref: null, error: null, ...over,
}) as import("@/lib/types").PlanStep;

export const planDetail = (over: Record<string, unknown> = {}) => ({
  ...planItem(), inputs: {}, steps: [step()], reviews: [], approvals: [], ...over,
}) as import("@/lib/types").PlanDetail;

export const baDim = (over: Record<string, unknown> = {}) => ({
  dimension: "D1", name: "Business goals & success measures", weight: 12, coverage_claimed: 0.5, coverage_effective: 0.5, downgraded: false,
  justification: "Goals are clear, no measure yet", source_refs: ["L3-L5"], ...over,
}) as import("@/lib/types").BaDimension;

export const baScore = (over: Record<string, unknown> = {}) => ({
  round: 0, total: 58, capped: false, total_uncapped: 58,
  dimensions: [baDim(), baDim({ dimension: "D5", name: "Functional requirements", weight: 15, coverage_effective: 0.75, coverage_claimed: 1, downgraded: true, justification: "Pages listed", source_refs: ["L7", "answer:12"] })],
  gates: [{ id: "GT-1", title: "Budget and delivery deadline are stated", passed: true, detail: "both stated" }, { id: "GT-3", title: "No unresolved conflict between sponsors", passed: false, detail: "1 open conflict" }],
  requirements: [{ temp_id: "R1", title: "Welcome page", description: "A home page.", priority: "MUST", requested_by: [1, 2], acceptance_criteria: ["Given a visitor, when they open /, then it loads"], source_refs: ["L3"] }],
  conflicts: [{ topic: "Booking online or enquiry only", positions: [{ member_id: 1, position: "wants booking" }, { member_id: 2, position: "no payments" }], resolved: false, resolution: null }],
  out_of_scope: ["Online payments"], injection_attempts: [], created_at: "2026-11-10T12:00:00", ...over,
}) as import("@/lib/types").BaScore;

export const baQuestion = (over: Record<string, unknown> = {}) => ({
  id: 1, round: 0, dimension: "D5", dimension_name: "Functional requirements", question: "Should visitors book online?", rationale: "The sponsors disagree.",
  addressed_to: [1, 2], suggested_options: ["Enquiry form only", "Online booking"], status: "OPEN", answers: [], can_answer: true, ...over,
}) as import("@/lib/types").BaQuestion;

export const baView = (over: Record<string, unknown> = {}) => ({
  session: { id: 1, state: "ACTIVE", round: 0, current_score: 58, target_score: 90, max_rounds: 5 }, score: baScore(),
  history: [{ round: 0, total: 58, capped: false, created_at: "2026-11-10T12:00:00" }], questions: [baQuestion()], can_run: false, can_finalize: false, ...over,
}) as import("@/lib/types").BaView;

export const transcript = (n = 10) => ({
  id: 1, source_name: "meeting.txt", line_count: n, sha256: "x", uploaded_at: "2026-11-10T11:00:00",
  lines: Array.from({ length: n }, (_, i) => ({ n: i + 1, text: `Speaker ${(i % 3) + 1}: line ${i + 1}` })),
});

export const ledger = (rows: import("@/lib/types").LedgerRow[], over: Record<string, unknown> = {}) => ({
  project_id: 1, public: false, rows, totals: { pool_in_cents: 0, pool_out_cents: 0, pool_balance_cents: 0, rows: rows.length }, ...over,
});
