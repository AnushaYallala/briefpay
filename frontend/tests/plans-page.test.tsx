import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PlansPage from "@/app/plans/page";
import { AuthProvider } from "@/lib/auth";
import { PLAN_REFRESH_MS } from "@/lib/plans";
import { clearToken, setToken } from "@/lib/token";
import { lakshmi, mockFetch, planDetail, planItem, review, rule, step } from "./helpers";

const nav = vi.hoisted(() => ({ query: "id=1" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams(nav.query) }));

beforeEach(() => { clearToken(); nav.query = "id=1"; });
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  clearToken();
});

const me = (role = "LEAD") => ({ user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role }] });
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const gridRows = () => Array.from(document.querySelectorAll(".ag-grid-scrolling-container .ag-row"));
const body = (c: { init: RequestInit }) => JSON.parse(String(c.init.body));

const plans = [
  planItem({ id: 3, kind: "CAPTURE_PLEDGES", state: "DONE", decision: "ALLOW", reason: "GOAL_REACHED" }),
  planItem({ id: 2, kind: "FREELANCER_PAYOUT", state: "REVIEWED", decision: "HOLD" }),
  planItem({ id: 1, kind: "REFUND_CAPTURED", state: "PROPOSED", decision: null }),
];

async function open(role: string | null = "LEAD", routes: Record<string, unknown> = {}, list = plans) {
  if (role) setToken("tok");
  const m = mockFetch({ ...(role ? { "GET /auth/me": { body: me(role) } } : {}), "GET /projects/1/plans": { body: { plans: list } }, ...routes } as never);
  wrapped(<PlansPage />);
  await screen.findByRole("list", { name: "Plans" });
  return m;
}
const pick = async (name: RegExp) => { fireEvent.click(screen.getByRole("button", { name })); return screen.findByTestId("plan-detail"); };
const reviewed = (over: Record<string, unknown> = {}) => planDetail({ id: 2, state: "REVIEWED", decision: "ALLOW", reviews: [review()], ...over });

describe("plans page: the list", () => {
  it("lists every plan with plain words, state and decision, newest first", async () => {
    await open();
    const items = within(screen.getByRole("list", { name: "Plans" })).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toContain("Collect the pledges");
    expect(items[0].textContent).toContain("Done");
    expect(items[0].textContent).toContain("ALLOW");
    expect(items[1].textContent).toContain("Pay the builder");
    expect(items[1].textContent).toContain("Checked: waiting for a person");
    expect(items[1].textContent).toContain("HOLD");
    expect(items[2].textContent).toContain("Refund the pledgers");
    expect(items[2].textContent).toContain("Not reviewed");
    expect(items[2].textContent).toContain("Plan 1 · Nov 10, 12:00 UTC");
    expect(screen.getByText("Pick a plan")).toBeTruthy();
    expect(screen.getByText(/Money never moves on its own/)).toBeTruthy();
  });

  it("asks people who are not signed in to sign in, without calling the API", async () => {
    const m = mockFetch({});
    wrapped(<PlansPage />);
    expect(await screen.findByText("Sign in to see the money plans")).toBeTruthy();
    expect(m.calls).toHaveLength(0);
  });

  it("waits for the sign-in check before deciding", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me(), delayMs: 100 }, "GET /projects/1/plans": { body: { plans } } });
    wrapped(<PlansPage />);
    expect(screen.getByText("Checking who you are...")).toBeTruthy();
    expect(screen.queryByText("Sign in to see the money plans")).toBeNull();
    await screen.findByRole("list", { name: "Plans" });
  });

  it("shows the server's reason when the person is not a member", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me() }, "GET /projects/1/plans": { status: 403, body: { error: { code: "FORBIDDEN", message: "You are not on this project" } } } });
    wrapped(<PlansPage />);
    expect(await screen.findByText("You are not on this project")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Plans" })).toBeNull();
  });

  it("shows an empty state when there are no plans", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me() }, "GET /projects/1/plans": { body: { plans: [] } } });
    wrapped(<PlansPage />);
    expect(await screen.findByText("No money plans yet")).toBeTruthy();
  });

  it("asks for a project when the address has no valid id", async () => {
    for (const q of ["", "id=abc", "id=-1", "id=1234567890"]) {
      nav.query = q;
      const { unmount } = wrapped(<PlansPage />);
      expect(await screen.findByText("No project selected")).toBeTruthy();
      unmount();
    }
  });

  it("opens the plan named in the address", async () => {
    nav.query = "id=1&plan=2";
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me() }, "GET /projects/1/plans": { body: { plans } }, "GET /plans/2": { body: reviewed() } });
    wrapped(<PlansPage />);
    expect(await screen.findByTestId("plan-detail")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Pay the builder/ }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: /Collect the pledges/ }).getAttribute("aria-pressed")).toBe("false");
  });

  it("ignores a plan number that is not a number", async () => {
    nav.query = "id=1&plan=abc";
    await open();
    expect(screen.getByText("Pick a plan")).toBeTruthy();
  });
});

