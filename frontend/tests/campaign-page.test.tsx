import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CampaignPage from "@/app/campaign/page";
import { AuthProvider } from "@/lib/auth";
import { JOB_POLL_MS } from "@/lib/ba";
import { CAMPAIGN_REFRESH_MS, CLOCK_MS } from "@/lib/campaign";
import { clearToken, setToken } from "@/lib/token";
import { campaignView, lakshmi, leadPart, ledger, ledgerRow, mockFetch, project, strategistReport } from "./helpers";

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

const me = (role: string) => ({ user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role }] });
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const body = (c: { init: RequestInit }) => JSON.parse(String(c.init.body));
const rows = () => Array.from(document.querySelectorAll(".ag-grid-scrolling-container .ag-row"));
const posts = (m: { calls: { method: string; path: string; init: RequestInit }[] }) => m.calls.filter((c) => c.method === "POST");
const noReport = { status: 404, body: { error: { code: "NO_REPORT", message: "Run the Strategist first" } } };
const pledgeRows = [
  ledgerRow({ seq: 1, type: "PLEDGE_AUTHORIZED", ref_type: "pledge", ref_id: "4", counterparty: "Lakshmi", created_at: "2026-11-10T11:00:00" }),
  ledgerRow({ seq: 2, type: "PLEDGE_AUTHORIZED", ref_type: "pledge", ref_id: "5", counterparty: "Ravi", created_at: "2026-11-10T12:00:00" }),
  ledgerRow({ seq: 3, type: "PLEDGE_CAPTURED", ref_type: "pledge", ref_id: "4", counterparty: "Lakshmi", created_at: "2026-11-11T09:00:00", amount_cents: 15000, bucket: "POOL" }),
];

async function open(role: string | null = null, view = campaignView(), routes: Record<string, unknown> = {}) {
  if (role) setToken("tok");
  const m = mockFetch({
    ...(role ? { "GET /auth/me": { body: me(role) } } : {}),
    "GET /campaigns/1": { body: view }, "GET /projects/1/ledger": { body: ledger(pledgeRows) }, "GET /campaigns/1/strategist": noReport, ...routes,
  } as never);
  wrapped(<CampaignPage />);
  await screen.findByTestId("title");
  return m;
}

