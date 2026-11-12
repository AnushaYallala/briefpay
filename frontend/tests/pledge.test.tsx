import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CampaignPage from "@/app/campaign/page";
import { PledgeBox, amountProblem } from "@/components/PledgeBox";
import { AuthProvider, useAuth } from "@/lib/auth";
import { clearToken, setToken } from "@/lib/token";
import type { CampaignView } from "@/lib/types";
import { campaignView, lakshmi, leadPart, ledger, mockFetch } from "./helpers";

const h = vi.hoisted(() => ({
  push: vi.fn(),
  options: [] as { createOrder: () => Promise<string>; onApprove: (d: { orderID: string }) => Promise<void>; onCancel?: () => void; onError?: (e: unknown) => void }[],
  closed: vi.fn(),
  load: null as null | ((id: string, currency: string) => Promise<unknown>),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: h.push }), useSearchParams: () => new URLSearchParams("id=1") }));
vi.mock("@/lib/paypal", () => ({
  PAYPAL_CLIENT_ID: "sb-client",
  loadPayPal: (id: string, currency: string) => h.load!(id, currency),
}));

const fakePayPal = () => Promise.resolve({
  Buttons: (o: (typeof h.options)[number]) => { h.options.push(o); return { render: vi.fn(async () => undefined), close: async () => { h.closed(); } }; },
});

beforeEach(() => { clearToken(); h.options.length = 0; h.push.mockClear(); h.closed.mockClear(); h.load = vi.fn(fakePayPal); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); clearToken(); });

