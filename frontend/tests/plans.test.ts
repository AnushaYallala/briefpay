import { describe, expect, it } from "vitest";
import {
  DECISIONS, OP_WORDS, PLAN_REFRESH_MS, PLAN_STATES, RULE_STATUS, STEP_STATES, TAMPERS, approval, decisionInfo, isLive, mayReview, opWord, planState,
  planWord, realReview, roleOn, ruleCounts, ruleStatus, stepState, tampersFor,
} from "@/lib/plans";
import { planDetail, review } from "./helpers";

describe("plan words", () => {
  it("has plain words for kinds, states, decisions, operations and step states, and passes unknown ones through", () => {
    expect(planWord("FREELANCER_PAYOUT")).toBe("Pay the builder");
    expect(planWord("NEW_KIND")).toBe("NEW_KIND");
    expect(planState("EXECUTING")).toEqual({ label: "Running", tone: "amber" });
    expect(planState("MYSTERY")).toEqual({ label: "MYSTERY", tone: "grey" });
    expect(opWord("VOID_AUTH")).toBe("Release a hold");
    expect(opWord("NEW_OP")).toBe("NEW_OP");
    expect(stepState("CONFIRMED").tone).toBe("green");
    expect(stepState("FAILED").tone).toBe("red");
    expect(stepState("ODD")).toEqual({ label: "ODD", tone: "grey" });
    expect(ruleStatus("FAIL")).toEqual({ symbol: "✗", label: "Failed", tone: "red" });
    expect(ruleStatus("PASS").symbol).toBe("✓");
    expect(ruleStatus("UNVERIFIED").symbol).toBe("?");
    expect(ruleStatus("SKIPPED").symbol).toBe("–");
    expect(ruleStatus("ODD")).toEqual({ symbol: "?", label: "ODD", tone: "grey" });
    expect([Object.keys(PLAN_STATES).length, Object.keys(STEP_STATES).length, Object.keys(OP_WORDS).length, Object.keys(RULE_STATUS).length, Object.keys(DECISIONS).length]).toEqual([8, 4, 5, 4, 3]);
  });

  it("colours every state, step state and rule result", () => {
    const tones = (table: Record<string, { tone: string }>) => Object.fromEntries(Object.entries(table).map(([k, v]) => [k, v.tone]));
    expect(tones(PLAN_STATES)).toEqual({ PROPOSED: "grey", REVIEWED: "blue", APPROVED: "teal", EXECUTING: "amber", DONE: "green", PARTIAL: "red", FAILED: "red", BLOCKED: "red" });
    expect(tones(STEP_STATES)).toEqual({ PENDING: "grey", SENT: "amber", CONFIRMED: "green", FAILED: "red" });
    expect(tones(RULE_STATUS)).toEqual({ PASS: "green", FAIL: "red", UNVERIFIED: "amber", SKIPPED: "grey" });
    expect(tones(DECISIONS)).toEqual({ ALLOW: "green", HOLD: "amber", BLOCK: "red" });
  });

  it("describes a decision, including 'not reviewed yet' and unknown ones", () => {
    expect(decisionInfo(null)).toEqual({ label: "Not reviewed", tone: "grey", hint: "The Guardian has not looked at this plan yet." });
    expect(decisionInfo("ALLOW")).toMatchObject({ label: "ALLOW", tone: "green" });
    expect(decisionInfo("HOLD")).toMatchObject({ label: "HOLD", tone: "amber" });
    expect(decisionInfo("BLOCK")).toMatchObject({ label: "BLOCK", tone: "red" });
    expect(decisionInfo("WEIRD")).toEqual({ label: "WEIRD", tone: "grey", hint: "" });
  });

  it("knows which tamper tests belong to which plan kind", () => {
    expect(tampersFor("FREELANCER_PAYOUT").map((t) => t.key)).toEqual(["SWAP_RECIPIENT", "INFLATE_AMOUNT", "EXTRA_RECIPIENT"]);
    expect(tampersFor("CAPTURE_PLEDGES").map((t) => t.key)).toEqual(["DOUBLE_CAPTURE"]);
    expect(tampersFor("RELEASE_HOLDS").map((t) => t.key)).toEqual(["CAPTURE_IN_RELEASE"]);
    expect(tampersFor("REFUND_CAPTURED")).toEqual([]);
    expect(Object.keys(TAMPERS)).toHaveLength(5);
  });
});