describe("the public campaign page", () => {
  it("shows the project, round and state, the progress, and the held-not-charged promise", async () => {
    await open();
    expect(screen.getByTestId("title").textContent).toBe("Velugu Cove tourism website");
    expect(screen.getByText("Round 1: Open for pledges")).toBeTruthy();
    expect(screen.getByText(/Pledged \$150\.00 of \$400\.00 by 1 person/)).toBeTruthy();
    expect(screen.getByTestId("money-note").textContent).toBe("Held, not charged. Nothing is charged unless the goal is reached. A pledge is only a hold on your PayPal account.");
    expect(screen.getByText("Back to the project").getAttribute("href")).toBe("/project?id=1");
    const stepBar = screen.getByRole("navigation", { name: "Project lifecycle progress" });
    expect(within(stepBar).getByRole("link", { name: /Requirements/i }).getAttribute("href")).toBe("/ba?id=1");
    expect(within(stepBar).getByRole("link", { name: /Brief/i }).getAttribute("href")).toBe("/brd?id=1");
    expect(within(stepBar).getByRole("link", { name: /Campaign/i }).getAttribute("href")).toBe("/campaign?project=1");
  });

  it("lists the goal, what is still needed, the smallest pledge, the deadline and how it closes", async () => {
    await open(null, campaignView({ suggested_share_cents: 10000 }));
    const text = document.querySelector("dl")!.textContent!;
    expect(text).toContain("Goal$400.00");
    expect(screen.getByTestId("need").textContent).toBe("$250.00");
    expect(text).toContain("Smallest pledge$5.00");
    expect(text).toContain("Suggested share$100.00");
    expect(text).toContain("DeadlineNov 12, 10:00 UTC");
    expect(screen.getByText("Closes as soon as the goal is reached, so the money is collected promptly.")).toBeTruthy();
  });

  it("leaves out a suggested share that was not set, and explains the other closing policy", async () => {
    await open(null, campaignView({ close_policy: "AT_DEADLINE" }));
    expect(document.querySelector("dl")!.textContent).not.toContain("Suggested share");
    expect(screen.getByText("Stays open until the deadline, even after the goal is reached.")).toBeTruthy();
  });

  it("asks a visitor who has not signed in to sign in, and says a campaign still being set up is not open yet", async () => {
    await open();
    expect(screen.getByTestId("pledge-unavailable").textContent).toContain("Sign in to hold an amount");
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe("/login");
    expect(screen.queryByTestId("pledge-form")).toBeNull();
    cleanup();
    await open(null, campaignView({ state: "SETUP", opens_at: null }));
    expect(screen.getByTestId("pledge-unavailable").textContent).toBe("This campaign has not opened yet.");
    expect(screen.getByTestId("money-note").textContent).toContain("This campaign has not opened yet. Nothing can be pledged.");
  });

  it("shows the right words for every finished state, and no pledge box, still-needed or time-left lines", async () => {
    const cases: [string, string, string][] = [
      ["CAPTURING", "Collecting the pledged money", "The goal was reached. The held money is being collected now."],
      ["CAPTURED", "Funded", "Funded. The pledged money has been collected."],
      ["FAILING", "Releasing holds", "The goal was missed. Every hold is being released: nobody pays."],
      ["FAILED", "Goal missed: holds released", "The goal was missed. Every hold was released: nobody was charged."],
      ["CANCELLED", "Cancelled", "This campaign was cancelled. Every hold is released: nobody pays."],
    ];
    for (const [state, label, note] of cases) {
      cleanup();
      await open(null, campaignView({ state, held_not_charged: state !== "CAPTURED" }));
      expect(screen.getByText(`Round 1: ${label}`), state).toBeTruthy();
      expect(screen.getByTestId("money-note").textContent, state).toContain(note);
      expect(screen.queryByRole("region", { name: "Pledge" }), state).toBeNull();
      expect(screen.queryByTestId("need"), state).toBeNull();
      expect(screen.queryByTestId("countdown"), state).toBeNull();
    }
  });

  it("does not claim 'held, not charged' once the money is collected", async () => {
    await open(null, campaignView({ state: "CAPTURED", held_not_charged: false }));
    expect(screen.getByTestId("money-note").textContent).toBe("Funded. The pledged money has been collected.");
  });

  it("gives the reason a goal was missed, and when the goal was reached", async () => {
    await open(null, campaignView({ state: "FAILED", fail_reason: "DEADLINE_PASSED" }));
    expect(screen.getByTestId("fail-reason").textContent).toBe("Why: DEADLINE_PASSED");
    cleanup();
    await open(null, campaignView({ state: "FAILED", fail_reason: null }));
    expect(screen.queryByTestId("fail-reason")).toBeNull();
    cleanup();
    await open(null, campaignView({ state: "CAPTURING", goal_reached_at: "2026-11-11T08:00:00+00:00" }));
    expect(document.querySelector("dl")!.textContent).toContain("Goal reachedNov 11, 08:00 UTC");
    cleanup();
    await open(null, campaignView({ state: "CAPTURING" }));
    expect(document.querySelector("dl")!.textContent).not.toContain("Goal reached");
  });

  it("asks which campaign when the address has no valid number", async () => {
    for (const q of ["", "id=abc", "id=-1", "id=1234567890", "project=x"]) {
      nav.query = q;
      const { unmount } = wrapped(<CampaignPage />);
      expect(await screen.findByText("No campaign selected"), q).toBeTruthy();
      unmount();
    }
  });

  it("shows the server's reason when the campaign cannot be loaded", async () => {
    mockFetch({ "GET /campaigns/1": { status: 404, body: { error: { code: "CAMPAIGN_NOT_FOUND", message: "No such campaign" } } } });
    wrapped(<CampaignPage />);
    expect(await screen.findByText("No such campaign")).toBeTruthy();
  });

  it("waits for the sign-in check before showing anything", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me("LEAD"), delayMs: 100 }, "GET /campaigns/1": { body: campaignView({ lead: leadPart() }) }, "GET /projects/1/ledger": { body: ledger([]) }, "GET /campaigns/1/strategist": noReport });
    wrapped(<CampaignPage />);
    expect(screen.getByText("Checking who you are...")).toBeTruthy();
    await screen.findByTestId("title");
    expect(screen.getByRole("region", { name: "Organiser" })).toBeTruthy();
  });

  it("reloads when a different person signs in", async () => {
    setToken("tok");
    let who = 0;
    const ravi = { id: 2, email: "ravi@velugu.example.com", display_name: "Ravi" };
    const m = mockFetch({
      "GET /auth/me": () => ({ body: who === 0 ? me("LEAD") : { user: ravi, memberships: [{ member_id: 2, project_id: 1, role: "SPONSOR" }] } }),
      "POST /auth/login": () => { who = 1; return { body: { token: "tok2", user: ravi } }; },
      "GET /campaigns/1": { body: campaignView() }, "GET /projects/1/ledger": { body: ledger([]) },
    });
    const { Switch } = await import("./switch");
    wrapped(<><CampaignPage /><Switch /></>);
    await screen.findByTestId("title");
    const n = () => m.calls.filter((c) => c.path === "/campaigns/1").length;
    const before = n();
    fireEvent.click(screen.getByRole("button", { name: "switch person" }));
    await waitFor(() => expect(n()).toBe(before + 1));
  });
});