const me = (role: string | null) => ({ user: lakshmi, memberships: role ? [{ member_id: 1, project_id: 1, role }] : [] });
const posts = (m: { calls: { method: string; path: string; init: RequestInit }[] }) => m.calls.filter((c) => c.method === "POST");
const bodyOf = (c: { init: RequestInit }) => JSON.parse(String(c.init.body));
const type = (label: RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

async function openPage(role: string | null, view: CampaignView = campaignView(), routes: Record<string, unknown> = {}) {
  setToken("tok");
  const m = mockFetch({
    "GET /auth/me": { body: me(role) }, "GET /campaigns/1": { body: view }, "GET /projects/1/ledger": { body: ledger([]) },
    "GET /campaigns/1/strategist": { status: 404, body: { error: { code: "NO_REPORT", message: "none" } } }, ...routes,
  } as never);
  render(<AuthProvider><CampaignPage /></AuthProvider>);
  await screen.findByTestId("title");
  return m;
}

const order = { id: 7, campaign_id: 1, display_name: "Lakshmi", amount_cents: 2500, status: "CREATED", order_id: "ORDER-7", honor_until: null, currency: "USD" };
const held = { ...order, status: "AUTHORIZED", honor_until: "2026-11-13T12:00:00+00:00" };

describe("the amount rules shown before anything is sent", () => {
  it("accepts an amount between the smallest pledge and what is still needed, and explains anything else", () => {
    expect(amountProblem("25", 500, 25000, "USD")).toEqual({ cents: 2500, problem: null });
    expect(amountProblem("5", 500, 25000, "USD").cents).toBe(500);
    expect(amountProblem("250.00", 500, 25000, "USD").cents).toBe(25000);
    expect(amountProblem("", 500, 25000, "USD")).toEqual({ cents: null, problem: null });
    expect(amountProblem("4.99", 500, 25000, "USD").problem).toBe("The smallest pledge is $5.00.");
    expect(amountProblem("250.01", 500, 25000, "USD").problem).toBe("Only $250.00 is still needed.");
    expect(amountProblem("ten", 500, 25000, "USD").problem).toBe("Amounts are in dollars, for example 25 or 12.50.");
    expect(amountProblem("-5", 500, 25000, "USD").cents).toBeNull();
  });
});

describe("the pledge box", () => {
  it("shows no PayPal button until the amount is acceptable, then offers it", async () => {
    await openPage("SPONSOR");
    expect(screen.getByTestId("pledge-hint")).toBeTruthy();
    expect(h.options).toHaveLength(0);
    type(/Amount to hold/, "4");
    expect(screen.getByTestId("amount-problem").textContent).toBe("The smallest pledge is $5.00.");
    expect(h.options).toHaveLength(0);
    type(/Amount to hold/, "25");
    await waitFor(() => expect(h.options).toHaveLength(1));
    expect(screen.getByTestId("paypal-button")).toBeTruthy();
    expect(screen.getByText(/This only holds \$25\.00; it is not a payment\./)).toBeTruthy();
    expect(h.load).toHaveBeenCalledWith("sb-client", "USD");
    type(/Amount to hold/, "ten");
    await waitFor(() => expect(h.closed).toHaveBeenCalled());          // the button goes away again
    expect(screen.queryByTestId("paypal-button")).toBeNull();
  });

  it("starts the order with the typed amount in cents and the name, and returns PayPal's order id", async () => {
    const m = await openPage("SPONSOR", campaignView(), { "POST /campaigns/1/pledges/order": { status: 201, body: order } });
    type(/Amount to hold/, "25");
    type(/Name on the board/, "  Meena K ");
    await waitFor(() => expect(h.options).toHaveLength(1));
    expect(await h.options[0].createOrder()).toBe("ORDER-7");
    expect(bodyOf(posts(m)[0])).toEqual({ amount_cents: 2500, display_name: "Meena K" });
  });

  it("uses the latest amount without rebuilding the button each time it changes", async () => {
    const m = await openPage("SPONSOR", campaignView(), { "POST /campaigns/1/pledges/order": { status: 201, body: order } });
    type(/Amount to hold/, "25");
    await waitFor(() => expect(h.options).toHaveLength(1));
    type(/Amount to hold/, "30.50");
    await h.options[0].createOrder();
    expect(h.options).toHaveLength(1);
    expect(bodyOf(posts(m)[0]).amount_cents).toBe(3050);
  });

  it("places the hold when PayPal says it was approved, thanks the supporter, and refreshes the campaign", async () => {
    const m = await openPage("SPONSOR", campaignView(), {
      "POST /campaigns/1/pledges/order": { status: 201, body: order }, "POST /campaigns/1/pledges/authorize": { body: held },
    });
    type(/Amount to hold/, "25");
    await waitFor(() => expect(h.options).toHaveLength(1));
    const before = m.calls.filter((c) => c.path === "/campaigns/1").length;
    await act(async () => { await h.options[0].onApprove({ orderID: "ORDER-7" }); });
    expect(bodyOf(posts(m)[0])).toEqual({ order_id: "ORDER-7" });
    const done = await screen.findByTestId("pledge-done");
    expect(done.textContent).toContain("Thank you, Lakshmi.");
    expect(done.textContent).toContain("$25.00 is held on your PayPal account");
    expect(done.textContent).toContain("charged only if the goal is reached");
    await waitFor(() => expect(m.calls.filter((c) => c.path === "/campaigns/1").length).toBeGreaterThan(before));
    expect(screen.queryByTestId("pledge-form")).toBeNull();
    expect(h.closed).toHaveBeenCalled();                                  // PayPal's button is taken down once the hold exists
  });

  it("offers to hold another amount while money is still needed, and not once the goal is covered", async () => {
    await openPage("SPONSOR", campaignView(), {
      "POST /campaigns/1/pledges/order": { status: 201, body: order }, "POST /campaigns/1/pledges/authorize": { body: held },
    });
    type(/Amount to hold/, "25");
    await waitFor(() => expect(h.options).toHaveLength(1));
    await act(async () => { await h.options[0].onApprove({ orderID: "ORDER-7" }); });
    fireEvent.click(await screen.findByRole("button", { name: "Hold another amount" }));
    expect((screen.getByLabelText(/Amount to hold/) as HTMLInputElement).value).toBe("");
    expect(screen.queryByTestId("pledge-done")).toBeNull();
    cleanup();
    let covered = false;                                                    // the last $5 needed: after it is held nothing is still needed
    await openPage("SPONSOR", campaignView(), {
      "GET /campaigns/1": () => ({ body: campaignView({ remaining_need_cents: covered ? 0 : 500 }) }),
      "POST /campaigns/1/pledges/order": { status: 201, body: order },
      "POST /campaigns/1/pledges/authorize": () => { covered = true; return { body: held }; },
    });
    type(/Amount to hold/, "5");
    await waitFor(() => expect(h.options.length).toBeGreaterThan(0));
    await act(async () => { await h.options[h.options.length - 1].onApprove({ orderID: "ORDER-7" }); });
    await screen.findByTestId("pledge-done");
    expect(screen.queryByRole("button", { name: "Hold another amount" })).toBeNull();
  });

  it("forgets the last pledge's thank-you when a different person is signed in", async () => {
    const ravi = { id: 2, email: "ravi@velugu.example.com", display_name: "Ravi" };
    let who = lakshmi;
    function Switch() { const a = useAuth(); return <button onClick={() => void a.login(ravi.email, ravi.display_name)}>switch to Ravi</button>; }
    setToken("tok");
    mockFetch({
      "GET /auth/me": () => ({ body: { user: who, memberships: [{ member_id: 1, project_id: 1, role: "SPONSOR" }] } }),
      "POST /auth/login": () => { who = ravi; return { body: { token: "tok2", user: ravi } }; },
      "GET /campaigns/1": { body: campaignView() }, "GET /projects/1/ledger": { body: ledger([]) },
      "GET /campaigns/1/strategist": { status: 404, body: { error: { code: "NO_REPORT", message: "none" } } },
      "POST /campaigns/1/pledges/order": { status: 201, body: order }, "POST /campaigns/1/pledges/authorize": { body: held },
    } as never);
    render(<AuthProvider><Switch /><CampaignPage /></AuthProvider>);
    await screen.findByTestId("title");
    type(/Amount to hold/, "25");
    await waitFor(() => expect(h.options).toHaveLength(1));
    await act(async () => { await h.options[0].onApprove({ orderID: "ORDER-7" }); });
    expect((await screen.findByTestId("pledge-done")).textContent).toContain("Thank you, Lakshmi.");
    fireEvent.click(screen.getByRole("button", { name: "switch to Ravi" }));
    await waitFor(() => expect(screen.queryByTestId("pledge-done")).toBeNull());
    expect((screen.getByLabelText(/Name on the board/) as HTMLInputElement).value).toBe("Ravi");
  });

  it("shows the server's reason when the order cannot be started, and when the hold is declined", async () => {
    await openPage("SPONSOR", campaignView(), {
      "POST /campaigns/1/pledges/order": { status: 403, body: { error: { code: "FREELANCER_CANNOT_PLEDGE", message: "The freelancer cannot fund their own job" } } },
      "POST /campaigns/1/pledges/authorize": { status: 402, body: { error: { code: "PLEDGE_DECLINED", message: "PayPal did not place the hold (status DENIED)" } } },
    });
    type(/Amount to hold/, "25");
    await waitFor(() => expect(h.options).toHaveLength(1));
    await expect(h.options[0].createOrder()).rejects.toThrow();
    expect((await screen.findByRole("alert", {}, { timeout: 2000 })).textContent).toBe("The freelancer cannot fund their own job");
    await act(async () => { await h.options[0].onApprove({ orderID: "ORDER-7" }); });
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("PayPal did not place the hold (status DENIED)"));
    expect(screen.queryByTestId("pledge-done")).toBeNull();
  });

  it("says nothing was held when the supporter closes PayPal, and that nothing was charged if PayPal fails", async () => {
    await openPage("SPONSOR");
    type(/Amount to hold/, "25");
    await waitFor(() => expect(h.options).toHaveLength(1));
    act(() => h.options[0].onCancel!());
    expect(screen.getByRole("status").textContent).toBe("You closed PayPal. Nothing was held and nothing was charged.");
    act(() => h.options[0].onError!(new Error("x")));
    expect(screen.getByRole("alert").textContent).toBe("PayPal could not finish. Nothing was charged. Please try again.");
  });

  it("prefills the suggested share", async () => {
    await openPage("SPONSOR", campaignView({ suggested_share_cents: 10000 }));
    expect((screen.getByLabelText(/Amount to hold/) as HTMLInputElement).value).toBe("100.00");
    await waitFor(() => expect(h.options).toHaveLength(1));
  });

  it("tells the signed-out visitor to sign in, the builder that they cannot pledge, and a closed campaign nothing to pledge", async () => {
    mockFetch({ "GET /campaigns/1": { body: campaignView() }, "GET /projects/1/ledger": { body: ledger([]) } } as never);
    render(<AuthProvider><CampaignPage /></AuthProvider>);
    expect((await screen.findByTestId("pledge-unavailable")).textContent).toContain("Sign in to hold an amount");
    cleanup();
    await openPage("FREELANCER");
    expect(screen.getByTestId("pledge-unavailable").textContent).toBe("The builder cannot fund their own job.");
    expect(h.options).toHaveLength(0);
    cleanup();
    await openPage("SPONSOR", campaignView({ state: "CAPTURED", held_not_charged: false }));
    expect(screen.queryByRole("region", { name: "Pledge" })).toBeNull();
  });

  it("says plainly when PayPal is not set up on the site, instead of showing a button that cannot work", () => {
    const view = campaignView() as CampaignView;
    render(<PledgeBox campaign={view} role="SPONSOR" signedIn userName="Lakshmi" onPledged={() => undefined} clientId="" />);
    expect(screen.getByTestId("pledge-unavailable").textContent).toContain("PayPal is not set up on this site yet");
    expect(screen.queryByLabelText(/Amount to hold/)).toBeNull();
  });

  it("shows why when PayPal's button cannot be loaded", async () => {
    h.load = vi.fn(() => Promise.reject(new Error("PayPal's button could not be loaded. Check your connection and try again.")));
    await openPage("SPONSOR");
    type(/Amount to hold/, "25");
    expect((await screen.findByText("PayPal's button could not be loaded. Check your connection and try again.")).textContent).toBeTruthy();
  });
});

