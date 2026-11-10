/** Money plan logic (SPEC 11, screen 11), kept apart from the screens so it can be tested on its own. */
import type { Tone } from "./states";
import type { GuardianReview, Membership, PlanDetail } from "./types";

/** How often an approved or running plan asks for news while the page is open. */
export const PLAN_REFRESH_MS = 5000;

export const PLAN_WORDS: Record<string, string> = {
  CAPTURE_PLEDGES: "Collect the pledges", RELEASE_HOLDS: "Release the holds", FREELANCER_PAYOUT: "Pay the builder", REFUND_CAPTURED: "Refund the pledgers",
};

export const PLAN_STATES: Record<string, { label: string; tone: Tone }> = {
  PROPOSED: { label: "Waiting for the Guardian", tone: "grey" },
  REVIEWED: { label: "Checked: waiting for a person", tone: "blue" },
  APPROVED: { label: "Approved: about to run", tone: "teal" },
  EXECUTING: { label: "Running", tone: "amber" },
  DONE: { label: "Done", tone: "green" },
  PARTIAL: { label: "Partly done", tone: "red" },
  FAILED: { label: "Failed", tone: "red" },
  BLOCKED: { label: "Blocked by the Guardian", tone: "red" },
};

export const DECISIONS: Record<string, { label: string; tone: Tone; hint: string }> = {
  ALLOW: { label: "ALLOW", tone: "green", hint: "Every safety rule passed." },
  HOLD: { label: "HOLD", tone: "amber", hint: "Nothing is broken, but a person must look before money moves." },
  BLOCK: { label: "BLOCK", tone: "red", hint: "A safety rule failed. This plan can never run." },
};

export const OP_WORDS: Record<string, string> = {
  CAPTURE_AUTH: "Collect a pledge", VOID_AUTH: "Release a hold", REAUTH_AUTH: "Renew a hold", PAYOUT_ITEM: "Pay out", REFUND_CAPTURE: "Refund a payment",
};

export const STEP_STATES: Record<string, { label: string; tone: Tone }> = {
  PENDING: { label: "Waiting", tone: "grey" },
  SENT: { label: "Sent: waiting for PayPal", tone: "amber" },
  CONFIRMED: { label: "Confirmed", tone: "green" },
  FAILED: { label: "Failed", tone: "red" },
};

export const RULE_STATUS: Record<string, { symbol: string; label: string; tone: Tone }> = {
  PASS: { symbol: "✓", label: "Passed", tone: "green" },
  FAIL: { symbol: "✗", label: "Failed", tone: "red" },
  UNVERIFIED: { symbol: "?", label: "Could not be proved", tone: "amber" },
  SKIPPED: { symbol: "–", label: "Not checked", tone: "grey" },
};

/** The five tamper simulations (SPEC 7.5.6): which plan kind each applies to, and the rules that must catch it. A back-end test keeps this equal to the server's list. */
export const TAMPERS: Record<string, { kind: string; label: string; catches: string[] }> = {
  SWAP_RECIPIENT: { kind: "FREELANCER_PAYOUT", label: "Swap the recipient", catches: ["G-12", "G-03"] },
  INFLATE_AMOUNT: { kind: "FREELANCER_PAYOUT", label: "Inflate the amount", catches: ["G-12", "G-07"] },
  EXTRA_RECIPIENT: { kind: "FREELANCER_PAYOUT", label: "Add an extra recipient", catches: ["G-12", "G-04"] },
  DOUBLE_CAPTURE: { kind: "CAPTURE_PLEDGES", label: "Collect one pledge twice", catches: ["G-10", "G-02"] },
  CAPTURE_IN_RELEASE: { kind: "RELEASE_HOLDS", label: "Sneak a collection into a release", catches: ["G-11"] },
};

const lookup = <T>(table: Record<string, T>, key: string, fallback: T): T => table[key] ?? fallback;

export const planWord = (kind: string) => PLAN_WORDS[kind] ?? kind;
export const planState = (state: string) => lookup(PLAN_STATES, state, { label: state, tone: "grey" as Tone });
export const opWord = (op: string) => OP_WORDS[op] ?? op;
export const stepState = (state: string) => lookup(STEP_STATES, state, { label: state, tone: "grey" as Tone });
export const ruleStatus = (status: string) => lookup(RULE_STATUS, status, { symbol: "?", label: status, tone: "grey" as Tone });
/** A plan that has not been reviewed has no decision yet. */
export const decisionInfo = (decision: string | null) => (decision === null ? { label: "Not reviewed", tone: "grey" as Tone, hint: "The Guardian has not looked at this plan yet." } : lookup(DECISIONS, decision, { label: decision, tone: "grey" as Tone, hint: "" }));

export const tampersFor = (kind: string) => Object.entries(TAMPERS).filter(([, t]) => t.kind === kind).map(([key, t]) => ({ key, ...t }));

/** A plan that is moving: it keeps asking for news. */
export const isLive = (state: string) => state === "APPROVED" || state === "EXECUTING";

/** The Guardian's real verdict (simulations are never the real one). The server lists the newest first. */
export const realReview = (plan: PlanDetail): GuardianReview | null => plan.reviews.find((r) => !r.simulated) ?? null;

export function ruleCounts(rules: { status: string }[]) {
  const n = { PASS: 0, FAIL: 0, UNVERIFIED: 0, SKIPPED: 0 };
  for (const r of rules) if (r.status in n) n[r.status as keyof typeof n] += 1;
  return n;
}

export function roleOn(memberships: Membership[], projectId: number): Membership["role"] | null {
  return memberships.find((m) => m.project_id === projectId)?.role ?? null;
}

/** Who may ask the Guardian to review a plan. */
export const mayReview = (role: string | null, state: string) => (role === "LEAD" || role === "SPONSOR") && (state === "PROPOSED" || state === "REVIEWED");

/**
 * Approval, mirroring the server's rules so the button says why it is off (the server still decides):
 * the plan must be REVIEWED, the Guardian must not have blocked it, a HOLD needs a written reason from a person,
 * refunds and held capture/release plans are for the lead only, everything else for the lead or a sponsor.
 */
export function approval(plan: Pick<PlanDetail, "kind" | "state">, review: Pick<GuardianReview, "decision"> | null, role: string | null, note: string) {
  const needsNote = review?.decision === "HOLD";
  const no = (reason: string) => ({ ok: false as const, reason, needsNote });
  if (plan.state === "BLOCKED" || review?.decision === "BLOCK") return no("The Guardian blocked this plan. It can never be approved; fix the cause and build a new plan.");
  if (plan.state !== "REVIEWED" || review === null) return no("The plan must be checked by the Guardian first.");
  const leadOnly = plan.kind === "REFUND_CAPTURED" || (needsNote && (plan.kind === "CAPTURE_PLEDGES" || plan.kind === "RELEASE_HOLDS"));
  if (leadOnly ? role !== "LEAD" : role !== "LEAD" && role !== "SPONSOR") return no(leadOnly ? "Only the lead can approve this plan." : "Only the lead or a sponsor can approve this plan.");
  if (needsNote && note.trim() === "") return no("Write why it is safe to go ahead.");
  return { ok: true as const, reason: "", needsNote };
}
