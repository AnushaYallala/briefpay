import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BrdPage from "@/app/brd/page";
import { RequirementDialog } from "@/components/RequirementDialog";
import { AuthProvider } from "@/lib/auth";
import { JOB_POLL_MS } from "@/lib/ba";
import { BRD_REFRESH_MS } from "@/lib/brd";
import { formatMoney } from "@/lib/money";
import { clearToken, setToken } from "@/lib/token";
import { brdReq, brdView, lakshmi, mockFetch, project } from "./helpers";

// Tests added after the mutation check found weak spots in the brief page.
const nav = vi.hoisted(() => ({ query: "id=1" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams(nav.query) }));

beforeEach(() => { clearToken(); nav.query = "id=1"; });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); clearToken(); });

const members = [
  { id: 1, role: "LEAD", display_name: "Lakshmi", business_name: null, business_type: null },
  { id: 2, role: "SPONSOR", display_name: "Ravi", business_name: null, business_type: null },
];
const detail = (state = "BRD_REVIEW") => ({ ...project({ state }), delivery_days: 5, payout_release_policy: "HUMAN", created_at: "2026-11-09T10:00:00", members, viewer: null });
const me = (role: string) => ({ user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role }] });
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const rows = () => Array.from(document.querySelectorAll(".ag-grid-scrolling-container .ag-row"));
const count = (m: { calls: { path: string }[] }, path: string) => m.calls.filter((c) => c.path === path).length;
const ok = { changed: true, brd_version: 1, brd_status: "PENDING_APPROVAL", project_state: "BRD_REVIEW", approved: 1, required: 2, locked: false };

async function open(role: string | null = "LEAD", view = brdView(), state = "BRD_REVIEW", routes: Record<string, unknown> = {}) {
  if (role) setToken("tok");
  const m = mockFetch({ ...(role ? { "GET /auth/me": { body: me(role) } } : {}), "GET /projects/1/brd": { body: view }, "GET /projects/1": { body: detail(state) }, ...routes } as never);
  wrapped(<BrdPage />);
  await screen.findByTestId("title");
  return m;
}

describe("the table and the dialog", () => {
  it("shows people's names in the table once the project's people have loaded", async () => {
    await open(null, brdView(), "BRD_REVIEW", { "GET /projects/1": { body: detail(), delayMs: 1500 } });
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(rows()[0].querySelector('[col-id="askedBy"]')!.textContent).toBe("someone, someone");
    await waitFor(() => expect(rows()[0].querySelector('[col-id="askedBy"]')!.textContent).toBe("Lakshmi, Ravi"), { timeout: 4000 });
  });

  it("stops listening for Escape when the dialog closes", () => {
    const spy = vi.spyOn(window, "removeEventListener");
    const { unmount } = render(<RequirementDialog req={brdReq()} names={{}} onClose={() => undefined} />);
    unmount();
    expect(spy.mock.calls.some(([type]) => type === "keydown")).toBe(true);
  });
});