describe("the pledge board", () => {
  it("shows who pledged and what became of each pledge, with the amount only when collected", async () => {
    await open();
    await waitFor(() => expect(rows()).toHaveLength(2));
    const text = rows().map((r) => r.textContent ?? "");
    expect(text[0]).toContain("Lakshmi");
    expect(text[0]).toContain("Collected");
    expect(text[0]).toContain("$150.00");
    expect(text[1]).toContain("Ravi");
    expect(text[1]).toContain("Held");
    expect(text[1]).toContain("held");
    expect(rows()[0].querySelector('[col-id="status"] span')!.className).toContain("bg-green-100");
    expect(rows()[1].querySelector('[col-id="status"] span')!.className).toContain("bg-sea-100");
    expect(rows().map((r) => r.getAttribute("row-id"))).toEqual(["4", "5"]);
    expect(screen.getByText(/A hold shows no amount until the money is collected/)).toBeTruthy();
  });

  it("says pledges will appear once the campaign opens, and does not ask for the ledger before then", async () => {
    const m = await open(null, campaignView({ state: "SETUP", opens_at: null }));
    expect(screen.getByText("Pledges will appear here once the campaign opens.")).toBeTruthy();
    expect(m.calls.some((c) => c.path.includes("/ledger"))).toBe(false);
  });

  it("shows the board empty with its own words when nobody has pledged", async () => {
    await open(null, campaignView(), { "GET /projects/1/ledger": { body: ledger([]) } });
    await waitFor(() => expect(document.querySelector('[data-testid="pledge-board"]')).not.toBeNull());
    expect(rows()).toHaveLength(0);
    expect(document.body.textContent).toContain("No pledges yet");
  });

  it("shows a loading note while the pledges load, and an alert when they cannot", async () => {
    await open(null, campaignView(), { "GET /projects/1/ledger": { body: ledger(pledgeRows), delayMs: 300 } });
    expect(screen.getByText("Loading the pledges...")).toBeTruthy();
    await waitFor(() => expect(rows()).toHaveLength(2));
    cleanup();
    await open(null, campaignView(), { "GET /projects/1/ledger": { status: 500, body: { error: { code: "X", message: "down" } } } });
    expect(await screen.findByText(/Could not load the pledges just now \(down\)/)).toBeTruthy();
  });

  it("pins and orders nothing it should not: only pledges since the campaign opened appear", async () => {
    const old = ledgerRow({ seq: 9, type: "PLEDGE_AUTHORIZED", ref_type: "pledge", ref_id: "1", counterparty: "Earlier round", created_at: "2026-11-01T09:00:00" });
    await open(null, campaignView(), { "GET /projects/1/ledger": { body: ledger([old, ...pledgeRows]) } });
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(document.querySelector('[data-testid="pledge-board"]')!.textContent).not.toContain("Earlier round");
  });
});