describe("plan helpers", () => {
  it("polls only approved or running plans, gently", () => {
    expect(["APPROVED", "EXECUTING"].map(isLive)).toEqual([true, true]);
    expect(["PROPOSED", "REVIEWED", "DONE", "PARTIAL", "FAILED", "BLOCKED"].map(isLive)).toEqual([false, false, false, false, false, false]);
    expect(PLAN_REFRESH_MS).toBe(5000);
  });

  it("takes the newest real review, never a simulation", () => {
    const sim = review({ id: 30, simulated: true, decision: "BLOCK" });
    const real = review({ id: 20 });
    const older = review({ id: 10 });
    expect(realReview(planDetail({ reviews: [sim, real, older] }))?.id).toBe(20);
    expect(realReview(planDetail({ reviews: [sim] }))).toBeNull();
    expect(realReview(planDetail({ reviews: [] }))).toBeNull();
  });

  it("counts rule results", () => {
    expect(ruleCounts([{ status: "PASS" }, { status: "PASS" }, { status: "FAIL" }, { status: "UNVERIFIED" }, { status: "SKIPPED" }, { status: "ODD" }])).toEqual({ PASS: 2, FAIL: 1, UNVERIFIED: 1, SKIPPED: 1 });
    expect(ruleCounts([])).toEqual({ PASS: 0, FAIL: 0, UNVERIFIED: 0, SKIPPED: 0 });
  });

  it("finds the person's role on a project", () => {
    const ms = [{ member_id: 1, project_id: 1, role: "LEAD" as const }, { member_id: 2, project_id: 2, role: "SPONSOR" as const }];
    expect(roleOn(ms, 1)).toBe("LEAD");
    expect(roleOn(ms, 2)).toBe("SPONSOR");
    expect(roleOn(ms, 3)).toBeNull();
    expect(roleOn([], 1)).toBeNull();
  });

  it("lets only the lead or a sponsor ask for a Guardian check, and only before approval", () => {
    expect([["LEAD", "PROPOSED"], ["SPONSOR", "PROPOSED"], ["LEAD", "REVIEWED"], ["SPONSOR", "REVIEWED"]].map(([r, s]) => mayReview(r, s as string))).toEqual([true, true, true, true]);
    expect([["SUPPORTER", "PROPOSED"], ["FREELANCER", "PROPOSED"], [null, "PROPOSED"], ["LEAD", "APPROVED"], ["LEAD", "EXECUTING"], ["LEAD", "DONE"], ["LEAD", "BLOCKED"]].map(([r, s]) => mayReview(r, s as string))).toEqual([false, false, false, false, false, false, false]);
  });
});

describe("approval rules, as the server has them", () => {
  const plan = (kind: string, state = "REVIEWED") => ({ kind, state });
  const allow = { decision: "ALLOW" };
  const hold = { decision: "HOLD" };

  it("allows an ALLOW plan for the lead or a sponsor", () => {
    expect(approval(plan("FREELANCER_PAYOUT"), allow, "LEAD", "")).toEqual({ ok: true, reason: "", needsNote: false });
    expect(approval(plan("FREELANCER_PAYOUT"), allow, "SPONSOR", "")).toMatchObject({ ok: true });
    expect(approval(plan("CAPTURE_PLEDGES"), allow, "SPONSOR", "")).toMatchObject({ ok: true });
    expect(approval(plan("RELEASE_HOLDS"), allow, "SPONSOR", "")).toMatchObject({ ok: true });
  });

  it("refuses everyone else, with the reason", () => {
    for (const role of ["SUPPORTER", "FREELANCER", null]) expect(approval(plan("FREELANCER_PAYOUT"), allow, role, "")).toEqual({ ok: false, reason: "Only the lead or a sponsor can approve this plan.", needsNote: false });
  });

  it("lets only the lead approve refunds, and held capture or release plans", () => {
    expect(approval(plan("REFUND_CAPTURED"), allow, "SPONSOR", "")).toEqual({ ok: false, reason: "Only the lead can approve this plan.", needsNote: false });
    expect(approval(plan("REFUND_CAPTURED"), allow, "LEAD", "")).toMatchObject({ ok: true });
    expect(approval(plan("CAPTURE_PLEDGES"), hold, "SPONSOR", "because")).toMatchObject({ ok: false, reason: "Only the lead can approve this plan." });
    expect(approval(plan("RELEASE_HOLDS"), hold, "SPONSOR", "because")).toMatchObject({ ok: false, reason: "Only the lead can approve this plan." });
    expect(approval(plan("CAPTURE_PLEDGES"), hold, "LEAD", "because")).toMatchObject({ ok: true, needsNote: true });
    expect(approval(plan("FREELANCER_PAYOUT"), hold, "SPONSOR", "because")).toMatchObject({ ok: true });   // a held payout may be approved by a sponsor
  });

  it("needs a written reason for a HOLD, not just spaces", () => {
    expect(approval(plan("FREELANCER_PAYOUT"), hold, "LEAD", "")).toEqual({ ok: false, reason: "Write why it is safe to go ahead.", needsNote: true });
    expect(approval(plan("FREELANCER_PAYOUT"), hold, "LEAD", "   \n ")).toMatchObject({ ok: false, reason: "Write why it is safe to go ahead." });
    expect(approval(plan("FREELANCER_PAYOUT"), hold, "LEAD", " I checked ")).toMatchObject({ ok: true, needsNote: true });
  });

  it("never approves a blocked plan, or one that has not been reviewed", () => {
    const blocked = "The Guardian blocked this plan. It can never be approved; fix the cause and build a new plan.";
    expect(approval(plan("FREELANCER_PAYOUT", "BLOCKED"), { decision: "BLOCK" }, "LEAD", "x")).toEqual({ ok: false, reason: blocked, needsNote: false });
    expect(approval(plan("FREELANCER_PAYOUT", "BLOCKED"), null, "LEAD", "x")).toEqual({ ok: false, reason: blocked, needsNote: false });
    expect(approval(plan("FREELANCER_PAYOUT", "REVIEWED"), { decision: "BLOCK" }, "LEAD", "x")).toEqual({ ok: false, reason: blocked, needsNote: false });
    const first = { ok: false, reason: "The plan must be checked by the Guardian first.", needsNote: false };
    for (const state of ["PROPOSED", "APPROVED", "EXECUTING", "DONE", "FAILED"]) expect(approval(plan("FREELANCER_PAYOUT", state), allow, "LEAD", "x")).toEqual(first);
    expect(approval(plan("FREELANCER_PAYOUT", "REVIEWED"), null, "LEAD", "x")).toEqual(first);
  });
});
