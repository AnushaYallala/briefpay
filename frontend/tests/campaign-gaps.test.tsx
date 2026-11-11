import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CampaignPage from "@/app/campaign/page";
import { AuthProvider } from "@/lib/auth";
import { JOB_POLL_MS } from "@/lib/ba";
import { CAMPAIGN_REFRESH_MS, CLOCK_MS } from "@/lib/campaign";
import { formatMoney } from "@/lib/money";
import { clearToken, setToken } from "@/lib/token";
import { campaignView, lakshmi, leadPart, ledger, ledgerRow, mockFetch, project, strategistReport } from "./helpers";

// Tests added after the mutation check found weak spots in the campaign page.
const nav = vi.hoisted(() => ({ query: "id=1" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams(nav.query) }));

beforeEach(() => { clearToken(); nav.query = "id=1"; });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); clearToken(); });

const me = (role: string) => ({ user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role }] });
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const body = (c: { init: RequestInit }) => JSON.parse(String(c.init.body));
const rows = () => Array.from(document.querySelectorAll(".ag-grid-scrolling-container .ag-row"));
type Call = { method: string; path: string; init: RequestInit };
const posts = (m: { calls: Call[] }) => m.calls.filter((c) => c.method === "POST");
const count = (m: { calls: Call[] }, path: string) => m.calls.filter((c) => c.path === path).length;
const noReport = { status: 404, body: { error: { code: "NO_REPORT", message: "Run the Strategist first" } } };
const pledged = [
  ledgerRow({ seq: 1, type: "PLEDGE_AUTHORIZED", ref_type: "pledge", ref_id: "4", counterparty: "Lakshmi", created_at: "2026-11-10T11:00:00" }),
  ledgerRow({ seq: 2, type: "PLEDGE_CAPTURED", ref_type: "pledge", ref_id: "4", counterparty: "Lakshmi", created_at: "2026-11-11T09:00:00", amount_cents: 15000 }),
];
const live = (over: Record<string, unknown> = {}) => campaignView({ lead: leadPart(), ...over });
const setup = (over: Record<string, unknown> = {}) => campaignView({ state: "SETUP", opens_at: null, lead: leadPart(), ...over });

async function open(role: string | null = null, view = campaignView(), routes: Record<string, unknown> = {}) {
  if (role) setToken("tok");
  const m = mockFetch({
    ...(role ? { "GET /auth/me": { body: me(role) } } : {}),
    "GET /campaigns/1": { body: view }, "GET /projects/1/ledger": { body: ledger(pledged) }, "GET /campaigns/1/strategist": noReport, ...routes,
  } as never);
  wrapped(<CampaignPage />);
  await screen.findByTestId("title");
  return m;
}

describe("the pledge board's details", () => {
  it("shows collected amounts in the campaign's own currency and the time in words", async () => {
    await open(null, campaignView({ currency: "EUR" }));
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(rows()[0].querySelector('[col-id="amount_cents"]')!.textContent).toBe(formatMoney(15000, "EUR"));
    expect(formatMoney(15000, "EUR")).not.toBe(formatMoney(15000, "USD"));
    expect(rows()[0].querySelector('[col-id="at"]')!.textContent).toBe("Nov 11, 09:00 UTC");
  });
});

