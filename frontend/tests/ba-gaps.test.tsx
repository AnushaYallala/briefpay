import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BaPage from "@/app/ba/page";
import { ScoreGauge } from "@/components/ScoreGauge";
import { TranscriptPanel } from "@/components/TranscriptPanel";
import { AuthProvider } from "@/lib/auth";
import { BA_REFRESH_MS, JOB_POLL_MS, groupQuestions } from "@/lib/ba";
import { clearToken, setToken } from "@/lib/token";
import { baQuestion, baScore, baView, lakshmi, mockFetch, project, transcript } from "./helpers";

// Tests added after the mutation check found weak spots in BA Studio.
const nav = vi.hoisted(() => ({ query: "id=1" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams(nav.query) }));

beforeEach(() => { clearToken(); nav.query = "id=1"; });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); clearToken(); });

const me = (role = "LEAD") => ({ user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role }] });
const members = [{ id: 1, role: "LEAD", display_name: "Lakshmi", business_name: null, business_type: null }];
const detail = () => ({ ...project(), delivery_days: 5, payout_release_policy: "HUMAN", created_at: "2026-11-09T10:00:00", members, viewer: { role: "LEAD", member_id: 1 } });
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const lines = () => Array.from(document.querySelectorAll('[data-testid="transcript-lines"] li'));
const count = (m: { calls: { path: string }[] }, path: string) => m.calls.filter((c) => c.path === path).length;
const session = (over: Record<string, unknown> = {}) => ({ id: 1, state: "ACTIVE", round: 0, current_score: 58, target_score: 90, max_rounds: 5, ...over });

async function open(role = "LEAD", view = baView(), routes: Record<string, unknown> = {}) {
  setToken("tok");
  const m = mockFetch({
    "GET /auth/me": { body: me(role) }, "GET /projects/1/ba": { body: view }, "GET /projects/1/transcript": { body: transcript() }, "GET /projects/1": { body: detail() }, ...routes,
  } as never);
  wrapped(<BaPage />);
  await screen.findByRole("heading", { name: "BA Studio" });
  return m;
}

describe("the score gauge on its own", () => {
  it("renders nothing without a session", () => {
    const { container } = render(<ScoreGauge view={baView({ session: null, score: null, history: [] })} />);
    expect(container.innerHTML).toBe("");
  });

  it("uses the session's score when no round has been scored, and the scored total otherwise", () => {
    const { unmount } = render(<ScoreGauge view={baView({ score: null, session: session({ current_score: 42 }) })} />);
    expect(screen.getByTestId("score").textContent).toBe("42");
    unmount();
    render(<ScoreGauge view={baView({ score: baScore({ total: 61 }), session: session({ current_score: 40 }) })} />);
    expect(screen.getByTestId("score").textContent).toBe("61");
  });

  it("turns green exactly at the line, not before", () => {
    const at = (total: number) => { const { unmount } = render(<ScoreGauge view={baView({ score: baScore({ total }) })} />); const cls = screen.getByTestId("score").className; unmount(); return cls.includes("text-green-700"); };
    expect([at(89), at(90), at(91)]).toEqual([false, true, true]);
  });

  it("mentions the uncapped score only when it is known", () => {
    const { unmount } = render(<ScoreGauge view={baView({ score: baScore({ total: 89, capped: true, total_uncapped: null }) })} />);
    expect(screen.getByTestId("capped").textContent).toContain("holds the score at 89.");
    expect(screen.getByTestId("capped").textContent).not.toContain("it would be");
    unmount();
    render(<ScoreGauge view={baView({ score: baScore({ total: 89, capped: true, total_uncapped: 95 }) })} />);
    expect(screen.getByTestId("capped").textContent).toContain("(it would be 95)");
  });

  it("draws a dashed line at the target on the chart and says what the state means", () => {
    render(<ScoreGauge view={baView()} />);
    const line = document.querySelector("svg line")!;
    expect([line.getAttribute("y1"), line.getAttribute("y2"), line.getAttribute("stroke-dasharray")]).toEqual(["6", "6", "4 3"]);
    expect(screen.getByText(/The analyst is still collecting details\./)).toBeTruthy();
  });
});

describe("questions and the transcript panel on their own", () => {
  it("keeps questions in the order they were asked when they are equally urgent", () => {
    const qs = [baQuestion({ id: 5, status: "OPEN" }), baQuestion({ id: 3, status: "OPEN" }), baQuestion({ id: 9, status: "ANSWERED" }), baQuestion({ id: 7, status: "ANSWERED" })];
    expect(groupQuestions(qs)[0].questions.map((q) => q.id)).toEqual([3, 5, 7, 9]);
  });

  it("scrolls to the first highlighted line each time the highlight changes", () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    const t = transcript();
    const { rerender } = render(<TranscriptPanel transcript={t} highlight={new Set()} />);
    expect(scroll).not.toHaveBeenCalled();
    rerender(<TranscriptPanel transcript={t} highlight={new Set([5, 4, 6])} />);
    expect(scroll).toHaveBeenCalledTimes(1);
    expect((scroll.mock.contexts[0] as HTMLElement).getAttribute("data-line")).toBe("4");
    expect(scroll.mock.calls[0][0]).toEqual({ block: "center" });
    rerender(<TranscriptPanel transcript={t} highlight={new Set([8])} />);
    expect(scroll).toHaveBeenCalledTimes(2);
    expect((scroll.mock.contexts[1] as HTMLElement).getAttribute("data-line")).toBe("8");
    delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
  });

  it("names a pasted transcript as such", () => {
    render(<TranscriptPanel transcript={{ ...transcript(), source_name: "" }} highlight={new Set()} />);
    expect(screen.getByText(/Pasted text · 10 lines/)).toBeTruthy();
  });
});

