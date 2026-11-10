import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PlansPage from "@/app/plans/page";
import { AuthProvider } from "@/lib/auth";
import { clearToken, setToken } from "@/lib/token";
import { lakshmi, mockFetch, planDetail, planItem, review, rule, step } from "./helpers";

// Tests added after the mutation check found weak spots in the plans screen.
const nav = vi.hoisted(() => ({ query: "id=1" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams(nav.query) }));

beforeEach(() => { clearToken(); nav.query = "id=1"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); clearToken(); });

const me = (role = "LEAD") => ({ user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role }] });
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const gridRows = () => Array.from(document.querySelectorAll(".ag-grid-scrolling-container .ag-row"));
const body = (c: { init: RequestInit }) => JSON.parse(String(c.init.body));
const cellOf = (row: Element, col: string) => row.querySelector(`[col-id="${col}"]`) as HTMLElement;
const byIndex = () => gridRows().sort((a, b) => Number(a.getAttribute("row-index")) - Number(b.getAttribute("row-index")));

const plans = [
  planItem({ id: 3, kind: "CAPTURE_PLEDGES", state: "DONE", decision: "ALLOW" }),
  planItem({ id: 2, kind: "FREELANCER_PAYOUT", state: "REVIEWED", decision: "HOLD" }),
];
const reviewed = (over: Record<string, unknown> = {}) => planDetail({ id: 2, state: "REVIEWED", decision: "ALLOW", reviews: [review()], ...over });

async function open(role = "LEAD", routes: Record<string, unknown> = {}) {
  setToken("tok");
  const m = mockFetch({ "GET /auth/me": { body: me(role) }, "GET /projects/1/plans": { body: { plans } }, ...routes } as never);
  wrapped(<PlansPage />);
  await screen.findByRole("list", { name: "Plans" });
  return m;
}
const pick = async (name: RegExp) => { fireEvent.click(screen.getByRole("button", { name })); return screen.findByTestId("plan-detail"); };

describe("steps grid", () => {
  it("pins and orders the step numbers, colours each state, and shows the reference and the problem", async () => {
    const steps = [step({ seq: 2, state: "CONFIRMED", paypal_ref: "PAYOUT-ABCDEFGHIJKLM" }), step({ seq: 1, state: "FAILED", error: { code: "X" } }), step({ seq: 3, state: "SENT" }), step({ seq: 4, state: "PENDING" })];
    await open("LEAD", { "GET /plans/2": { body: reviewed({ steps }) } });
    await pick(/Pay the builder/);
    await waitFor(() => expect(gridRows().length).toBe(4));
    expect(document.querySelector(".ag-root")!.className).toContain("ag-has-left-pinned-cols");
    expect(cellOf(gridRows()[0], "seq").className).toContain("ag-cell-last-left-pinned");
    expect(cellOf(gridRows()[0], "op").className).not.toContain("pinned");
    expect(byIndex().map((r) => cellOf(r, "seq").textContent)).toEqual(["1", "2", "3", "4"]);
    expect(gridRows().map((r) => r.getAttribute("row-id")).sort()).toEqual(["1", "2", "3", "4"]);
    const chip = (i: number) => /bg-(red|green|amber|gray)-100/.exec(cellOf(byIndex()[i], "state").querySelector("span")!.className)![0];
    expect([chip(0), chip(1), chip(2), chip(3)]).toEqual(["bg-red-100", "bg-green-100", "bg-amber-100", "bg-gray-100"]);
    const ref = cellOf(byIndex()[1], "paypal_ref").querySelector("span")!;
    expect([ref.textContent, ref.getAttribute("title")]).toEqual(["PAYOUT-ABC…", "PAYOUT-ABCDEFGHIJKLM"]);
    expect(cellOf(byIndex()[0], "error").textContent).toBe('{"code":"X"}');
    expect(cellOf(byIndex()[1], "error").textContent).toBe("");
  });
});

