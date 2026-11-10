import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AuditPage from "@/app/audit/page";
import { AuthProvider } from "@/lib/auth";
import { AUDIT_REFRESH_MS } from "@/lib/audit";
import { clearToken, setToken } from "@/lib/token";
import { lakshmi, mockFetch, run } from "./helpers";

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

const runs = [
  run({ id: 4, agent: "VERIFY_JUDGE", status: "ERROR", output: null, error: "model timed out", latency_ms: 2540, input_tokens: null, output_tokens: null }),
  run({ id: 3, agent: "BRD_GEN", status: "REPLAYED", model: "recorded", provider: "replay" }),
  run({ id: 2, agent: "BA_SCORE", output: { score: 80, note: "<img src=x onerror=alert(1)>" } }),
  run({ id: 1, agent: "BA_SCORE", prompt_version: "v2" }),
];
const me = { user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role: "LEAD" }] };
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const gridRows = () => Array.from(document.querySelectorAll(".ag-grid-scrolling-container .ag-row"));

async function open(extra: Record<string, never> = {}) {
  setToken("tok");
  const m = mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/agent-runs": { body: { project_id: 1, rows: runs } }, ...extra });
  wrapped(<AuditPage />);
  await screen.findByTestId("audit-grid");
  await waitFor(() => expect(gridRows().length).toBeGreaterThan(0));
  return m;
}

const cell = (row: Element, col: string) => row.querySelector(`[col-id="${col}"]`) as HTMLElement;

