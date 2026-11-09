import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProjectPage from "@/app/project/page";
import Home from "@/app/page";
import { Header } from "@/components/Header";
import { MembersPanel } from "@/components/MembersPanel";
import { MoneyBox } from "@/components/MoneyBox";
import { Stepper } from "@/components/Stepper";
import { AuthProvider } from "@/lib/auth";
import { PROJECT_STATES } from "@/lib/states";
import { STEPS, STEP_OF, WHAT_NEXT, stepStatuses } from "@/lib/steps";
import { formatDateTime } from "@/lib/time";
import { clearToken, setToken } from "@/lib/token";
import type { Member } from "@/lib/types";
import { lakshmi, mockFetch, project } from "./helpers";

const nav = vi.hoisted(() => ({ query: "", push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: nav.push }), useSearchParams: () => new URLSearchParams(nav.query) }));

beforeEach(() => { clearToken(); nav.query = "id=1"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); clearToken(); });

const members: Member[] = [
  { id: 1, role: "LEAD", display_name: "Lakshmi", business_name: "Sea Breeze Homestay", business_type: "Homestay", email: "lakshmi@velugu.example.com", paypal_email: "secret@sandbox.example.com" },
  { id: 2, role: "SPONSOR", display_name: "Ravi", business_name: "Ravi's Fish Kitchen", business_type: "Restaurant", email: "ravi@velugu.example.com" },
  { id: 4, role: "FREELANCER", display_name: "Arjun", business_name: null, business_type: null, email: "arjun@velugu.example.com", paypal_email: "arjun-sandbox@velugu.example.com" },
];
const detail = (over: Record<string, unknown> = {}) => ({ ...project(), delivery_days: 5, payout_release_policy: "HUMAN", created_at: "2026-11-09T10:00:00", members, viewer: null, ...over });
const money = (over: Record<string, unknown> = {}) => ({
  project_id: 1, pool_balance_cents: 0, holds: { count: 2, total_cents: 25000, note: "Holds are not money: nothing is charged unless the goal is reached." },
  next_honor_deadline: "2026-11-12T18:30:00+00:00", campaign: null, contract_amount_cents: 40000, open_plans: [], unclaimed_payouts: 0, alerts: [], ...over });
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const me = { user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role: "LEAD" }] };

describe("stepper logic", () => {
  it("covers every project state and every step is named", () => {
    expect(Object.keys(STEP_OF).sort()).toEqual(Object.keys(PROJECT_STATES).sort());
    expect(Object.keys(WHAT_NEXT).sort()).toEqual(Object.keys(PROJECT_STATES).sort());
    expect([...STEPS]).toEqual(["Requirements", "Brief", "Contract", "Campaign", "Build", "Verify", "Payout", "Ledger"]);
  });

  it.each([
    ["DRAFT", 0], ["REQUIREMENTS", 0], ["BRD_REVIEW", 1], ["CONTRACTING", 2], ["CAMPAIGN_SETUP", 3], ["PLEDGING", 3], ["CAMPAIGN_FAILED", 3], ["IN_PROGRESS", 4],
    ["VERIFYING", 5], ["PAYOUT_READY", 6], ["PAYOUT_PENDING", 6], ["PAYOUT_FAILED", 6], ["PAID", 7],
  ])("%s is step %i: earlier steps done, later ones upcoming", (state, at) => {
    const s = stepStatuses(state);
    expect(s.filter((x) => x === "current").length).toBe(1);
    s.forEach((x, i) => expect(x).toBe(i < at ? "done" : i === at ? "current" : "upcoming"));
  });

  it.each(["REFUNDING", "CANCELLED", "SOMETHING_ELSE"])("%s is off the normal path: nothing is current", (state) => {
    expect(stepStatuses(state).every((x) => x === "upcoming")).toBe(true);
  });

  it("a missed goal keeps the campaign step current (the organiser can try again)", () => expect(stepStatuses("CAMPAIGN_FAILED")[3]).toBe("current"));
  it("every explanation is a real sentence, and failed rounds say nobody was charged", () => {
    Object.values(WHAT_NEXT).forEach((t) => expect(t.length).toBeGreaterThan(30));
    expect(WHAT_NEXT.CAMPAIGN_FAILED).toContain("nobody was charged");
    expect(WHAT_NEXT.PLEDGING).toContain("only a hold");
  });
});