describe("the Strategist's details", () => {
  it("shows the money in the campaign's own currency", async () => {
    await open("LEAD", live({ currency: "EUR" }), { "GET /campaigns/1/strategist": { body: strategistReport() } });
    const f = await screen.findByTestId("forecast");
    expect(f.textContent).toContain(`expected ${formatMoney(15750, "EUR")} of ${formatMoney(40000, "EUR")}`);
  });

  it("hides the 'no forecast yet' note while it is being made, and clears an earlier problem when it is run again", async () => {
    let k = 0;
    await open("LEAD", live(), { "POST /campaigns/1/strategist/run": () => (k++ === 0 ? { status: 409, body: { error: { code: "X", message: "Not now" } } } : { status: 202, body: { job_id: 4 } }), "GET /jobs/4": { body: { state: "RUNNING", result: null, error: null, attempts: 1 } } });
    fireEvent.click(await screen.findByRole("button", { name: "Run the Strategist" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Not now");
    fireEvent.click(screen.getByRole("button", { name: "Run the Strategist" }));
    expect(await screen.findByText("The Strategist is working. This takes a short while.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByTestId("no-report")).toBeNull();
  });

  it("clears an earlier problem when a deadline is applied, and will not apply twice at once", async () => {
    let k = 0;
    const m = await open("LEAD", live(), {
      "GET /campaigns/1/strategist": { body: strategistReport() },
      "POST /campaigns/1/strategist/apply": () => (k++ === 0 ? { status: 409, body: { error: { code: "X", message: "Too late" } } } : { body: campaignView(), delayMs: 200 }),
    });
    const apply = await screen.findByRole("button", { name: "Apply this deadline" }) as HTMLButtonElement;
    fireEvent.click(apply);
    expect((await screen.findByRole("alert")).textContent).toBe("Too late");
    fireEvent.click(apply);
    await waitFor(() => expect(apply.textContent).toBe("Applying..."));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(apply.disabled).toBe(true);
    fireEvent.click(apply);
    await waitFor(() => expect(apply.textContent).toBe("Apply this deadline"));
    expect(posts(m)).toHaveLength(2);
  });
});

describe("the organiser panel's details", () => {
  const detail = (campaign: unknown = null) => ({ ...project({ state: "CAMPAIGN_SETUP", campaign }), delivery_days: 5, payout_release_policy: "HUMAN", created_at: "2026-11-09T10:00:00", members: [], viewer: null });

  it("starts a new campaign on 'closes as soon as the goal is reached', and asks for a deadline before bothering the server", async () => {
    nav.query = "project=1";
    setToken("tok");
    const m = mockFetch({ "GET /auth/me": { body: me("LEAD") }, "GET /projects/1": { body: detail() }, "POST /projects/1/campaigns": { status: 201, body: setup() } });
    wrapped(<CampaignPage />);
    const form = await screen.findByRole("form", { name: "Campaign terms" });
    const radios = Array.from(form.querySelectorAll('input[type="radio"]')) as HTMLInputElement[];
    expect(radios.map((r) => r.checked)).toEqual([true, false]);
    fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Choose a date and time for the deadline.");
    expect(posts(m)).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Deadline (UTC)"), { target: { value: "2026-11-12T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    await waitFor(() => expect(posts(m)).toHaveLength(1));
    expect(body(posts(m)[0]).close_policy).toBe("EARLY_ON_GOAL");
  });

  it("asks only for the campaign when both numbers are in the address", async () => {
    nav.query = "id=1&project=1";
    const m = await open(null, campaignView());
    expect(m.calls.some((c) => c.path === "/projects/1")).toBe(false);
  });

  it("keeps the setup form on screen while the project reloads, even if that reload fails", async () => {
    nav.query = "project=1";
    setToken("tok");
    let n = 0;
    mockFetch({
      "GET /auth/me": { body: me("LEAD") },
      "GET /projects/1": () => (n++ === 0 ? { body: detail() } : { status: 500, body: { error: { code: "X", message: "down" } }, delayMs: 150 }),
      "POST /projects/1/campaigns": { status: 201, body: setup() },
    });
    wrapped(<CampaignPage />);
    await screen.findByRole("form", { name: "Campaign terms" });
    fireEvent.change(screen.getByLabelText("Deadline (UTC)"), { target: { value: "2026-11-12T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 60)); });
    expect(screen.queryByText("Loading the project...")).toBeNull();
    expect(screen.getByRole("form", { name: "Campaign terms" })).toBeTruthy();
    await act(async () => { await new Promise((r) => setTimeout(r, 200)); });
    expect(screen.getByRole("form", { name: "Campaign terms" })).toBeTruthy();
    expect(screen.queryByText("down")).toBeNull();
  });

  it("clears 'Saved.' when the next attempt is refused by the form, and again when the campaign is opened", async () => {
    await open("LEAD", setup(), { "POST /projects/1/campaigns": { status: 201, body: setup() }, "POST /campaigns/1/launch": { status: 409, body: { error: { code: "X", message: "Not yet" } } } });
    fireEvent.change(screen.getByLabelText("Deadline (UTC)"), { target: { value: "2026-11-12T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    expect((await screen.findByRole("status")).textContent).toBe("Saved.");
    fireEvent.change(screen.getByLabelText("Smallest pledge (dollars, optional)"), { target: { value: "five" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    fireEvent.change(screen.getByLabelText("Smallest pledge (dollars, optional)"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    expect((await screen.findByRole("status")).textContent).toBe("Saved.");
    fireEvent.click(screen.getByRole("button", { name: "Open for pledges" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Not yet");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("does not show the opening controls once the campaign is open", async () => {
    await open("LEAD", live());
    expect(screen.queryByRole("button", { name: "Open for pledges" })).toBeNull();
    expect(screen.queryByTestId("blockers")).toBeNull();
  });
});

describe("what is shown for a campaign that ended", () => {
  it("gives the reason for any state that has one, and nothing when there is none", async () => {
    for (const state of ["FAILING", "FAILED", "CANCELLED"]) {
      cleanup();
      await open(null, campaignView({ state, fail_reason: "DEADLINE_PASSED" }));
      expect(screen.getByTestId("fail-reason").textContent, state).toBe("Why: DEADLINE_PASSED");
    }
  });
});

describe("reloading", () => {
  it("keeps the whole campaign on screen while it reloads after a change", async () => {
    let n = 0;
    await open("LEAD", setup(), {
      "GET /campaigns/1": () => ({ body: setup(), delayMs: n++ === 0 ? 0 : 250 }),
      "POST /projects/1/campaigns": { status: 201, body: setup() },
    });
    fireEvent.change(screen.getByLabelText("Deadline (UTC)"), { target: { value: "2026-11-12T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 80)); });
    expect(n).toBe(2);
    expect(screen.queryByText("Loading the campaign...")).toBeNull();
    expect(screen.getByTestId("title")).toBeTruthy();
  });

  it("reloads the pledges as well when a different person signs in", async () => {
    setToken("tok");
    let who = 0;
    const ravi = { id: 2, email: "ravi@velugu.example.com", display_name: "Ravi" };
    const m = mockFetch({
      "GET /auth/me": () => ({ body: who === 0 ? me("LEAD") : { user: ravi, memberships: [{ member_id: 2, project_id: 1, role: "SPONSOR" }] } }),
      "POST /auth/login": () => { who = 1; return { body: { token: "tok2", user: ravi } }; },
      "GET /campaigns/1": { body: campaignView() }, "GET /projects/1/ledger": { body: ledger(pledged) },
    });
    const { Switch } = await import("./switch");
    wrapped(<><CampaignPage /><Switch /></>);
    await screen.findByTestId("title");
    await waitFor(() => expect(rows()).toHaveLength(1));
    const before = count(m, "/projects/1/ledger");
    fireEvent.click(screen.getByRole("button", { name: "switch person" }));
    await waitFor(() => expect(count(m, "/projects/1/ledger")).toBe(before + 1));
  });
});

describe("sharing and reloading the board", () => {
  it("copies the link to share, says so, and does not claim it when the copy is refused", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await open(null, campaignView());
    fireEvent.click(screen.getByRole("button", { name: "Copy the link to share" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Link copied" })).toBeTruthy());
    expect(writeText).toHaveBeenCalledWith(window.location.href);
    cleanup();
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockRejectedValue(new Error("blocked")) }, configurable: true });
    await open(null, campaignView());
    fireEvent.click(screen.getByRole("button", { name: "Copy the link to share" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 40)); });
    expect(screen.queryByRole("button", { name: "Link copied" })).toBeNull();
    expect(screen.getByRole("button", { name: "Copy the link to share" })).toBeTruthy();
  });

  it("keeps the pledge board on screen while the pledges reload", async () => {
    let n = 0;
    await open(null, campaignView(), { "GET /projects/1/ledger": () => ({ body: ledger(pledged), delayMs: n++ === 0 ? 0 : 250 }) });
    await waitFor(() => expect(rows()).toHaveLength(1));
    const { default: Switch } = { default: (await import("./switch")).Switch };
    expect(Switch).toBeTruthy();
    cleanup();
    setToken("tok");
    let who = 0;
    const ravi = { id: 2, email: "ravi@velugu.example.com", display_name: "Ravi" };
    let k = 0;
    mockFetch({
      "GET /auth/me": () => ({ body: who === 0 ? me("LEAD") : { user: ravi, memberships: [{ member_id: 2, project_id: 1, role: "SPONSOR" }] } }),
      "POST /auth/login": () => { who = 1; return { body: { token: "tok2", user: ravi } }; },
      "GET /campaigns/1": { body: campaignView() },
      "GET /projects/1/ledger": () => ({ body: ledger(pledged), delayMs: k++ === 0 ? 0 : 250 }),
    });
    wrapped(<><CampaignPage /><Switch /></>);
    await screen.findByTestId("title");
    await waitFor(() => expect(rows()).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "switch person" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 80)); });
    expect(k).toBe(2);
    expect(screen.queryByText("Loading the pledges...")).toBeNull();
    expect(rows()).toHaveLength(1);
  });
});

// last on purpose: these fake the clock and spy on the interval functions
describe("timers", () => {
  it("asks about no job before one was started", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const m = await open("LEAD", live());
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS * 3); });
    expect(m.calls.some((c) => c.path.startsWith("/jobs"))).toBe(false);
  });

  it("says a failed Strategist gave no reason when the server gave none", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await open("LEAD", live(), { "POST /campaigns/1/strategist/run": { status: 202, body: { job_id: 6 } }, "GET /jobs/6": { body: { state: "FAILED", result: null, error: null, attempts: 3 } } });
    fireEvent.click(await screen.findByRole("button", { name: "Run the Strategist" }));
    await screen.findByText("The Strategist is working. This takes a short while.");
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    expect((await screen.findByRole("alert")).textContent).toBe("The Strategist could not finish. It failed.");
  });

  it("stops both of its timers when the page is left", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const set = vi.spyOn(globalThis, "setInterval");
    const clear = vi.spyOn(globalThis, "clearInterval");
    await open(null, campaignView());
    const ids = (ms: number) => set.mock.calls.map((c, i) => (c[1] === ms ? set.mock.results[i].value : undefined)).filter((v) => v !== undefined);
    await waitFor(() => expect(ids(CLOCK_MS)).toHaveLength(1));
    await waitFor(() => expect(ids(CAMPAIGN_REFRESH_MS)).toHaveLength(1));
    const [tick, news] = [ids(CLOCK_MS)[0], ids(CAMPAIGN_REFRESH_MS)[0]];
    cleanup();
    const cleared = [tick, news].map((id) => clear.mock.calls.some((c) => c[0] === id));
    set.mockRestore();
    clear.mockRestore();
    vi.useRealTimers();
    expect(cleared).toEqual([true, true]);
  });
});