describe("gaps found by the mutation check", () => {
  it("shows the time in UTC words, tokens that are missing as zero, and the fingerprint short with the whole thing on hover", async () => {
    await open();
    expect(cell(gridRows()[0], "created_at").textContent).toBe("Nov 10, 12:00 UTC");
    expect(cell(gridRows()[0], "tokens").textContent).toBe("0 / 0");
    const hash = cell(gridRows()[2], "input_hash").querySelector("span") as HTMLElement;
    expect([hash.textContent, hash.getAttribute("title")]).toEqual(["abcdef12", "abcdef1234567890abcdef"]);
  });

  it("colours the result chip by outcome and searches by its plain words, not the raw code", async () => {
    await open();
    const chip = (i: number) => cell(gridRows()[i], "status").querySelector("span") as HTMLElement;
    expect(chip(0).className).toContain("bg-red-100");
    expect(chip(1).className).toContain("bg-blue-100");
    expect(chip(2).className).toContain("bg-green-100");
    fireEvent.change(screen.getByLabelText("Search the audit trail"), { target: { value: "Replayed from" } });
    await waitFor(() => expect(gridRows().length).toBe(1));
  });

  it("search finds a call by plain words or by the raw code, for agents and results alike", async () => {
    await open();
    const box = screen.getByLabelText("Search the audit trail");
    for (const [text, count] of [["Brief writer", 1], ["BRD_GEN", 1], ["Business analyst", 2], ["BA_SCORE", 2], ["Failed", 1], ["ERROR", 1], ["Answered", 2], ["OK", 2]] as const) {
      fireEvent.change(box, { target: { value: text } });
      await waitFor(() => expect(gridRows().length, text).toBe(count));
    }
  });

  it("marks every kind of failed call red and nothing else", async () => {
    setToken("tok");
    const four = [run({ id: 4, status: "SCHEMA_INVALID" }), run({ id: 3, status: "ERROR" }), run({ id: 2, status: "REPLAYED" }), run({ id: 1, status: "OK" })];
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/agent-runs": { body: { project_id: 1, rows: four } } });
    wrapped(<AuditPage />);
    await waitFor(() => expect(gridRows().length).toBe(4));
    expect(gridRows().map((r) => r.className.includes("bg-red-50"))).toEqual([true, true, false, false]);
  });

  it("shows the newest call first and pins the number column on the left", async () => {
    await open();
    expect(document.querySelector(".ag-root")!.className).toContain("ag-has-left-pinned-cols");
    expect(cell(gridRows()[0], "id").className).toContain("ag-cell-last-left-pinned");
    expect(cell(gridRows()[0], "agent").className).not.toContain("pinned");
    expect(gridRows().map((r) => r.getAttribute("row-index"))).toEqual(["0", "1", "2", "3"]);
    expect(gridRows().map((r) => cell(r, "id").textContent)).toEqual(["4", "3", "2", "1"]);
  });

  it("sorts newest first even when the server sends them oldest first", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/agent-runs": { body: { project_id: 1, rows: [...runs].reverse() } } });
    wrapped(<AuditPage />);
    await waitFor(() => expect(gridRows().length).toBe(4));
    const byIndex = gridRows().sort((a, b) => Number(a.getAttribute("row-index")) - Number(b.getAttribute("row-index")));
    expect(byIndex.map((r) => cell(r, "id").textContent)).toEqual(["4", "3", "2", "1"]);
  });

  it("lets a small trail grow to its natural height and gives a large one a scrolling window", async () => {
    await open();
    expect(document.querySelector(".ag-root")!.className).toContain("ag-layout-auto-height");
    expect(screen.getByTestId("audit-grid").className).not.toContain("h-[600px]");
    cleanup();
    const many = Array.from({ length: 201 }, (_, i) => run({ id: i + 1 }));
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/agent-runs": { body: { project_id: 1, rows: many } } });
    wrapped(<AuditPage />);
    await screen.findByTestId("audit-grid");
    await waitFor(() => expect(document.querySelector(".ag-root")).not.toBeNull());
    expect(document.querySelector(".ag-root")!.className).toContain("ag-layout-normal");
    expect(screen.getByTestId("audit-grid").className).toContain("h-[600px]");
  });

  it("describes the call in the dialog header: result, prompt version and input fingerprint", async () => {
    await open();
    fireEvent.click(gridRows()[2].querySelector("button")!);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("Answered · prompt v1");
    expect(dialog.textContent).toContain("input abcdef1234567890abcdef");
  });

  it("stops listening for Escape when the dialog closes", async () => {
    await open();
    const spy = vi.spyOn(window, "removeEventListener");
    fireEvent.click(gridRows()[2].querySelector("button")!);
    await screen.findByRole("dialog");
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(spy.mock.calls.some(([type]) => type === "keydown")).toBe(true);
    spy.mockRestore();
  });

  it("says '1 call' for a single call", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/agent-runs": { body: { project_id: 1, rows: [run()] } } });
    wrapped(<AuditPage />);
    await waitFor(() => expect(gridRows().length).toBe(1));
    expect(screen.getByTestId("audit-summary").textContent).toContain("1 call ·");
  });

  it("keeps every agent chip while one is chosen, and does not claim 'no calls' when a choice has none left", async () => {
    let n = 0;
    setToken("tok");
    mockFetch({
      "GET /auth/me": { body: me },
      "GET /projects/1/agent-runs": () => ({ body: { project_id: 1, rows: n++ === 0 ? runs : runs.filter((r) => r.agent !== "BA_SCORE") } }),
    });
    wrapped(<AuditPage />);
    await waitFor(() => expect(gridRows().length).toBe(4));
    fireEvent.click(screen.getByRole("button", { name: "Business analyst: scoring" }));
    await waitFor(() => expect(gridRows().length).toBe(2));
    expect(screen.getByRole("button", { name: "Brief writer" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Verifier: judge" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));              // the chosen agent's calls are gone from the answer
    await waitFor(() => expect(n).toBe(2));
    await waitFor(() => expect(gridRows().length).toBe(0));
    expect(screen.queryByText("No AI calls yet")).toBeNull();
    expect(screen.getByRole("button", { name: "Brief writer" })).toBeTruthy();
  });

  it("waits for the sign-in check before deciding, and reloads when a different person signs in", async () => {
    setToken("tok");
    let who = 0;
    const m = mockFetch({
      "GET /auth/me": () => (who === 0 ? { body: me, delayMs: 120 } : { body: { user: { id: 2, email: "ravi@velugu.example.com", display_name: "Ravi" }, memberships: [{ member_id: 2, project_id: 1, role: "SPONSOR" }] } }),
      "POST /auth/login": () => { who = 1; return { body: { token: "tok2", user: { id: 2, email: "ravi@velugu.example.com", display_name: "Ravi" } } }; },
      "GET /projects/1/agent-runs": { body: { project_id: 1, rows: runs } },
    });
    const { Switch } = await import("./switch");
    wrapped(<><AuditPage /><Switch /></>);
    expect(screen.getByText("Checking who you are...")).toBeTruthy();
    expect(screen.queryByText("Sign in to see the AI audit trail")).toBeNull();
    await waitFor(() => expect(gridRows().length).toBe(4));
    const before = m.calls.filter((c) => c.path.endsWith("agent-runs")).length;
    fireEvent.click(screen.getByRole("button", { name: "switch person" }));
    await waitFor(() => expect(m.calls.filter((c) => c.path.endsWith("agent-runs")).length).toBe(before + 1));
  });
});

describe("audit page", () => {
  it("shows every call newest first with plain words, the summary and a red failed row", async () => {
    await open();
    expect(screen.getByRole("heading", { name: "AI audit trail" })).toBeTruthy();
    expect(gridRows().map((r) => r.getAttribute("row-id"))).toEqual(["4", "3", "2", "1"]);
    const text = gridRows().map((r) => r.textContent ?? "");
    expect(text[0]).toContain("Verifier: judge");
    expect(text[0]).toContain("Failed");
    expect(text[0]).toContain("2.5 s");
    expect(text[1]).toContain("replay / recorded");
    expect(text[2]).toContain("100 / 50");
    expect(text[2]).toContain("abcdef12");
    expect(text[3]).toContain("v2");
    expect(gridRows()[0].className).toContain("bg-red-50");
    expect(gridRows()[2].className).not.toContain("bg-red-50");
    expect(screen.getByTestId("audit-summary").textContent).toBe("4 calls · 1 failed · average 950 ms · 450 tokens");
  });

  it("filters by agent with chips that toggle, and the summary follows", async () => {
    await open();
    const chip = screen.getByRole("button", { name: "Business analyst: scoring" });
    fireEvent.click(chip);
    await waitFor(() => expect(chip.getAttribute("aria-pressed")).toBe("true"));
    await waitFor(() => expect(gridRows().length).toBe(2));
    expect(screen.getByTestId("audit-summary").textContent).toContain("2 calls · 0 failed");
    fireEvent.click(chip);
    await waitFor(() => expect(chip.getAttribute("aria-pressed")).toBe("false"));
    await waitFor(() => expect(gridRows().length).toBe(4));
  });

  it("searches across the table", async () => {
    await open();
    fireEvent.change(screen.getByLabelText("Search the audit trail"), { target: { value: "recorded" } });
    await waitFor(() => expect(gridRows().length).toBe(1));
  });

  it("opens the full call as plain text, never as HTML, and closes with Escape, the button or the backdrop", async () => {
    await open();
    fireEvent.click(gridRows()[2].querySelector("button")!);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.getAttribute("aria-label")).toBe("AI call 2");
    expect(screen.getByTestId("run-output").textContent).toContain("<img src=x onerror=alert(1)>");
    expect(document.querySelector("dialog img, [role=dialog] img")).toBeNull();
    expect(screen.queryByTestId("run-error")).toBeNull();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fireEvent.click(gridRows()[0].querySelector("button")!);
    expect((await screen.findByTestId("run-error")).textContent).toBe("model timed out");
    expect(screen.getByTestId("run-output").textContent).toBe("No answer was saved.");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fireEvent.click(gridRows()[1].querySelector("button")!);
    fireEvent.click((await screen.findByRole("dialog")).parentElement!);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("does not close when the click is inside the dialog", async () => {
    await open();
    fireEvent.click(gridRows()[1].querySelector("button")!);
    fireEvent.click(await screen.findByRole("dialog"));
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.keyDown(window, { key: "Enter" });
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("asks people who are not signed in to sign in, without calling the API", async () => {
    const m = mockFetch({});
    wrapped(<AuditPage />);
    expect(await screen.findByText("Sign in to see the AI audit trail")).toBeTruthy();
    expect(m.calls).toHaveLength(0);
  });

  it("shows the server's reason when the person is not a member", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/agent-runs": { status: 403, body: { error: { code: "FORBIDDEN", message: "You are not on this project" } } } });
    wrapped(<AuditPage />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("You are not on this project")).toBeTruthy();
  });

  it("shows an empty state", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/agent-runs": { body: { project_id: 1, rows: [] } } });
    wrapped(<AuditPage />);
    expect(await screen.findByText("No AI calls yet")).toBeTruthy();
  });

  it("asks for a project when the address has no valid id", async () => {
    for (const q of ["", "id=abc", "id=-1", "id=1234567890"]) {
      nav.query = q;
      const { unmount } = wrapped(<AuditPage />);
      expect(await screen.findByText("No project selected")).toBeTruthy();
      unmount();
    }
  });

  it("refreshes on a timer while visible, not while hidden, keeps rows when a refresh fails, and stops on leaving", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    let fail = false;
    setToken("tok");
    mockFetch({
      "GET /auth/me": { body: me },
      "GET /projects/1/agent-runs": () => { n += 1; return fail ? { status: 500, body: { error: { code: "X", message: "boom" } } } : { body: { project_id: 1, rows: runs } }; },
    });
    wrapped(<AuditPage />);
    await screen.findByTestId("audit-grid");
    const first = n;
    await act(async () => { await vi.advanceTimersByTimeAsync(AUDIT_REFRESH_MS - 1000); });
    expect(n).toBe(first);
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(n).toBe(first + 1);

    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(AUDIT_REFRESH_MS * 2); });
    expect(n).toBe(first + 1);

    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    fail = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(AUDIT_REFRESH_MS + 100); });
    expect(await screen.findByText(/Could not refresh just now \(boom\)/)).toBeTruthy();
    expect(gridRows().length).toBe(4);                                          // the old calls stay on screen

    const calls = n;
    cleanup();
    await act(async () => { await vi.advanceTimersByTimeAsync(AUDIT_REFRESH_MS * 3); });
    expect(n).toBe(calls);                                                      // the timer stops when the page is left
  });

  it("the Refresh button asks again and keeps the table on screen while it waits", async () => {
    let n = 0;
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/agent-runs": () => ({ body: { project_id: 1, rows: runs }, delayMs: n++ === 0 ? 0 : 150 }) });
    wrapped(<AuditPage />);
    await waitFor(() => expect(gridRows().length).toBe(4));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 40)); });
    expect(n).toBe(2);
    expect(screen.queryByText(/Loading the AI audit trail/)).toBeNull();
    expect(gridRows().length).toBe(4);
  });

  it("the Refresh button asks again", async () => {
    const m = await open();
    const before = m.calls.filter((c) => c.path.endsWith("agent-runs")).length;
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(m.calls.filter((c) => c.path.endsWith("agent-runs")).length).toBe(before + 1));
  });
});

// last on purpose: a test that fakes only the interval functions must not run before the timing test above
describe("timer clean-up", () => {
  it("stops its timer when the page is left", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const set = vi.spyOn(globalThis, "setInterval");
    const clear = vi.spyOn(globalThis, "clearInterval");
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/agent-runs": { body: { project_id: 1, rows: runs } } });
    const { unmount } = wrapped(<AuditPage />);
    await waitFor(() => expect(gridRows().length).toBe(4));
    const mine = set.mock.calls.map((c, i) => (c[1] === AUDIT_REFRESH_MS ? set.mock.results[i].value : undefined)).filter((v) => v !== undefined);
    expect(mine).toHaveLength(1);                                               // the page's own refresh timer (the grid has timers of its own)
    expect(clear.mock.calls.some((c) => c[0] === mine[0])).toBe(false);
    unmount();
    const cleared = clear.mock.calls.some((c) => c[0] === mine[0]);
    set.mockRestore();
    clear.mockRestore();
    vi.useRealTimers();
    expect(cleared).toBe(true);
  });
});