describe("plans page: one plan", () => {
  it("shows the steps in a grid with plain words and a state chip, and the plan's summary", async () => {
    const steps = [step({ seq: 1 }), step({ seq: 2, op: "VOID_AUTH", target_type: "PLEDGE", target_id: 7, amount_cents: 1000, bucket: "NONE", receiver_email: null, state: "FAILED", paypal_ref: "CAPTURE-ABCDEFGHIJKLMNOP", error: { code: "X" } })];
    await open("LEAD", { "GET /plans/2": { body: reviewed({ steps }) } });
    const detail = await pick(/Pay the builder/);
    await waitFor(() => expect(gridRows().length).toBe(2));
    const text = gridRows().map((r) => r.textContent ?? "");
    expect(text[0]).toContain("Pay out");
    expect(text[0]).toContain("Contract 1");
    expect(text[0]).toContain("$400.00");
    expect(text[0]).toContain("Pool");
    expect(text[0]).toContain("arjun-sandbox@velugu.example.com");
    expect(text[0]).toContain("Waiting");
    expect(text[1]).toContain("Release a hold");
    expect(text[1]).toContain("Pledge 7");
    expect(text[1]).toContain("Memo");
    expect(text[1]).toContain("Failed");
    expect(text[1]).toContain("CAPTURE-AB…");
    expect(gridRows()[1].className).toContain("bg-red-50");
    expect(gridRows()[0].className).not.toContain("bg-red-50");
    expect(detail.textContent).toContain("2 steps moving $410.00");
    expect(detail.textContent).toContain("Plan 2");
    expect(detail.textContent).toContain("Fingerprint a1b2c3d4e5f6");
    expect(detail.querySelector('[title="a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"]')).not.toBeNull();
  });

  it("says '1 step' for a single step, and shows the reason in words", async () => {
    await open("LEAD", { "GET /plans/3": { body: planDetail({ id: 3, kind: "CAPTURE_PLEDGES", state: "DONE", decision: "ALLOW", reason: "GOAL_REACHED", reviews: [review()] }) } });
    const detail = await pick(/Collect the pledges/);
    expect(detail.textContent).toContain("goal reached · 1 step moving $400.00");
  });

  it("shows the Guardian's rules with marks, the PayPal tag, counts and a red row for a failure", async () => {
    const rules = [rule(), rule({ id: "G-06", title: "PayPal-side proof", paypal_verified: true }), rule({ id: "G-07", title: "Conservation", status: "FAIL", detail: "money from nowhere" }),
                   rule({ id: "G-08", title: "Solvency", status: "UNVERIFIED" }), rule({ id: "G-09", title: "Success", status: "SKIPPED" })];
    await open("LEAD", { "GET /plans/2": { body: reviewed({ decision: "BLOCK", state: "BLOCKED", reviews: [review({ decision: "BLOCK", rules })] }) } });
    await pick(/Pay the builder/);
    const items = within(screen.getByRole("list", { name: "Guardian rules" })).getAllByRole("listitem");
    expect(items.map((i) => i.getAttribute("data-status"))).toEqual(["PASS", "PASS", "FAIL", "UNVERIFIED", "SKIPPED"]);
    expect(items[1].textContent).toContain("verified with PayPal (APIMatic SDK)");
    expect(items[0].textContent).not.toContain("APIMatic");
    expect(items[2].className).toContain("bg-red-50");
    expect(items[0].className).not.toContain("bg-red-50");
    expect(items[2].textContent).toContain("G-07 Conservation");
    expect(items[2].textContent).toContain("money from nowhere");
    expect(items.map((i) => i.querySelector("[aria-label]")!.getAttribute("aria-label"))).toEqual(["Passed", "Passed", "Failed", "Could not be proved", "Not checked"]);
    expect(screen.getByTestId("rule-counts").textContent).toBe("2 of 5 rules passed, 1 failed, 1 could not be proved, 1 not checked.");
    expect(screen.getByText("A safety rule failed. This plan can never run.")).toBeTruthy();
  });

  it("counts only the kinds of result that happened", async () => {
    await open("LEAD", { "GET /plans/2": { body: reviewed() } });
    await pick(/Pay the builder/);
    expect(screen.getByTestId("rule-counts").textContent).toBe("3 of 3 rules passed.");
  });

  it("lists the cautions of a HOLD and the AI risk review", async () => {
    const r = review({ decision: "HOLD", soft_flags: [{ id: "S-02", title: "Concentration", detail: "one payer holds at least 60% of the goal" }],
                       llm: { status: "OK", risk_level: "high", explanation_for_sponsors: "One person paid most of it.", findings: [{ type: "CONCENTRATION", detail: "60% from one payer", severity: "high" }] } });
    await open("LEAD", { "GET /plans/2": { body: reviewed({ decision: "HOLD", reviews: [r] }) } });
    await pick(/Pay the builder/);
    expect(within(screen.getByRole("list", { name: "Cautions" })).getByText("S-02 Concentration: one payer holds at least 60% of the goal")).toBeTruthy();
    expect(screen.getByText("One person paid most of it.")).toBeTruthy();
    expect(screen.getByText("CONCENTRATION: 60% from one payer")).toBeTruthy();
    expect(screen.getByText("high").className).toContain("bg-red-100");
    expect(screen.getByText(/The AI can only raise the caution level/)).toBeTruthy();
  });

  it.each([
    ["medium", "bg-amber-100"], ["low", "bg-green-100"],
  ])("colours a %s AI risk", async (level, cls) => {
    await open("LEAD", { "GET /plans/2": { body: reviewed({ reviews: [review({ llm: { status: "OK", risk_level: level, explanation_for_sponsors: "ok", findings: [] } })] }) } });
    await pick(/Pay the builder/);
    expect(screen.getByText(level).className).toContain(cls);
    expect(screen.queryByRole("list", { name: "Cautions" })).toBeNull();
  });

  it("explains when the AI review could not run, was skipped, or does not apply", async () => {
    const cases: [unknown, string][] = [
      [{ status: "UNAVAILABLE", risk_level: null, explanation_for_sponsors: "The AI risk review could not run, so a human must look.", findings: [] }, "The AI risk review could not run, so a human must look."],
      [{ status: "SKIPPED", reason: "blocked by a hard rule" }, "Not run: blocked by a hard rule."],
      [{ status: "SKIPPED" }, "Not run: a hard rule already blocked the plan."],
      [null, "No AI risk review for this plan."],
    ];
    for (const [llm, text] of cases) {
      cleanup();
      await open("LEAD", { "GET /plans/2": { body: reviewed({ reviews: [review({ llm })] }) } });
      await pick(/Pay the builder/);
      expect(screen.getByText(text)).toBeTruthy();
    }
  });

  it("says so when the Guardian has not looked yet", async () => {
    await open("LEAD", { "GET /plans/1": { body: planDetail({ id: 1, kind: "REFUND_CAPTURED" }) } });
    await pick(/Refund the pledgers/);
    expect(screen.getByText("The Guardian has not checked this plan yet.")).toBeTruthy();
    expect(screen.queryByTestId("guardian-panel")).toBeNull();
  });

  it("shows the real verdict, not a simulation, and who approved", async () => {
    const sim = review({ id: 99, simulated: true, decision: "BLOCK" });
    const approvals = [{ approver: "user:1", plan_hash: "x", ack_note: "I checked the work", created_at: "2026-11-10T13:00:00" }, { approver: "system:AUTO_ON_ALLOW", plan_hash: "x", ack_note: null, created_at: "2026-11-10T13:05:00" }];
    await open("LEAD", { "GET /plans/2": { body: reviewed({ state: "EXECUTING", reviews: [sim, review()], approvals }) } });
    await pick(/Pay the builder/);
    expect(screen.getAllByTestId("guardian-panel")).toHaveLength(1);
    expect(screen.getByText("Every safety rule passed.")).toBeTruthy();
    const list = within(screen.getByRole("region", { name: "Approvals" })).getAllByRole("listitem");
    expect(list[0].textContent).toBe('user:1 · Nov 10, 13:00 UTC · "I checked the work"');
    expect(list[1].textContent).toBe("the system (the Guardian allowed it automatically) · Nov 10, 13:05 UTC");
  });

  it("shows the server's reason when a plan cannot be loaded, and keeps the list", async () => {
    await open("LEAD", { "GET /plans/2": { status: 404, body: { error: { code: "PLAN_NOT_FOUND", message: "No such plan" } } } });
    fireEvent.click(screen.getByRole("button", { name: /Pay the builder/ }));
    expect(await screen.findByText("No such plan")).toBeTruthy();
    expect(screen.getByRole("list", { name: "Plans" })).toBeTruthy();
  });

  it("does not show one plan's details while another is loading", async () => {
    await open("LEAD", { "GET /plans/2": { body: reviewed() }, "GET /plans/3": { body: planDetail({ id: 3, kind: "CAPTURE_PLEDGES", state: "DONE", reviews: [review()] }), delayMs: 200 } });
    await pick(/Pay the builder/);
    fireEvent.click(screen.getByRole("button", { name: /Collect the pledges/ }));
    expect(screen.queryByTestId("plan-detail")).toBeNull();
    expect(screen.getByText("Loading the plan...")).toBeTruthy();
    expect((await screen.findByTestId("plan-detail")).textContent).toContain("Plan 3");
  });
});