describe("dates", () => {
  it("are shown in UTC with the label", () => expect(formatDateTime("2026-11-12T18:30:00+00:00")).toBe("Nov 12, 18:30 UTC"));
  it("convert other offsets to UTC", () => expect(formatDateTime("2026-11-12T18:30:00+05:30")).toBe("Nov 12, 13:00 UTC"));
  it("say so for nothing or nonsense", () => {
    expect(formatDateTime(null)).toBe("none");
    expect(formatDateTime(undefined)).toBe("none");
    expect(formatDateTime("")).toBe("none");
    expect(formatDateTime("not a date")).toBe("unknown");
  });
});

describe("stepper component", () => {
  it("marks done, current and upcoming steps", () => {
    render(<Stepper state="VERIFYING" />);
    const items = screen.getAllByRole("listitem");
    expect(items.map((li) => li.getAttribute("data-status"))).toEqual(["done", "done", "done", "done", "done", "current", "upcoming", "upcoming"]);
    expect(items.filter((li) => li.getAttribute("aria-current") === "step").length).toBe(1);
    expect(items[0].textContent).toContain("✓");
    expect(items[5].textContent).toBe("6Verify");
  });
  it("is muted when the project left the normal path", () => {
    render(<Stepper state="CANCELLED" />);
    expect(screen.getAllByRole("listitem").every((li) => li.getAttribute("data-status") === "upcoming" && li.className.includes("text-gray-400"))).toBe(true);
  });
});

describe("people panel", () => {
  it("shows names, businesses and roles, marks the viewer, and never shows an address", () => {
    const { container } = render(<MembersPanel members={members} viewerId={2} />);
    expect(screen.getByText("Lakshmi")).toBeTruthy();
    expect(screen.getByText("Sea Breeze Homestay")).toBeTruthy();
    expect(screen.getByText("Organiser")).toBeTruthy();
    expect(screen.getByText("Builder")).toBeTruthy();
    expect(screen.getByText("(you)").parentElement?.textContent).toContain("Ravi");
    expect(container.textContent).not.toMatch(/@|sandbox|secret/);
  });
});