describe("for the organiser: setting up and opening", () => {
  const setup = (over: Record<string, unknown> = {}, lead: Record<string, unknown> = {}) => campaignView({ state: "SETUP", opens_at: null, lead: leadPart(lead), ...over });

  it("shows the organiser panel only to the lead", async () => {
    await open("LEAD", setup());
    expect(screen.getByRole("region", { name: "Organiser" })).toBeTruthy();
    for (const role of ["SPONSOR", "SUPPORTER", "FREELANCER"]) {
      cleanup();
      await open(role, campaignView({ state: "SETUP", opens_at: null }));
      expect(screen.queryByRole("region", { name: "Organiser" }), role).toBeNull();
      expect(screen.queryByRole("region", { name: "Strategist" }), role).toBeNull();
    }
    cleanup();
    await open(null, campaignView({ state: "SETUP", opens_at: null }));
    expect(screen.queryByRole("region", { name: "Organiser" })).toBeNull();
  });

  it("fills the form from the saved terms, and shows the allowed window and why", async () => {
    await open("LEAD", setup({ deadline_at: "2026-11-12T10:30:00+00:00", min_pledge_cents: 500, suggested_share_cents: 12500, close_policy: "AT_DEADLINE" }));
    const form = screen.getByRole("form", { name: "Campaign terms" });
    expect((within(form).getByLabelText("Deadline (UTC)") as HTMLInputElement).value).toBe("2026-11-12T10:30");
    expect((within(form).getByLabelText("Smallest pledge (dollars, optional)") as HTMLInputElement).value).toBe("5.00");
    expect((within(form).getByLabelText("Suggested share (dollars, optional)") as HTMLInputElement).value).toBe("125.00");
    const radios = within(form).getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((r) => r.checked)).toEqual([false, true]);
    expect(form.textContent).toContain("The goal is the price in the signed contract: $400.00");
    expect(screen.getByTestId("window").textContent).toContain("between Nov 10, 11:00 UTC and Nov 13, 08:00 UTC");
    expect(screen.getByTestId("window").textContent).toContain("three days");
  });

  it("leaves the suggested share blank when none was set", async () => {
    await open("LEAD", setup());
    expect((screen.getByLabelText("Suggested share (dollars, optional)") as HTMLInputElement).value).toBe("");
  });

  it("saves the terms as typed: the deadline as a UTC moment, amounts in cents, blank amounts left out", async () => {
    const m = await open("LEAD", setup(), { "POST /projects/1/campaigns": { status: 201, body: setup() } });
    fireEvent.change(screen.getByLabelText("Deadline (UTC)"), { target: { value: "2026-11-12T14:30" } });
    fireEvent.click(screen.getAllByRole("radio")[1]);
    fireEvent.change(screen.getByLabelText("Smallest pledge (dollars, optional)"), { target: { value: "7.50" } });
    fireEvent.change(screen.getByLabelText("Suggested share (dollars, optional)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    expect((await screen.findByRole("status")).textContent).toBe("Saved.");
    expect(posts(m)[0].path).toBe("/projects/1/campaigns");
    expect(body(posts(m)[0])).toEqual({ deadline_at: "2026-11-12T14:30:00.000Z", close_policy: "AT_DEADLINE", min_pledge_cents: 750 });
  });

  it("checks the deadline against the window and the amounts before asking the server", async () => {
    const m = await open("LEAD", setup());
    const save = () => fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    fireEvent.change(screen.getByLabelText("Deadline (UTC)"), { target: { value: "2026-11-10T10:00" } });
    save();
    expect((await screen.findByRole("alert")).textContent).toContain("too soon");
    fireEvent.change(screen.getByLabelText("Deadline (UTC)"), { target: { value: "2026-11-14T10:00" } });
    save();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("too late"));
    fireEvent.change(screen.getByLabelText("Deadline (UTC)"), { target: { value: "" } });
    save();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Choose a date and time for the deadline."));
    fireEvent.change(screen.getByLabelText("Deadline (UTC)"), { target: { value: "2026-11-12T10:00" } });
    fireEvent.change(screen.getByLabelText("Smallest pledge (dollars, optional)"), { target: { value: "five" } });
    save();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Amounts are in dollars, for example 5 or 12.50."));
    fireEvent.change(screen.getByLabelText("Smallest pledge (dollars, optional)"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Suggested share (dollars, optional)"), { target: { value: "-1" } });
    save();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Amounts are in dollars, for example 5 or 12.50."));
    expect(posts(m)).toHaveLength(0);
  });

  it("shows the server's reason when saving is refused, and clears it on the next try", async () => {
    let k = 0;
    await open("LEAD", setup(), { "POST /projects/1/campaigns": () => (k++ === 0 ? { status: 422, body: { error: { code: "BAD_TERMS", message: "The smallest pledge is too big" } } } : { status: 201, body: setup() }) });
    fireEvent.change(screen.getByLabelText("Deadline (UTC)"), { target: { value: "2026-11-12T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The smallest pledge is too big");
    fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect((await screen.findByRole("status")).textContent).toBe("Saved.");
  });

  it("lists what blocks opening, and keeps the button off until nothing does", async () => {
    await open("LEAD", setup({}, { launch_blockers: ["The contract is not signed yet."], can_launch: false }));
    expect(screen.getByTestId("blockers").textContent).toContain("The contract is not signed yet.");
    expect((screen.getByRole("button", { name: "Open for pledges" }) as HTMLButtonElement).disabled).toBe(true);
    cleanup();
    await open("LEAD", setup());
    expect(screen.queryByTestId("blockers")).toBeNull();
    expect((screen.getByRole("button", { name: "Open for pledges" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("opens the campaign, reloads, and will not do it twice at once", async () => {
    let state = "SETUP";
    const m = await open("LEAD", setup(), {
      "GET /campaigns/1": () => ({ body: state === "SETUP" ? setup() : campaignView({ lead: leadPart() }) }),
      "POST /campaigns/1/launch": () => { state = "OPEN"; return { body: campaignView(), delayMs: 150 }; },
    });
    const go = screen.getByRole("button", { name: "Open for pledges" }) as HTMLButtonElement;
    fireEvent.click(go);
    await waitFor(() => expect(go.textContent).toBe("Opening..."));
    expect(go.disabled).toBe(true);
    fireEvent.click(go);
    await screen.findByText("Round 1: Open for pledges");
    expect(posts(m).filter((c) => c.path === "/campaigns/1/launch")).toHaveLength(1);
    expect(screen.queryByRole("form", { name: "Campaign terms" })).toBeNull();
  });

  it("shows the server's reason when opening is refused", async () => {
    await open("LEAD", setup(), { "POST /campaigns/1/launch": { status: 409, body: { error: { code: "CONTRACT_NOT_SIGNED", message: "The freelancer must sign first" } } } });
    fireEvent.click(screen.getByRole("button", { name: "Open for pledges" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The freelancer must sign first");
  });

  it("offers the lead the buttons that make sense for an open campaign, and keeps the others off", async () => {
    await open("LEAD", campaignView({ lead: leadPart({ earliest_honor_until: "2026-11-13T09:00:00+00:00" }) }));
    const on = (n: string) => !(screen.getByRole("button", { name: new RegExp(n) }) as HTMLButtonElement).disabled;
    expect([on("Close and collect now"), on("Cancel the campaign"), on("Start another round"), on("Try the deadline early")]).toEqual([true, true, false, true]);
    expect(screen.queryByTestId("not-built")).toBeNull();
    expect(screen.getByTestId("honor").textContent).toBe("The earliest hold runs out Nov 13, 09:00 UTC.");
    expect(screen.queryByRole("form", { name: "Campaign terms" })).toBeNull();
  });

  it("offers only 'Start another round' after a round that missed its goal, and nothing once it is funded", async () => {
    await open("LEAD", campaignView({ state: "FAILED", lead: leadPart() }));
    const on = (n: string) => !(screen.getByRole("button", { name: new RegExp(n) }) as HTMLButtonElement).disabled;
    expect([on("Close and collect now"), on("Cancel the campaign"), on("Start another round"), on("Try the deadline early")]).toEqual([false, false, true, false]);
    cleanup();
    await open("LEAD", campaignView({ state: "CAPTURED", lead: leadPart() }));
    for (const b of screen.getByRole("region", { name: "Organiser" }).querySelectorAll("[aria-label=Controls] button")) expect((b as HTMLButtonElement).disabled).toBe(true);
  });

  it("does not show a hold deadline or the lead's buttons while still setting up", async () => {
    await open("LEAD", setup());
    expect(screen.queryByTestId("honor")).toBeNull();
    expect(screen.queryByRole("button", { name: /Close and collect now/ })).toBeNull();
  });
});

describe("setting up from the project, before a campaign exists", () => {
  const detail = (state: string, campaign: unknown = null) => ({ ...project({ state, campaign }), delivery_days: 5, payout_release_policy: "HUMAN", created_at: "2026-11-09T10:00:00", members: [], viewer: null });

  it("shows the lead the setup form, saves, and then shows the new campaign", async () => {
    nav.query = "project=1";
    setToken("tok");
    let made = false;
    const m = mockFetch({
      "GET /auth/me": { body: me("LEAD") },
      "GET /projects/1": () => ({ body: detail("CAMPAIGN_SETUP", made ? { id: 1, number: 1, state: "SETUP", goal_cents: 40000, pledged_cents: 0, pledge_count: 0, deadline_at: null } : null) }),
      "POST /projects/1/campaigns": () => { made = true; return { status: 201, body: campaignView({ state: "SETUP", lead: leadPart() }) }; },
      "GET /campaigns/1": { body: campaignView({ state: "SETUP", opens_at: null, lead: leadPart() }) },
    });
    wrapped(<CampaignPage />);
    expect(await screen.findByRole("form", { name: "Campaign terms" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Campaign" })).toBeTruthy();
    expect(screen.getByText("Back to the project").getAttribute("href")).toBe("/project?id=1");
    fireEvent.change(screen.getByLabelText("Deadline (UTC)"), { target: { value: "2026-11-12T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the terms" }));
    expect(await screen.findByTestId("title")).toBeTruthy();
    expect(posts(m)).toHaveLength(1);
  });

  it("tells everyone else there is no campaign yet", async () => {
    nav.query = "project=1";
    for (const [role, state] of [["SPONSOR", "CAMPAIGN_SETUP"], ["LEAD", "CONTRACTING"], [null, "CAMPAIGN_SETUP"]] as const) {
      if (role) setToken("tok");
      mockFetch({ ...(role ? { "GET /auth/me": { body: me(role) } } : {}), "GET /projects/1": { body: detail(state) } } as never);
      wrapped(<CampaignPage />);
      expect(await screen.findByText("No campaign yet"), `${role} ${state}`).toBeTruthy();
      expect(screen.queryByRole("form", { name: "Campaign terms" })).toBeNull();
      cleanup();
      clearToken();
    }
  });

  it("goes to the project's campaign when it has one", async () => {
    nav.query = "project=1";
    mockFetch({
      "GET /projects/1": { body: detail("PLEDGING", { id: 1, number: 1, state: "OPEN", goal_cents: 40000, pledged_cents: 0, pledge_count: 0, deadline_at: null }) },
      "GET /campaigns/1": { body: campaignView() }, "GET /projects/1/ledger": { body: ledger([]) },
    });
    wrapped(<CampaignPage />);
    expect(await screen.findByTestId("title")).toBeTruthy();
  });

  it("shows the server's reason when the project cannot be loaded", async () => {
    nav.query = "project=1";
    mockFetch({ "GET /projects/1": { status: 404, body: { error: { code: "PROJECT_NOT_FOUND", message: "No such project" } } } });
    wrapped(<CampaignPage />);
    expect(await screen.findByText("No such project")).toBeTruthy();
  });
});

describe("the Strategist", () => {
  const live = (over: Record<string, unknown> = {}) => campaignView({ lead: leadPart(), ...over });
  const withReport = (r = strategistReport()) => ({ "GET /campaigns/1/strategist": { body: r } });

  it("is shown to the lead for a campaign that is still live, and never otherwise", async () => {
    await open("LEAD", live());
    expect(screen.getByRole("region", { name: "Strategist" })).toBeTruthy();
    cleanup();
    await open("LEAD", live({ state: "SETUP", opens_at: null }));
    expect(screen.getByRole("region", { name: "Strategist" })).toBeTruthy();
    for (const state of ["CAPTURING", "CAPTURED", "FAILING", "FAILED", "CANCELLED"]) {
      cleanup();
      const m = await open("LEAD", live({ state }));
      expect(screen.queryByRole("region", { name: "Strategist" }), state).toBeNull();
      expect(m.calls.some((c) => c.path.includes("strategist")), state).toBe(false);
    }
  });

  it("tells the lead to run it when there is no forecast yet", async () => {
    await open("LEAD", live());
    expect(await screen.findByTestId("no-report")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run the Strategist" })).toBeTruthy();
  });

  it("does not claim there is no forecast for another kind of failure", async () => {
    await open("LEAD", live(), { "GET /campaigns/1/strategist": { status: 500, body: { error: { code: "BOOM", message: "down" } } } });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("no-report")).toBeNull();
  });

  it("shows the estimate in words with every number from the system, the risks and where the wording came from", async () => {
    await open("LEAD", live(), withReport());
    expect((await screen.findByTestId("headline")).textContent).toBe("About a 3% chance of reaching the goal (estimate (heuristic))");
    expect(screen.getByTestId("probability").textContent).toBe("3%");
    const f = screen.getByTestId("forecast");
    expect(f.textContent).toContain("estimate (heuristic)");
    expect(f.textContent).toContain("expected $157.50 of $400.00 · 48 h left");
    expect(f.textContent).toContain("$0 of $400 is held.");
    expect(within(screen.getByRole("list", { name: "Risks" })).getByText("Some invitees have not opened the link")).toBeTruthy();
    expect(screen.getByTestId("source").textContent).toContain("Worded by a template; every number is computed by the system.");
    expect(screen.getByRole("button", { name: "Update the forecast" })).toBeTruthy();
    cleanup();
    await open("LEAD", live(), withReport(strategistReport({ narrative: { ...strategistReport().narrative, source: "AI", risk_factors: [] } })));
    expect((await screen.findByTestId("source")).textContent).toContain("Worded by the AI");
    expect(screen.queryByRole("list", { name: "Risks" })).toBeNull();
  });

  it("suggests a deadline with its reason, and applies exactly that moment", async () => {
    const m = await open("LEAD", live(), { ...withReport(), "POST /campaigns/1/strategist/apply": { body: campaignView() } });
    const adv = await screen.findByTestId("advice");
    expect(adv.textContent).toContain("Suggested deadline: Nov 13, 12:00 UTC");
    expect(adv.textContent).toContain("The expected pledges are well below the goal");
    fireEvent.click(screen.getByRole("button", { name: "Apply this deadline" }));
    await waitFor(() => expect(posts(m)).toHaveLength(1));
    expect(posts(m)[0].path).toBe("/campaigns/1/strategist/apply");
    expect(body(posts(m)[0])).toEqual({ deadline_at: "2026-11-13T12:00:00+00:00" });
  });

  it("reloads the campaign and the forecast after applying, and shows the server's reason when it refuses", async () => {
    let k = 0;
    const m = await open("LEAD", live(), { ...withReport(), "POST /campaigns/1/strategist/apply": () => (k++ === 0 ? { body: campaignView() } : { status: 409, body: { error: { code: "EXTENSION_USED", message: "The deadline has already been extended once" } } }) });
    await screen.findByTestId("advice");
    const camp = () => m.calls.filter((c) => c.path === "/campaigns/1").length;
    const rep = () => m.calls.filter((c) => c.path === "/campaigns/1/strategist").length;
    const [c0, r0] = [camp(), rep()];
    fireEvent.click(screen.getByRole("button", { name: "Apply this deadline" }));
    await waitFor(() => expect(camp()).toBe(c0 + 1));
    await waitFor(() => expect(rep()).toBe(r0 + 1));
    fireEvent.click(screen.getByRole("button", { name: "Apply this deadline" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The deadline has already been extended once");
  });

  it("shows no advice when there is none, and notes an extension already used", async () => {
    const r = strategistReport();
    r.suggestions = { ...r.suggestions, deadline: null, applied_extension: { from: "2026-11-12T10:00:00+00:00", to: "2026-11-13T09:00:00+00:00", at: "2026-11-11T10:00:00+00:00" } };
    await open("LEAD", live(), withReport(r));
    await screen.findByTestId("forecast");
    expect(screen.queryByTestId("advice")).toBeNull();
    expect(screen.getByTestId("extended").textContent).toBe("The deadline was extended once, from Nov 12, 10:00 UTC to Nov 13, 09:00 UTC. It cannot be extended again.");
    cleanup();
    await open("LEAD", live(), withReport());
    await screen.findByTestId("forecast");
    expect(screen.queryByTestId("extended")).toBeNull();
  });

  it("offers each message to copy or open in WhatsApp, with the reason that person was chosen", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await open("LEAD", live(), withReport());
    const item = within(await screen.findByRole("list", { name: "Nudges" })).getAllByRole("listitem")[0];
    expect(item.getAttribute("data-source")).toBe("TEMPLATE");
    expect(item.textContent).toContain("Ravi");
    expect(item.textContent).toContain("Draft from a template");
    expect(item.textContent).toContain("hasn't opened the link, said $150");
    expect(item.textContent).toContain("Ravi, we're $400 short. The link: http://x/campaign?id=1");
    expect(within(item).getByText("Draft from a template").className).toContain("bg-gray-100");
    const wa = within(item).getByRole("link", { name: "Open in WhatsApp" });
    expect(wa.getAttribute("href")).toBe(`https://wa.me/?text=${encodeURIComponent("Ravi, we're $400 short. The link: http://x/campaign?id=1")}`);
    expect(wa.getAttribute("target")).toBe("_blank");
    expect(wa.getAttribute("rel")).toBe("noopener noreferrer");
    fireEvent.click(within(item).getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(within(item).getByRole("button", { name: "Copied" })).toBeTruthy());
    expect(writeText).toHaveBeenCalledWith("Ravi, we're $400 short. The link: http://x/campaign?id=1");
  });

  it("marks a message written by the AI differently, and says when the copy did not work", async () => {
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockRejectedValue(new Error("blocked")) }, configurable: true });
    const r = strategistReport();
    r.nudges = [{ ...r.nudges[0], source: "AI" }];
    await open("LEAD", live(), withReport(r));
    const item = within(await screen.findByRole("list", { name: "Nudges" })).getAllByRole("listitem")[0];
    expect(within(item).getByText("Draft written by the AI, checked by the system").className).toContain("bg-blue-100");
    fireEvent.click(within(item).getByRole("button", { name: "Copy" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Could not copy. Select the message and copy it by hand.");
    expect(within(item).getByRole("button", { name: "Copy" })).toBeTruthy();
  });

  it("leaves out the messages section when there are none, and the reason when the person is not in the ranking", async () => {
    const r = strategistReport();
    r.nudges = [{ ...r.nudges[0], member_id: 99 }];
    await open("LEAD", live(), withReport(r));
    const item = within(await screen.findByRole("list", { name: "Nudges" })).getAllByRole("listitem")[0];
    expect(item.textContent).not.toContain("hasn't opened");
    cleanup();
    r.nudges = [];
    await open("LEAD", live(), withReport(r));
    await screen.findByTestId("forecast");
    expect(screen.queryByRole("list", { name: "Nudges" })).toBeNull();
  });

  it("shows the server's reason when it cannot be run", async () => {
    await open("LEAD", live(), { "POST /campaigns/1/strategist/run": { status: 409, body: { error: { code: "CAMPAIGN_STATE", message: "Not advising on this campaign" } } } });
    fireEvent.click(await screen.findByRole("button", { name: "Run the Strategist" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Not advising on this campaign");
  });
});

describe("the clock and the news", () => {
  it("counts down to the deadline from the real time, and redraws every half minute", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
    vi.setSystemTime(new Date("2026-11-12T08:00:00Z"));
    await open();
    expect(screen.getByTestId("countdown").textContent).toBe("2 hours 0 minutes left");
    vi.setSystemTime(new Date("2026-11-12T09:14:00Z"));
    await act(async () => { vi.advanceTimersByTime(CLOCK_MS + 10); });
    expect(screen.getByTestId("countdown").textContent).toBe("45 minutes left");
    vi.setSystemTime(new Date("2026-11-12T10:00:30Z"));
    await act(async () => { vi.advanceTimersByTime(CLOCK_MS); });
    expect(screen.getByTestId("countdown").textContent).toBe("Closed");
  });

  it("shows no clock for a campaign that has not opened", async () => {
    await open(null, campaignView({ state: "SETUP", opens_at: null }));
    expect(screen.queryByTestId("countdown")).toBeNull();
  });

  it("asks an open campaign for news on a timer while visible, not while hidden, and keeps the page when a refresh fails", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    let l = 0;
    let fail = false;
    await open(null, campaignView(), {
      "GET /campaigns/1": () => { n += 1; return fail ? { status: 500, body: { error: { code: "X", message: "boom" } } } : { body: campaignView() }; },
      "GET /projects/1/ledger": () => { l += 1; return { body: ledger(pledgeRows) }; },
    });
    const [n0, l0] = [n, l];
    await act(async () => { await vi.advanceTimersByTimeAsync(CAMPAIGN_REFRESH_MS - 1000); });
    expect(n).toBe(n0);
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect([n, l]).toEqual([n0 + 1, l0 + 1]);
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(CAMPAIGN_REFRESH_MS * 2); });
    expect(n).toBe(n0 + 1);
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    fail = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(CAMPAIGN_REFRESH_MS + 100); });
    expect(await screen.findByText(/Could not refresh just now \(boom\)/)).toBeTruthy();
    expect(screen.getByTestId("title")).toBeTruthy();
  });

  it("does not ask a campaign that is not open for news", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    await open(null, campaignView({ state: "CAPTURED" }), { "GET /campaigns/1": () => { n += 1; return { body: campaignView({ state: "CAPTURED" }) }; } });
    const n0 = n;
    await act(async () => { await vi.advanceTimersByTimeAsync(CAMPAIGN_REFRESH_MS * 3); });
    expect(n).toBe(n0);
  });

  it("runs the Strategist and shows the forecast when the job is done", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let polls = 0;
    let done = false;
    await open("LEAD", campaignView({ lead: leadPart() }), {
      "GET /campaigns/1/strategist": () => (done ? { body: strategistReport() } : noReport),
      "POST /campaigns/1/strategist/run": { status: 202, body: { job_id: 9 } },
      "GET /jobs/9": () => { polls += 1; if (polls >= 2) done = true; return { body: { state: polls >= 2 ? "DONE" : "RUNNING", result: null, error: null, attempts: 1 } }; },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Run the Strategist" }));
    expect(await screen.findByText("The Strategist is working. This takes a short while.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Run the Strategist" }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    expect(polls).toBe(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS); });
    expect(await screen.findByTestId("headline")).toBeTruthy();
    expect(screen.queryByText("The Strategist is working. This takes a short while.")).toBeNull();
    const seen = polls;
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS * 4); });
    expect(polls).toBe(seen);
  });

  it("says so, with the reason, when the Strategist failed", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await open("LEAD", campaignView({ lead: leadPart() }), { "POST /campaigns/1/strategist/run": { status: 202, body: { job_id: 3 } }, "GET /jobs/3": { body: { state: "FAILED", result: null, error: "StrategistError: no data", attempts: 3 } } });
    fireEvent.click(await screen.findByRole("button", { name: "Run the Strategist" }));
    await screen.findByText("The Strategist is working. This takes a short while.");
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    expect((await screen.findByRole("alert")).textContent).toBe("The Strategist could not finish. It failed: StrategistError: no data");
    expect(screen.queryByText("The Strategist is working. This takes a short while.")).toBeNull();
    expect((screen.getByRole("button", { name: "Run the Strategist" }) as HTMLButtonElement).disabled).toBe(false);
  });
});