describe("question cards", () => {
  it("clears an earlier problem when the next try starts, and shows no answers list when there are none", async () => {
    let n = 0;
    await open("LEAD", baView(), { "POST /ba/questions/1/answers": () => (n++ === 0 ? { status: 409, body: { error: { code: "X", message: "Not now" } } } : { status: 201, body: {} }) });
    expect(screen.queryByRole("list", { name: "Answers" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Your answer to question 1"), { target: { value: "Yes" } });
    fireEvent.click(screen.getByRole("button", { name: "Send answer" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Not now");
    fireEvent.click(screen.getByRole("button", { name: "Send answer" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
});

describe("conflicts and the transcript upload", () => {
  it("colours the settled and open badges, and shows a resolution only for a settled conflict", async () => {
    const conflicts = [
      { topic: "A", positions: [], resolved: false, resolution: "left over" },
      { topic: "B", positions: [], resolved: true, resolution: "Agreed" },
    ];
    await open("LEAD", baView({ score: baScore({ conflicts }) }));
    expect(screen.getByText("Open").className).toContain("bg-red-100");
    expect(screen.getByText("Settled").className).toContain("bg-green-100");
    expect(screen.queryByText(/left over/)).toBeNull();
    expect(screen.getByText("Settled: Agreed")).toBeTruthy();
  });

  it("limits the length of the transcript's name", async () => {
    const none = { status: 404, body: { error: { code: "NO_TRANSCRIPT", message: "none" } } };
    await open("LEAD", baView({ session: null, score: null, history: [], questions: [] }), { "GET /projects/1/transcript": none });
    expect((await screen.findByLabelText("Where it came from")).getAttribute("maxlength")).toBe("120");
  });

  it("clears the pasted text and asks for the transcript again after an upload", async () => {
    const none = { status: 404, body: { error: { code: "NO_TRANSCRIPT", message: "none" } } };
    const m = await open("LEAD", baView({ session: null, score: null, history: [], questions: [] }), { "GET /projects/1/transcript": none, "POST /projects/1/transcripts": { status: 201, body: {} } });
    const before = count(m, "/projects/1/transcript");
    fireEvent.change(await screen.findByLabelText("Transcript text"), { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Upload the transcript" }));
    await waitFor(() => expect(count(m, "/projects/1/transcript")).toBe(before + 1));
    await waitFor(() => expect((screen.getByLabelText("Transcript text") as HTMLTextAreaElement).value).toBe(""));
  });

  it("does not flash the upload form while the transcript is still loading", async () => {
    const m = await open("LEAD", baView(), { "GET /projects/1/transcript": { body: transcript(), delayMs: 300 } });
    expect(screen.queryByText("No transcript yet")).toBeNull();
    expect(m.calls.length).toBeGreaterThan(0);
    await waitFor(() => expect(lines().length).toBe(10));
  });

  it("does not offer the upload form just because the transcript failed to load", async () => {
    await open("LEAD", baView(), { "GET /projects/1/transcript": { status: 500, body: { error: { code: "BOOM", message: "down" } } } });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText("No transcript yet")).toBeNull();
    expect(screen.queryByLabelText("Transcript text")).toBeNull();
  });
});

describe("refreshing", () => {
  it("keeps the whole studio on screen while a refresh is on its way", async () => {
    let n = 0;
    await open("LEAD", baView(), { "GET /projects/1/ba": () => ({ body: baView(), delayMs: n++ === 0 ? 0 : 200 }) });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 40)); });
    expect(n).toBe(2);
    expect(screen.queryByText(/Loading BA Studio/)).toBeNull();
    expect(screen.getByTestId("score")).toBeTruthy();
  });
});

// last on purpose: these fake the clock and spy on the interval functions
describe("timers", () => {
  it("stops its timers when the page is left", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const set = vi.spyOn(globalThis, "setInterval");
    const clear = vi.spyOn(globalThis, "clearInterval");
    const m = await open("LEAD", baView({ can_run: true }), { "POST /projects/1/ba/run": { status: 202, body: { job_id: 7 } }, "GET /jobs/7": { body: { state: "RUNNING", result: null, error: null, attempts: 1 } } });
    expect(m.calls.length).toBeGreaterThan(0);
    const ids = (ms: number) => set.mock.calls.map((c, i) => (c[1] === ms ? set.mock.results[i].value : undefined)).filter((v) => v !== undefined);
    await waitFor(() => expect(ids(BA_REFRESH_MS)).toHaveLength(1));
    const page = ids(BA_REFRESH_MS);
    fireEvent.click(screen.getByRole("button", { name: "Run the analysis again" }));
    await screen.findByText("The analyst is working. This takes a short while.");
    await waitFor(() => expect(ids(JOB_POLL_MS)).toHaveLength(1));
    const job = ids(JOB_POLL_MS);
    cleanup();
    const cleared = [page[0], job[0]].map((id) => clear.mock.calls.some((c) => c[0] === id));
    set.mockRestore();
    clear.mockRestore();
    vi.useRealTimers();
    expect(cleared).toEqual([true, true]);
  });
});