describe("money box", () => {
  it("shows the pool, the holds as not money, the deadline, the price", async () => {
    mockFetch({ "GET /projects/1/money": { body: money({ pool_balance_cents: 40000 }) } });
    render(<MoneyBox projectId={1} />);
    expect((await screen.findByTestId("pool")).textContent).toBe("$400.00");
    expect(screen.getByTestId("holds").textContent).toBe("$250.00 in 2 holds");
    expect(screen.getByText(/Holds are not money/)).toBeTruthy();
    expect(screen.getByText(/Holds must be used or released by Nov 12, 18:30 UTC/)).toBeTruthy();
    expect(screen.getByText(/Contract price:/).parentElement?.textContent).toContain("$400.00");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says 'hold' for one and 'No holds' for none, and hides the deadline when there is none", async () => {
    mockFetch({ "GET /projects/1/money": { body: money({ holds: { count: 1, total_cents: 500, note: "n" }, next_honor_deadline: null, contract_amount_cents: null }) } });
    render(<MoneyBox projectId={1} />);
    expect((await screen.findByTestId("holds")).textContent).toBe("$5.00 in 1 hold");
    expect(screen.queryByText(/Holds must be used/)).toBeNull();
    expect(screen.queryByText(/Contract price/)).toBeNull();
    cleanup();
    mockFetch({ "GET /projects/1/money": { body: money({ holds: { count: 0, total_cents: 0, note: "n" } }) } });
    render(<MoneyBox projectId={1} />);
    expect((await screen.findByTestId("holds")).textContent).toBe("No holds");
  });

  it("lists plans in words, warns about an unclaimed payment and about differences reported by PayPal", async () => {
    mockFetch({ "GET /projects/1/money": { body: money({ open_plans: [{ id: 3, kind: "FREELANCER_PAYOUT", state: "REVIEWED" }, { id: 4, kind: "REFUND_CAPTURED", state: "EXECUTING" }],
      unclaimed_payouts: 1, alerts: [{ seq: 9, created_at: "x", meta: {} }] }) } });
    render(<MoneyBox projectId={1} />);
    expect(await screen.findByText("Pay the builder: reviewed")).toBeTruthy();
    expect(screen.getByText("Refund the pledgers: executing")).toBeTruthy();
    expect(screen.getByText(/waiting for the builder to claim it at PayPal/)).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe("1 item need attention: PayPal reported something different from our records.");
  });

  it("pluralises alerts", async () => {
    mockFetch({ "GET /projects/1/money": { body: money({ alerts: [{ seq: 1, created_at: "x", meta: {} }, { seq: 2, created_at: "y", meta: {} }] }) } });
    render(<MoneyBox projectId={1} />);
    expect((await screen.findByRole("alert")).textContent).toContain("2 items need attention");
  });

  it("is honest when nothing has happened", async () => {
    mockFetch({ "GET /projects/1/money": { body: money({ holds: { count: 0, total_cents: 0, note: "n" }, next_honor_deadline: null }) } });
    render(<MoneyBox projectId={1} />);
    expect(await screen.findByText("No money has moved yet")).toBeTruthy();
  });

  it("shows errors with a retry and refreshes on request", async () => {
    let n = 0;
    const { calls } = mockFetch({ "GET /projects/1/money": () => (++n === 1 ? { status: 403, body: { error: { code: "NOT_A_MEMBER", message: "You are not a member of this project", details: {} } } } : { body: money({ pool_balance_cents: 100 }) }) });
    render(<MoneyBox projectId={1} />);
    expect((await screen.findByRole("alert")).textContent).toContain("You are not a member");
    fireEvent.click(screen.getByText("Try again"));
    expect((await screen.findByTestId("pool")).textContent).toBe("$1.00");
    fireEvent.click(screen.getByText("Refresh"));
    await waitFor(() => expect(calls.length).toBe(3));
  });

  it("uses the project's currency", async () => {
    mockFetch({ "GET /projects/1/money": { body: money({ pool_balance_cents: 1000 }) } });
    render(<MoneyBox projectId={1} currency="EUR" />);
    expect((await screen.findByTestId("pool")).textContent).toBe("EUR 10.00");
  });
});