describe("the brief page", () => {
  it("shows the money in the brief's own currency", async () => {
    const v = brdView();
    v.content = { ...v.content, constraints: { ...v.content.constraints, currency: "EUR" } };
    await open(null, v);
    expect(screen.getByRole("region", { name: "Details" }).textContent).toContain(`Budget${formatMoney(40000, "EUR")}`);
    expect(formatMoney(40000, "EUR")).not.toBe(formatMoney(40000, "USD"));
  });

  it("lists no decisions when there are none yet", async () => {
    await open(null, brdView({ approvals: [] }));
    expect(screen.queryByRole("list", { name: "Decisions" })).toBeNull();
    expect(screen.getByTestId("progress").textContent).toBe("0 of 1 sponsor approved");
  });

  it("asks the server again after an approval, and clears the earlier message when the next try fails", async () => {
    let k = 0;
    const m = await open("LEAD", brdView(), "BRD_REVIEW", { "POST /projects/1/brd/1/decision": () => (k++ === 0 ? { body: ok } : { status: 409, body: { error: { code: "X", message: "Not now" } } }) });
    const before = count(m, "/projects/1/brd");
    fireEvent.click(screen.getByRole("button", { name: "Approve this version" }));
    expect((await screen.findByRole("status")).textContent).toContain("Your approval is recorded");
    await waitFor(() => expect(count(m, "/projects/1/brd")).toBe(before + 1));
    fireEvent.click(screen.getByRole("button", { name: "Approve this version" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Not now");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("keeps the whole page on screen while another version is on its way", async () => {
    const versions = [{ version: 1, status: "SUPERSEDED", sha256: "a".repeat(64) }, { version: 2, status: "PENDING_APPROVAL", sha256: "c".repeat(64) }];
    await open("LEAD", brdView({ version: 2, versions }), "BRD_REVIEW", { "GET /projects/1/brd?version=1": { body: brdView({ version: 1, status: "SUPERSEDED", versions }), delayMs: 250 } });
    fireEvent.click(screen.getByRole("button", { name: "Version 1" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 60)); });
    expect(screen.queryByText("Loading the brief...")).toBeNull();
    expect(screen.getByTestId("title").textContent).toContain("version 2");
    await waitFor(() => expect(screen.getByTestId("title").textContent).toContain("version 1"));
  });
});

describe("the project page link", () => {
  it("is built from the project's own number", async () => {
    const { default: ProjectPage } = await import("@/app/project/page");
    mockFetch({ "GET /projects/1": { body: { ...detail(), id: 5 } } });
    wrapped(<ProjectPage />);
    expect((await screen.findByRole("link", { name: "Read the brief" })).getAttribute("href")).toBe("/brd?id=5");
  });
});

// last on purpose: these fake the clock
describe("timers", () => {
  it("does not ask about any job before one was started", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const m = await open("LEAD", brdView({ status: "SUPERSEDED" }), "REQUIREMENTS");
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS * 3); });
    expect(m.calls.some((c) => c.path.startsWith("/jobs"))).toBe(false);
  });

  it("writes a new version while an old one is open, and then shows the newest", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const versions = [{ version: 1, status: "SUPERSEDED", sha256: "a".repeat(64) }, { version: 2, status: "SUPERSEDED", sha256: "c".repeat(64) }];
    const m = await open("LEAD", brdView({ version: 2, status: "SUPERSEDED", versions }), "REQUIREMENTS", {
      "GET /projects/1/brd?version=1": { body: brdView({ version: 1, status: "SUPERSEDED", versions }) },
      "POST /projects/1/brd/generate": { status: 202, body: { job_id: 3 } },
      "GET /jobs/3": { body: { state: "DONE", result: null, error: null, attempts: 1 } },
    });
    fireEvent.click(screen.getByRole("button", { name: "Version 1" }));
    await waitFor(() => expect(screen.getByTestId("title").textContent).toContain("version 1"));
    fireEvent.click(screen.getByRole("button", { name: "Write a new version" }));
    expect(await screen.findByText("The brief is being written. This takes a short while.")).toBeTruthy();
    const before = count(m, "/projects/1/brd");
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    await waitFor(() => expect(count(m, "/projects/1/brd")).toBe(before + 1));
    await waitFor(() => expect(screen.getByTestId("title").textContent).toContain("version 2"));
    expect(screen.queryByText("The brief is being written. This takes a short while.")).toBeNull();
  });

  it("says a failed job gave no reason when the server gave none, and uses the server's words when the job cannot be asked about", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await open("LEAD", brdView({ status: "SUPERSEDED" }), "REQUIREMENTS", { "POST /projects/1/brd/generate": { status: 202, body: { job_id: 4 } }, "GET /jobs/4": { body: { state: "FAILED", result: null, error: null, attempts: 3 } } });
    fireEvent.click(screen.getByRole("button", { name: "Write a new version" }));
    await screen.findByText("The brief is being written. This takes a short while.");
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    expect((await screen.findByRole("alert")).textContent).toBe("The brief could not be written. It failed.");
    cleanup();
    await open("LEAD", brdView({ status: "SUPERSEDED" }), "REQUIREMENTS", { "POST /projects/1/brd/generate": { status: 202, body: { job_id: 5 } }, "GET /jobs/5": { status: 404, body: { error: { code: "JOB_NOT_FOUND", message: "No such job" } } } });
    fireEvent.click(screen.getByRole("button", { name: "Write a new version" }));
    await screen.findByText("The brief is being written. This takes a short while.");
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    expect((await screen.findByRole("alert")).textContent).toBe("The brief could not be written. No such job");
  });

  it("stops its timers when the page is left", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const set = vi.spyOn(globalThis, "setInterval");
    const clear = vi.spyOn(globalThis, "clearInterval");
    await open("LEAD", brdView(), "BRD_REVIEW");
    const ids = (ms: number) => set.mock.calls.map((c, i) => (c[1] === ms ? set.mock.results[i].value : undefined)).filter((v) => v !== undefined);
    await waitFor(() => expect(ids(BRD_REFRESH_MS)).toHaveLength(1));
    const page = ids(BRD_REFRESH_MS);
    cleanup();
    const cleared = clear.mock.calls.some((c) => c[0] === page[0]);
    set.mockRestore();
    clear.mockRestore();
    vi.useRealTimers();
    expect(cleared).toBe(true);
  });
});