describe("the lead's buttons", () => {
  const live = (over: Record<string, unknown> = {}) => campaignView({ lead: leadPart(), ...over });
  const plan = { id: 9, kind: "CAPTURE_PLEDGES", state: "APPROVED", decision: "ALLOW" };

  it("close and collect asks the server, says what the safety check decided, and links to the plan", async () => {
    const m = await openPage("LEAD", live(), { "POST /campaigns/1/close": { body: { ...live(), plan } } });
    fireEvent.click(screen.getByRole("button", { name: /Close and collect now/ }));
    expect((await screen.findByRole("status")).textContent).toBe("The goal is held, so the money is being collected. The safety check said ALLOW.");
    expect(posts(m).map((c) => c.path)).toEqual(["/campaigns/1/close"]);
    expect(screen.getByRole("link", { name: /See the plan/ }).getAttribute("href")).toBe("/plans?id=1&plan=9");
  });

  it("shows the server's reason when closing is refused", async () => {
    await openPage("LEAD", live(), { "POST /campaigns/1/close": { status: 409, body: { error: { code: "GOAL_NOT_REACHED", message: "The goal has not been reached by holds PayPal still guarantees" } } } });
    fireEvent.click(screen.getByRole("button", { name: /Close and collect now/ }));
    expect((await screen.findByRole("alert")).textContent).toBe("The goal has not been reached by holds PayPal still guarantees");
    expect(screen.queryByTestId("plan-link")).toBeNull();
  });

  it("cancelling needs a second, explicit yes, and 'no' sends nothing", async () => {
    const m = await openPage("LEAD", live(), { "POST /campaigns/1/cancel": { body: { ...live(), plan: { ...plan, kind: "RELEASE_HOLDS" } } } });
    fireEvent.click(screen.getByRole("button", { name: /Cancel the campaign/ }));
    expect(screen.getByTestId("confirm-cancel").textContent).toContain("nobody is charged");
    fireEvent.click(screen.getByRole("button", { name: "No, keep it open" }));
    expect(screen.queryByTestId("confirm-cancel")).toBeNull();
    expect(posts(m)).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: /Cancel the campaign/ }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, cancel it" }));
    expect((await screen.findByRole("status")).textContent).toBe("Every hold is being released. Nobody is charged. The safety check said ALLOW.");
    expect(posts(m).map((c) => c.path)).toEqual(["/campaigns/1/cancel"]);
    expect(screen.queryByTestId("confirm-cancel")).toBeNull();
  });

  it("starts another round after a failed one and goes to the new campaign", async () => {
    const m = await openPage("LEAD", live({ state: "FAILED" }), { "POST /campaigns/1/relaunch": { status: 201, body: live({ id: 2, number: 2, state: "SETUP" }) } });
    fireEvent.click(screen.getByRole("button", { name: /Start another round/ }));
    await waitFor(() => expect(h.push).toHaveBeenCalledWith("/campaign?id=2"));
    expect(posts(m).map((c) => c.path)).toEqual(["/campaigns/1/relaunch"]);
  });

  it("the demo shortcut pulls the deadline to now, runs the clock once, and says what it did", async () => {
    const m = await openPage("LEAD", live(), {
      "POST /demo/campaigns/1/expire": { body: live({ seconds_left: 0 }) },
      "POST /demo/clock/tick": { body: { actions: [{ campaign_id: 1, action: "RELEASE", reason: "DEADLINE_MISSED", plan_id: 3, plan_state: "APPROVED" }] } },
    });
    fireEvent.click(screen.getByRole("button", { name: /Try the deadline early/ }));
    expect((await screen.findByRole("status")).textContent).toBe("The deadline had passed without the goal, so the clock started releasing every hold. Nobody is charged.");
    expect(posts(m).map((c) => c.path)).toEqual(["/demo/campaigns/1/expire", "/demo/clock/tick"]);
  });

  it("describes every other thing the clock can do", async () => {
    for (const [actions, words] of [
      [[], "The clock looked at the campaign and had nothing to do yet."],
      [[{ action: "CAPTURE", reason: "GOAL_REACHED" }], "The clock saw the goal was held and started collecting the money."],
      [[{ action: "SKIPPED", why: "PLAN_EXISTS" }], "The clock found a money plan already waiting; a person decides from here."],
      [[{ action: "ERROR" }], "The clock could not finish; look at the money plans."],
    ] as const) {
      cleanup();
      await openPage("LEAD", live(), { "POST /demo/campaigns/1/expire": { body: live() }, "POST /demo/clock/tick": { body: { actions } } });
      fireEvent.click(screen.getByRole("button", { name: /Try the deadline early/ }));
      expect((await screen.findByRole("status")).textContent, words).toBe(words);
    }
  });

  it("repeats the safety check's actual decision, and drops an old plan link when the next action fails", async () => {
    let n = 0;
    await openPage("LEAD", live(), {
      "POST /campaigns/1/close": () => (++n === 1
        ? { body: { ...live(), plan: { ...plan, decision: "HOLD", state: "REVIEWED" } } }
        : { status: 409, body: { error: { code: "PLAN_IN_PROGRESS", message: "Money plan 9 is already REVIEWED" } } }),
    });
    fireEvent.click(screen.getByRole("button", { name: /Close and collect now/ }));
    expect((await screen.findByRole("status")).textContent).toContain("The safety check said HOLD.");
    expect(screen.getByTestId("plan-link")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Close and collect now/ }));
    expect((await screen.findByRole("alert")).textContent).toBe("Money plan 9 is already REVIEWED");
    expect(screen.queryByTestId("plan-link")).toBeNull();
  });

  it("will not send two actions at once", async () => {
    const m = await openPage("LEAD", live(), { "POST /campaigns/1/close": () => ({ body: { ...live(), plan }, delayMs: 100 }) });
    const close = screen.getByRole("button", { name: /Close and collect now/ }) as HTMLButtonElement;
    fireEvent.click(close);
    await waitFor(() => expect(close.textContent).toContain("Working..."));
    expect(close.disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Cancel the campaign/ }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(close);
    await screen.findByRole("status");
    expect(posts(m)).toHaveLength(1);
  });
});