describe("Guardian panel", () => {
  it("colours each rule's mark by its result", async () => {
    const rules = [rule({ id: "G-01", status: "PASS" }), rule({ id: "G-02", status: "FAIL" }), rule({ id: "G-03", status: "UNVERIFIED" }), rule({ id: "G-04", status: "SKIPPED" })];
    await open("LEAD", { "GET /plans/2": { body: reviewed({ reviews: [review({ rules })] }) } });
    await pick(/Pay the builder/);
    const marks = within(screen.getByRole("list", { name: "Guardian rules" })).getAllByRole("listitem").map((li) => li.querySelector("[aria-label]")!);
    expect(marks.map((m) => /text-(green|red|amber|gray)-\d+/.exec(m.className)![0])).toEqual(["text-green-700", "text-red-700", "text-amber-700", "text-gray-400"]);
    expect(marks.map((m) => m.textContent)).toEqual(["✓", "✗", "?", "–"]);
  });

  it("raises an alert only when the AI review could not run, and says 'unknown' for a missing risk level", async () => {
    await open("LEAD", { "GET /plans/2": { body: reviewed({ reviews: [review({ llm: { status: "UNAVAILABLE", risk_level: null, explanation_for_sponsors: "A human must look.", findings: [] } })] }) } });
    await pick(/Pay the builder/);
    expect(screen.getByRole("alert").textContent).toBe("A human must look.");
    cleanup();
    await open("LEAD", { "GET /plans/2": { body: reviewed({ reviews: [review({ llm: { status: "OK", risk_level: null, explanation_for_sponsors: "Fine.", findings: [] } })] }) } });
    await pick(/Pay the builder/);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("unknown").className).toContain("bg-green-100");
  });
});