describe("project page", () => {
  it("shows a visitor the project, where it stands and what happens next, without asking for money", async () => {
    const { calls } = mockFetch({ "GET /projects/1": { body: detail() } });
    wrapped(<ProjectPage />);
    expect(await screen.findByRole("heading", { name: "Velugu Cove tourism website" })).toBeTruthy();
    expect(screen.getByText("Collecting pledges", { selector: "span" })).toBeTruthy();
    expect(screen.getByTestId("what-next").textContent).toContain("only a hold");
    expect(screen.getAllByRole("listitem").filter((li) => li.getAttribute("aria-current") === "step")[0].textContent).toContain("Campaign");
    expect(screen.getByText(/Pledged \$150\.00 of \$400\.00 by 1 person/)).toBeTruthy();
    expect(screen.getByText("Approved by a person")).toBeTruthy();
    expect(screen.getByText("5 days")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe("/login");
    expect(screen.queryByTestId("pool")).toBeNull();
    expect(calls.map((c) => c.path)).toEqual(["/projects/1"]);                         // no money request for a visitor
    expect(document.body.textContent).not.toMatch(/@/);
  });

  it("shows a member the money box", async () => {
    setToken("tok");
    const { calls } = mockFetch({
      "GET /auth/me": { body: me },
      "GET /projects/1": { body: detail({ viewer: { role: "LEAD", member_id: 1 } }) },
      "GET /projects/1/money": { body: money({ pool_balance_cents: 40000 }) },
    });
    wrapped(<ProjectPage />);
    expect((await screen.findByTestId("pool")).textContent).toBe("$400.00");
    expect(screen.getByText("(you)")).toBeTruthy();
    expect(calls.map((c) => c.path)).toEqual(["/auth/me", "/projects/1", "/projects/1/money"]);   // waited for the sign-in check first
    expect((calls[1].init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("tells a signed-in outsider that the money box is for members", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1": { body: detail({ viewer: null }) } });
    wrapped(<ProjectPage />);
    expect(await screen.findByText(/Only the people on this project can see its money box/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Sign in" })).toBeNull();
  });

  it.each(["", "id=", "id=abc", "id=12x", "id=-1", "id=1.5", "id=9999999999", "other=1"])("refuses a bad project link (%s) without calling the API", (q) => {
    nav.query = q;
    const { fn } = mockFetch({});
    wrapped(<ProjectPage />);
    expect(screen.getByText("No project selected")).toBeTruthy();
    expect(screen.getByRole("link", { name: "the project list" }).getAttribute("href")).toBe("/");
    expect(fn).not.toHaveBeenCalled();
  });

  it("explains a project that does not exist, and can retry", async () => {
    nav.query = "id=77";
    mockFetch({ "GET /projects/77": { status: 404, body: { error: { code: "PROJECT_NOT_FOUND", message: "No such project", details: {} } } } });
    wrapped(<ProjectPage />);
    expect((await screen.findByRole("alert")).textContent).toContain("No such project");
    expect(screen.getByText("Try again")).toBeTruthy();
  });

  it("describes a cancelled project with a muted stepper and the refund explanation", async () => {
    mockFetch({ "GET /projects/1": { body: detail({ state: "CANCELLED", campaign: null }) } });
    wrapped(<ProjectPage />);
    expect((await screen.findByTestId("what-next")).textContent).toContain("every pledger was refunded");
    const steps = within(screen.getByRole("navigation", { name: "Project progress" })).getAllByRole("listitem");
    expect(steps.length).toBe(8);
    expect(steps.every((li) => li.getAttribute("data-status") === "upcoming")).toBe(true);
    expect(screen.getByText("No campaign yet")).toBeTruthy();
  });

  it("shows the other payout policy in words", async () => {
    mockFetch({ "GET /projects/1": { body: detail({ payout_release_policy: "AUTO_ON_GUARDIAN_ALLOW", delivery_days: null }) } });
    wrapped(<ProjectPage />);
    expect(await screen.findByText(/Released automatically when the safety checks allow/)).toBeTruthy();
    expect(screen.getByText("not set")).toBeTruthy();
  });

  it("reloads with the right view when the demo person changes", async () => {
    const ravi = { id: 2, email: "ravi@velugu.example.com", display_name: "Ravi" };
    const { calls } = mockFetch({
      "POST /auth/login": { body: { token: "ravi-token", user: ravi } },
      "GET /auth/me": { body: { user: ravi, memberships: [{ member_id: 2, project_id: 1, role: "SPONSOR" }] } },
      "GET /projects/1": (init) => ({ body: detail((init.headers as Record<string, string>).Authorization ? { viewer: { role: "SPONSOR", member_id: 2 } } : {}) }),
      "GET /projects/1/money": { body: money({ pool_balance_cents: 100 }) },
    });
    wrapped(<><Header /><ProjectPage /></>);
    await screen.findByRole("link", { name: "Sign in" }, { timeout: 2000 }).catch(() => null);
    expect(screen.queryByTestId("pool")).toBeNull();
    fireEvent.change(await screen.findByLabelText("Switch demo person"), { target: { value: "ravi" } });
    expect((await screen.findByTestId("pool")).textContent).toBe("$1.00");
    const reads = calls.filter((c) => c.path === "/projects/1");
    expect(reads.length).toBe(2);
    expect((reads[1].init.headers as Record<string, string>).Authorization).toBe("Bearer ravi-token");
  });
});

describe("home page links", () => {
  it("each project title opens its page", async () => {
    mockFetch({ "GET /projects": { body: { projects: [project(), project({ id: 2, title: "Second" })] } } });
    render(<Home />);
    const link = await screen.findByRole("link", { name: "Velugu Cove tourism website" });
    expect(link.getAttribute("href")).toBe("/project?id=1");
    expect(screen.getByRole("link", { name: "Second" }).getAttribute("href")).toBe("/project?id=2");
  });
});

describe("gaps found by the mutation check", () => {
  it("never says 'no money has moved' while something needs attention", async () => {
    mockFetch({ "GET /projects/1/money": { body: money({ holds: { count: 0, total_cents: 0, note: "n" }, next_honor_deadline: null, alerts: [{ seq: 3, created_at: "x", meta: {} }] }) } });
    render(<MoneyBox projectId={1} />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("No money has moved yet")).toBeNull();
  });

  it("does not call it empty while a plan is in progress either", async () => {
    mockFetch({ "GET /projects/1/money": { body: money({ holds: { count: 0, total_cents: 0, note: "n" }, next_honor_deadline: null, open_plans: [{ id: 1, kind: "RELEASE_HOLDS", state: "EXECUTING" }] }) } });
    render(<MoneyBox projectId={1} />);
    expect(await screen.findByText("Release the holds: executing")).toBeTruthy();
    expect(screen.queryByText("No money has moved yet")).toBeNull();
  });

  it("colours the role badges so the organiser and the builder stand out", () => {
    render(<MembersPanel members={members} viewerId={null} />);
    expect(screen.getByText("Organiser").className).toContain("bg-sea-100");
    expect(screen.getByText("Builder").className).toContain("bg-blue-100");
    expect(screen.getByText("Sponsor").className).toContain("bg-gray-100");
  });

  it("the page shows the money in the project's own currency", async () => {
    setToken("tok");
    mockFetch({
      "GET /auth/me": { body: me },
      "GET /projects/1": { body: detail({ currency: "EUR", viewer: { role: "LEAD", member_id: 1 } }) },
      "GET /projects/1/money": { body: money({ pool_balance_cents: 400 }) },
    });
    wrapped(<ProjectPage />);
    expect((await screen.findByTestId("pool")).textContent).toBe("EUR 4.00");
  });
});

describe("timestamps without an offset", () => {
  it.each([
    ["2026-11-10T12:00:00", "Nov 10, 12:00 UTC"], ["2026-11-10T12:00:00.123456", "Nov 10, 12:00 UTC"], ["2026-11-10T12:00:00Z", "Nov 10, 12:00 UTC"],
    ["2026-11-10T12:00:00+00:00", "Nov 10, 12:00 UTC"], ["2026-11-10T17:30:00+05:30", "Nov 10, 12:00 UTC"], ["2026-11-10T07:00:00-0500", "Nov 10, 12:00 UTC"],
    ["2026-11-10T12:00:00z", "Nov 10, 12:00 UTC"], ["  2026-11-10T12:00:00  ", "Nov 10, 12:00 UTC"],
  ])("%s is read as UTC", (iso, text) => expect(formatDateTime(iso)).toBe(text));
});

describe("ledger link", () => {
  it("the project page points to the public ledger", async () => {
    mockFetch({ "GET /projects/1": { body: detail() } });
    wrapped(<ProjectPage />);
    const link = await screen.findByRole("link", { name: "Open the public ledger" });
    expect(link.getAttribute("href")).toBe("/ledger?id=1");
  });
});