describe("plans page: asking the Guardian and approving", () => {
  it("asks the Guardian for a check and shows the new verdict", async () => {
    let state = "PROPOSED";
    const m = await open("LEAD", {
      "GET /plans/1": () => ({ body: planDetail({ id: 1, state, decision: state === "REVIEWED" ? "ALLOW" : null, reviews: state === "REVIEWED" ? [review()] : [] }) }),
      "POST /plans/1/review": () => { state = "REVIEWED"; return { body: planDetail({ id: 1, state, reviews: [review()] }) }; },
    });
    await pick(/Refund the pledgers/);
    fireEvent.click(screen.getByRole("button", { name: "Run the Guardian check" }));
    expect(await screen.findByTestId("guardian-panel")).toBeTruthy();
    expect(m.calls.filter((c) => c.method === "POST").map((c) => c.path)).toEqual(["/plans/1/review"]);
    expect(screen.getByRole("button", { name: "Check again" })).toBeTruthy();
  });

  it("offers the check to the lead and sponsors only, and only before approval", async () => {
    for (const [role, expected] of [["SPONSOR", true], ["SUPPORTER", false], ["FREELANCER", false]] as const) {
      cleanup();
      await open(role, { "GET /plans/1": { body: planDetail({ id: 1 }) } });
      await pick(/Refund the pledgers/);
      expect(!!screen.queryByRole("button", { name: "Run the Guardian check" }), role).toBe(expected);
    }
    cleanup();
    await open("LEAD", { "GET /plans/3": { body: planDetail({ id: 3, state: "DONE", reviews: [review()] }) } });
    await pick(/Collect the pledges/);
    expect(screen.queryByRole("button", { name: /Guardian check|Check again/ })).toBeNull();
  });

  it("shows the server's reason when the check fails, and re-enables the button", async () => {
    await open("LEAD", { "GET /plans/1": { body: planDetail({ id: 1 }) }, "POST /plans/1/review": { status: 409, body: { error: { code: "PLAN_STATE", message: "plan is APPROVED" } } } });
    await pick(/Refund the pledgers/);
    fireEvent.click(screen.getByRole("button", { name: "Run the Guardian check" }));
    expect((await screen.findByRole("alert")).textContent).toBe("plan is APPROVED");
    expect((screen.getByRole("button", { name: "Run the Guardian check" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("approves an ALLOW plan with exactly the plan's fingerprint and the Guardian's review", async () => {
    let state = "REVIEWED";
    const m = await open("LEAD", {
      "GET /plans/2": () => ({ body: reviewed({ state }) }),
      "POST /plans/2/approve": () => { state = "APPROVED"; return { body: reviewed({ state }) }; },
    });
    await pick(/Pay the builder/);
    expect(screen.queryByLabelText("Why it is safe to go ahead")).toBeNull();
    const approve = screen.getByRole("button", { name: "Approve and run" }) as HTMLButtonElement;
    expect(approve.disabled).toBe(false);
    expect(screen.queryByTestId("why-not")).toBeNull();
    fireEvent.click(approve);
    await waitFor(() => expect(screen.queryByRole("region", { name: "Approval" })).toBeNull());
    const post = m.calls.find((c) => c.method === "POST")!;
    expect(post.path).toBe("/plans/2/approve");
    expect(body(post)).toEqual({ plan_hash: "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90", guardian_review_id: 11 });
  });

  it("makes a HOLD wait for a written reason, shows when the holds run out, and sends the reason", async () => {
    let state = "REVIEWED";
    const holdPlan = () => reviewed({ state, kind: "CAPTURE_PLEDGES", decision: "HOLD", earliest_honor_until: "2026-11-12T10:00:00", reviews: [review({ decision: "HOLD" })] });
    const m = await open("LEAD", { "GET /plans/2": () => ({ body: holdPlan() }), "POST /plans/2/approve": () => { state = "APPROVED"; return { body: holdPlan() }; } }, [planItem({ id: 2, kind: "CAPTURE_PLEDGES", state: "REVIEWED", decision: "HOLD" })]);
    await pick(/Collect the pledges/);
    expect(screen.getByTestId("honor").textContent).toBe("Earliest hold runs out: Nov 12, 10:00 UTC.");
    const approve = screen.getByRole("button", { name: "Approve and run" }) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);
    expect(screen.getByTestId("why-not").textContent).toBe("Write why it is safe to go ahead.");
    fireEvent.change(screen.getByLabelText("Why it is safe to go ahead"), { target: { value: "   " } });
    expect(approve.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Why it is safe to go ahead"), { target: { value: "  The pledgers are the sponsors.  " } });
    expect(approve.disabled).toBe(false);
    expect(screen.queryByTestId("why-not")).toBeNull();
    fireEvent.click(approve);
    await waitFor(() => expect(m.calls.some((c) => c.method === "POST")).toBe(true));
    expect(body(m.calls.find((c) => c.method === "POST")!)).toMatchObject({ guardian_review_id: 11, ack_note: "The pledgers are the sponsors." });
  });

  it("does not show a deadline when the plan has none", async () => {
    await open("LEAD", { "GET /plans/2": { body: reviewed({ decision: "HOLD", reviews: [review({ decision: "HOLD" })] }) } });
    await pick(/Pay the builder/);
    expect(screen.queryByTestId("honor")).toBeNull();
    expect(screen.getByText(/The Guardian says HOLD/)).toBeTruthy();
  });

  it("explains why the button is off for people who may not approve", async () => {
    await open("SUPPORTER", { "GET /plans/2": { body: reviewed() } });
    await pick(/Pay the builder/);
    expect((screen.getByRole("button", { name: "Approve and run" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("why-not").textContent).toBe("Only the lead or a sponsor can approve this plan.");
  });

  it("never offers approval for a blocked plan, and says why", async () => {
    await open("LEAD", { "GET /plans/2": { body: reviewed({ state: "REVIEWED", decision: "BLOCK", reviews: [review({ decision: "BLOCK" })] }) } });
    await pick(/Pay the builder/);
    expect((screen.getByRole("button", { name: "Approve and run" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("why-not").textContent).toContain("can never be approved");
  });

  it("offers no approval once a plan is approved, running, done or still unchecked", async () => {
    for (const state of ["PROPOSED", "APPROVED", "EXECUTING", "DONE", "BLOCKED"]) {
      cleanup();
      await open("LEAD", { "GET /plans/2": { body: reviewed({ state }) } });
      await pick(/Pay the builder/);
      expect(screen.queryByRole("region", { name: "Approval" }), state).toBeNull();
    }
  });

  it("shows the server's reason when approval is refused, and keeps the page", async () => {
    await open("LEAD", { "GET /plans/2": { body: reviewed() }, "POST /plans/2/approve": { status: 409, body: { error: { code: "STALE_REVIEW", message: "that Guardian review is out of date; review the plan again" } } } });
    await pick(/Pay the builder/);
    fireEvent.click(screen.getByRole("button", { name: "Approve and run" }));
    expect((await screen.findByRole("alert")).textContent).toBe("that Guardian review is out of date; review the plan again");
    expect(screen.getByTestId("plan-detail")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Approve and run" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("forgets the note and messages when another plan is opened", async () => {
    const hold = (id: number) => planDetail({ id, state: "REVIEWED", decision: "HOLD", reviews: [review({ decision: "HOLD" })] });
    await open("LEAD", { "GET /plans/2": { body: hold(2) }, "GET /plans/3": { body: hold(3) } });
    await pick(/Pay the builder/);
    fireEvent.change(screen.getByLabelText("Why it is safe to go ahead"), { target: { value: "because" } });
    fireEvent.click(screen.getByRole("button", { name: /Collect the pledges/ }));
    await waitFor(() => expect(screen.getByTestId("plan-detail").textContent).toContain("Plan 3"));
    expect((screen.getByLabelText("Why it is safe to go ahead") as HTMLTextAreaElement).value).toBe("");
  });
});

describe("plans page: trying to cheat (demo)", () => {
  const sim = (decision = "BLOCK") => ({ simulation: true, mutation: "SWAP_RECIPIENT", review: review({ id: 50, simulated: true, decision, rules: [rule(), rule({ id: "G-12", title: "Work and recipient binding", status: "FAIL", detail: "recipient is not the signed contract's" })] }) });

  it("offers the tamper tests that belong to the plan's kind, to the lead and sponsors only", async () => {
    await open("LEAD", { "GET /plans/2": { body: reviewed() } });
    await pick(/Pay the builder/);
    const region = screen.getByRole("region", { name: "Tamper test" });
    expect(within(region).getAllByRole("button").map((b) => b.textContent)).toEqual(["Swap the recipient", "Inflate the amount", "Add an extra recipient"]);
    expect(region.textContent).toContain("PayPal is never contacted");
    cleanup();
    await open("SUPPORTER", { "GET /plans/2": { body: reviewed() } });
    await pick(/Pay the builder/);
    expect(screen.queryByRole("region", { name: "Tamper test" })).toBeNull();
    cleanup();
    await open("SPONSOR", { "GET /plans/3": { body: planDetail({ id: 3, kind: "CAPTURE_PLEDGES", state: "DONE", reviews: [review()] }) } });
    await pick(/Collect the pledges/);
    expect(within(screen.getByRole("region", { name: "Tamper test" })).getAllByRole("button").map((b) => b.textContent)).toEqual(["Collect one pledge twice"]);
    cleanup();
    await open("LEAD", { "GET /plans/1": { body: planDetail({ id: 1, kind: "REFUND_CAPTURED" }) } });
    await pick(/Refund the pledgers/);
    expect(screen.queryByRole("region", { name: "Tamper test" })).toBeNull();
  });

  it("shows the Guardian refusing a tampered copy, labelled as a simulation, with the failed rule in red", async () => {
    const m = await open("LEAD", { "GET /plans/2": { body: reviewed() }, "POST /plans/2/simulate-tamper": { body: sim() } });
    await pick(/Pay the builder/);
    fireEvent.click(screen.getByRole("button", { name: "Swap the recipient" }));
    const panel = await screen.findByRole("region", { name: "Simulation: Swap the recipient" });
    expect(body(m.calls.find((c) => c.method === "POST")!)).toEqual({ mutation: "SWAP_RECIPIENT" });
    expect(panel.textContent).toContain("BLOCK");
    expect(panel.textContent).toContain("Simulation: this is a test on a tampered copy. PayPal was never contacted");
    expect(panel.querySelector('[data-rule="G-12"]')!.className).toContain("bg-red-50");
    expect(within(panel).getByTestId("rule-counts").textContent).toBe("1 of 2 rules passed, 1 failed.");
    expect(within(panel).queryByText("AI risk review")).toBeNull();
    expect(screen.getAllByTestId("guardian-panel")).toHaveLength(2);                 // the real verdict stays beside it
    expect(screen.getByText("Every safety rule passed.")).toBeTruthy();
  });

  it("shows the server's reason when the test cannot be built", async () => {
    await open("LEAD", { "GET /plans/2": { body: reviewed() }, "POST /plans/2/simulate-tamper": { status: 422, body: { error: { code: "CANNOT_TAMPER", message: "this plan has no recipient to swap" } } } });
    await pick(/Pay the builder/);
    fireEvent.click(screen.getByRole("button", { name: "Inflate the amount" }));
    expect((await screen.findByRole("alert")).textContent).toBe("this plan has no recipient to swap");
    expect(screen.queryByRole("region", { name: /Simulation:/ })).toBeNull();
  });

  it("clears a simulation when another plan is opened", async () => {
    await open("LEAD", { "GET /plans/2": { body: reviewed() }, "GET /plans/3": { body: planDetail({ id: 3, kind: "CAPTURE_PLEDGES", state: "DONE", reviews: [review()] }) }, "POST /plans/2/simulate-tamper": { body: sim() } });
    await pick(/Pay the builder/);
    fireEvent.click(screen.getByRole("button", { name: "Swap the recipient" }));
    await screen.findByRole("region", { name: /Simulation:/ });
    fireEvent.click(screen.getByRole("button", { name: /Collect the pledges/ }));
    await screen.findByText(/Plan 3/);
    expect(screen.queryByRole("region", { name: /Simulation:/ })).toBeNull();
  });
});

describe("plans page: live status", () => {
  const running = (over: Record<string, unknown> = {}) => planDetail({ id: 2, state: "EXECUTING", decision: "ALLOW", reviews: [review()], steps: [step({ state: "SENT" })], ...over });

  it("asks PayPal now, and reloads the plan", async () => {
    let n = 0;
    const m = await open("LEAD", { "GET /plans/2": () => { n += 1; return { body: running() }; }, "POST /projects/1/money/refresh": { status: 202, body: { job_id: 4, already_running: false } } });
    await pick(/Pay the builder/);
    const before = n;
    fireEvent.click(screen.getByRole("button", { name: "Ask PayPal now" }));
    expect(await screen.findByText("Asked PayPal. The steps update as it answers.")).toBeTruthy();
    await waitFor(() => expect(n).toBe(before + 1));
    expect(m.calls.find((c) => c.method === "POST")!.path).toBe("/projects/1/money/refresh");
  });

  it("offers 'Ask PayPal now' only while the plan is running", async () => {
    for (const state of ["REVIEWED", "APPROVED", "DONE", "FAILED"]) {
      cleanup();
      await open("LEAD", { "GET /plans/2": { body: running({ state }) } });
      await pick(/Pay the builder/);
      expect(screen.queryByRole("button", { name: "Ask PayPal now" }), state).toBeNull();
    }
  });

  it("keeps asking for news while the plan is moving and the tab is visible, not while hidden", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    await open("LEAD", { "GET /plans/2": () => { n += 1; return { body: running() }; } });
    await pick(/Pay the builder/);
    const first = n;
    await act(async () => { await vi.advanceTimersByTimeAsync(PLAN_REFRESH_MS - 1000); });
    expect(n).toBe(first);
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(n).toBe(first + 1);
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(PLAN_REFRESH_MS * 3); });
    expect(n).toBe(first + 1);
  });

  it("shows a step turning confirmed and the plan finishing, then stops asking", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    await open("LEAD", { "GET /plans/2": () => { n += 1; return { body: n === 1 ? running() : running({ state: "DONE", steps: [step({ state: "CONFIRMED", paypal_ref: "PAYOUT-1" })] }) }; } });
    await pick(/Pay the builder/);
    await waitFor(() => expect(gridRows()[0].textContent).toContain("Sent: waiting for PayPal"));
    await act(async () => { await vi.advanceTimersByTimeAsync(PLAN_REFRESH_MS + 500); });
    await waitFor(() => expect(gridRows()[0].textContent).toContain("Confirmed"));
    expect(screen.getByTestId("plan-detail").textContent).toContain("Done");
    const calls = n;
    await act(async () => { await vi.advanceTimersByTimeAsync(PLAN_REFRESH_MS * 3); });
    expect(n).toBe(calls);
  });

  it("does not ask for news about a plan that is not moving", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    await open("LEAD", { "GET /plans/2": () => { n += 1; return { body: reviewed() }; } });
    await pick(/Pay the builder/);
    const first = n;
    await act(async () => { await vi.advanceTimersByTimeAsync(PLAN_REFRESH_MS * 3); });
    expect(n).toBe(first);
  });

  it("keeps the plan on screen when a refresh fails, and says so", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    await open("LEAD", { "GET /plans/2": () => (n++ === 0 ? { body: running() } : { status: 500, body: { error: { code: "X", message: "boom" } } }) });
    await pick(/Pay the builder/);
    await act(async () => { await vi.advanceTimersByTimeAsync(PLAN_REFRESH_MS + 500); });
    expect(await screen.findByText(/Could not refresh just now \(boom\)/)).toBeTruthy();
    expect(screen.getByTestId("plan-detail")).toBeTruthy();
  });
});

describe("plans page: building a plan", () => {
  it("builds a payout plan, opens it, and refreshes the list", async () => {
    let made = false;
    const m = await open("LEAD", {
      "GET /projects/1/plans": () => ({ body: { plans: made ? [planItem({ id: 9 }), ...plans] : plans } }),
      "POST /projects/1/plans": () => { made = true; return { status: 201, body: planDetail({ id: 9 }) }; },
      "GET /plans/9": { body: planDetail({ id: 9 }) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Build a payout plan" }));
    expect((await screen.findByTestId("plan-detail")).textContent).toContain("Plan 9");
    expect(body(m.calls.find((c) => c.method === "POST")!)).toEqual({ kind: "FREELANCER_PAYOUT" });
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Plans" })).getAllByRole("listitem")).toHaveLength(4));
  });

  it("builds a refund plan for the lead only", async () => {
    const m = await open("LEAD", { "POST /projects/1/plans": { status: 201, body: planDetail({ id: 8, kind: "REFUND_CAPTURED" }) }, "GET /plans/8": { body: planDetail({ id: 8, kind: "REFUND_CAPTURED" }) } });
    fireEvent.click(screen.getByRole("button", { name: "Build a refund plan" }));
    await screen.findByTestId("plan-detail");
    expect(body(m.calls.find((c) => c.method === "POST")!)).toEqual({ kind: "REFUND_CAPTURED" });
    for (const [role, payout, refund] of [["SPONSOR", true, false], ["SUPPORTER", false, false], ["FREELANCER", false, false]] as const) {
      cleanup();
      await open(role);
      expect(!!screen.queryByRole("button", { name: "Build a payout plan" }), role).toBe(payout);
      expect(!!screen.queryByRole("button", { name: "Build a refund plan" }), role).toBe(refund);
    }
  });

  it("shows the server's reason when a plan cannot be built", async () => {
    await open("LEAD", { "POST /projects/1/plans": { status: 409, body: { error: { code: "CANNOT_BUILD_PLAN", message: "the work has not been verified" } } } });
    fireEvent.click(screen.getByRole("button", { name: "Build a payout plan" }));
    expect((await screen.findByRole("alert")).textContent).toBe("the work has not been verified");
    expect((screen.getByRole("button", { name: "Build a payout plan" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByTestId("plan-detail")).toBeNull();
  });

  it("the Refresh button asks for the list again", async () => {
    const m = await open();
    const before = m.calls.filter((c) => c.path === "/projects/1/plans").length;
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(m.calls.filter((c) => c.path === "/projects/1/plans").length).toBe(before + 1));
  });

  it("keeps the list and says so when a refresh of the list fails", async () => {
    let n = 0;
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me() }, "GET /projects/1/plans": () => (n++ === 0 ? { body: { plans } } : { status: 500, body: { error: { code: "X", message: "down" } } }) });
    wrapped(<PlansPage />);
    await screen.findByRole("list", { name: "Plans" });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText(/Could not refresh just now \(down\)/)).toBeTruthy();
    expect(within(screen.getByRole("list", { name: "Plans" })).getAllByRole("listitem")).toHaveLength(3);
  });
});