describe("actions", () => {
  it("clears an earlier problem when the next action is tried", async () => {
    let n = 0;
    await open("LEAD", { "GET /plans/2": () => ({ body: reviewed() }), "POST /plans/2/approve": () => (n++ === 0 ? { status: 409, body: { error: { code: "STALE_REVIEW", message: "out of date" } } } : { body: reviewed({ state: "APPROVED" }) }) });
    await pick(/Pay the builder/);
    fireEvent.click(screen.getByRole("button", { name: "Approve and run" }));
    expect((await screen.findByRole("alert")).textContent).toBe("out of date");
    fireEvent.click(screen.getByRole("button", { name: "Approve and run" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("clears the 'Asked PayPal' note when the next action is tried", async () => {
    let n = 0;
    await open("LEAD", { "GET /plans/2": { body: planDetail({ id: 2, project_id: 5, state: "EXECUTING", decision: "ALLOW", reviews: [review()] }) },
                         "POST /projects/5/money/refresh": () => (n++ === 0 ? { status: 202, body: { job_id: 1, already_running: false } } : { status: 503, body: { error: { code: "DOWN", message: "PayPal is busy" } } }) });
    await pick(/Pay the builder/);
    fireEvent.click(screen.getByRole("button", { name: "Ask PayPal now" }));
    expect(await screen.findByText("Asked PayPal. The steps update as it answers.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ask PayPal now" }));
    expect((await screen.findByRole("alert")).textContent).toBe("PayPal is busy");
    expect(screen.queryByText("Asked PayPal. The steps update as it answers.")).toBeNull();
  });

  it("asks PayPal about the plan's own project", async () => {
    const m = await open("LEAD", { "GET /plans/2": { body: planDetail({ id: 2, project_id: 5, state: "EXECUTING", decision: "ALLOW", reviews: [review()] }) },
                                   "POST /projects/5/money/refresh": { status: 202, body: { job_id: 1, already_running: false } } });
    await pick(/Pay the builder/);
    fireEvent.click(screen.getByRole("button", { name: "Ask PayPal now" }));
    await screen.findByText("Asked PayPal. The steps update as it answers.");
    expect(m.calls.find((c) => c.method === "POST")!.path).toBe("/projects/5/money/refresh");
  });

  it("sends the plan's own fingerprint with an approval, not the review's", async () => {
    const m = await open("LEAD", { "GET /plans/2": { body: reviewed({ reviews: [review({ plan_hash: "0".repeat(64) })] }) }, "POST /plans/2/approve": { body: reviewed({ state: "APPROVED" }) } });
    await pick(/Pay the builder/);
    fireEvent.click(screen.getByRole("button", { name: "Approve and run" }));
    await waitFor(() => expect(m.calls.some((c) => c.method === "POST")).toBe(true));
    expect(body(m.calls.find((c) => c.method === "POST")!).plan_hash).toBe("a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90");
  });

  it("will not approve twice while the first approval is on its way", async () => {
    let state = "REVIEWED";
    const m = await open("LEAD", { "GET /plans/2": () => ({ body: reviewed({ state }) }), "POST /plans/2/approve": () => { state = "APPROVED"; return { body: reviewed({ state }), delayMs: 200 }; } });
    await pick(/Pay the builder/);
    const button = screen.getByRole("button", { name: "Approve and run" }) as HTMLButtonElement;
    fireEvent.click(button);
    await waitFor(() => expect(button.textContent).toBe("Approving..."));
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    await waitFor(() => expect(screen.queryByRole("region", { name: "Approval" })).toBeNull());
    expect(m.calls.filter((c) => c.method === "POST")).toHaveLength(1);
  });

  it("limits the length of the written reason", async () => {
    await open("LEAD", { "GET /plans/2": { body: reviewed({ decision: "HOLD", reviews: [review({ decision: "HOLD" })] }) } });
    await pick(/Pay the builder/);
    expect(screen.getByLabelText("Why it is safe to go ahead").getAttribute("maxlength")).toBe("2000");
  });

  it("sends the tamper test that was clicked", async () => {
    const m = await open("LEAD", { "GET /plans/2": { body: reviewed() }, "POST /plans/2/simulate-tamper": () => ({ body: { simulation: true, mutation: "X", review: review({ simulated: true, decision: "BLOCK" }) } }) });
    await pick(/Pay the builder/);
    for (const [label, mutation] of [["Inflate the amount", "INFLATE_AMOUNT"], ["Add an extra recipient", "EXTRA_RECIPIENT"], ["Swap the recipient", "SWAP_RECIPIENT"]]) {
      fireEvent.click(screen.getByRole("button", { name: label }));
      await waitFor(() => expect(m.calls.filter((c) => c.method === "POST").map((c) => body(c).mutation).pop()).toBe(mutation));
    }
  });
});

describe("list and building", () => {
  it("marks the chosen plan in the list", async () => {
    nav.query = "id=1&plan=2";
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me() }, "GET /projects/1/plans": { body: { plans } }, "GET /plans/2": { body: reviewed() } });
    wrapped(<PlansPage />);
    await screen.findByTestId("plan-detail");
    expect(screen.getByRole("button", { name: /Pay the builder/ }).className).toContain("border-sea-600");
    expect(screen.getByRole("button", { name: /Collect the pledges/ }).className).toContain("border-gray-200");
    expect(screen.getByRole("button", { name: /Collect the pledges/ }).className).not.toContain("border-sea-600");
  });

  it("will not build two plans at once", async () => {
    const m = await open("LEAD", { "POST /projects/1/plans": { status: 201, body: planDetail({ id: 9 }), delayMs: 200 }, "GET /plans/9": { body: planDetail({ id: 9 }) } });
    const button = screen.getByRole("button", { name: "Build a payout plan" }) as HTMLButtonElement;
    fireEvent.click(button);
    await waitFor(() => expect(button.textContent).toBe("Building..."));
    expect(button.disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Build a refund plan" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(button);
    await screen.findByTestId("plan-detail");
    expect(m.calls.filter((c) => c.method === "POST")).toHaveLength(1);
  });

  it("reloads when a different person signs in", async () => {
    setToken("tok");
    let who = 0;
    const ravi = { id: 2, email: "ravi@velugu.example.com", display_name: "Ravi" };
    const m = mockFetch({
      "GET /auth/me": () => ({ body: who === 0 ? me() : { user: ravi, memberships: [{ member_id: 2, project_id: 1, role: "SPONSOR" }] } }),
      "POST /auth/login": () => { who = 1; return { body: { token: "tok2", user: ravi } }; },
      "GET /projects/1/plans": { body: { plans } },
    });
    const { Switch } = await import("./switch");
    wrapped(<><PlansPage /><Switch /></>);
    await screen.findByRole("list", { name: "Plans" });
    const before = m.calls.filter((c) => c.path === "/projects/1/plans").length;
    fireEvent.click(screen.getByRole("button", { name: "switch person" }));
    await waitFor(() => expect(m.calls.filter((c) => c.path === "/projects/1/plans").length).toBe(before + 1));
  });
});
