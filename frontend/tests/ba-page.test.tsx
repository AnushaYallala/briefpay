import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BaPage from "@/app/ba/page";
import { AuthProvider } from "@/lib/auth";
import { BA_REFRESH_MS, JOB_POLL_MS } from "@/lib/ba";
import { clearToken, setToken } from "@/lib/token";
import { baQuestion, baScore, baView, lakshmi, mockFetch, project, transcript } from "./helpers";

const nav = vi.hoisted(() => ({ query: "id=1" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams(nav.query) }));

beforeEach(() => { clearToken(); nav.query = "id=1"; });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  clearToken();
});

const me = (role = "LEAD") => ({ user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role }] });
const members = [
  { id: 1, role: "LEAD", display_name: "Lakshmi", business_name: null, business_type: null },
  { id: 2, role: "SPONSOR", display_name: "Ravi", business_name: null, business_type: null },
];
const detail = () => ({ ...project(), delivery_days: 5, payout_release_policy: "HUMAN", created_at: "2026-11-09T10:00:00", members, viewer: { role: "LEAD", member_id: 1 } });
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const body = (c: { init: RequestInit }) => JSON.parse(String(c.init.body));
const lines = () => Array.from(document.querySelectorAll('[data-testid="transcript-lines"] li'));
const lit = () => lines().filter((l) => l.getAttribute("data-highlight") === "yes").map((l) => l.getAttribute("data-line"));

async function open(role: string | null = "LEAD", view = baView(), routes: Record<string, unknown> = {}) {
  if (role) setToken("tok");
  const m = mockFetch({
    ...(role ? { "GET /auth/me": { body: me(role) } } : {}),
    "GET /projects/1/ba": { body: view }, "GET /projects/1/transcript": { body: transcript() }, "GET /projects/1": { body: detail() }, ...routes,
  } as never);
  wrapped(<BaPage />);
  await screen.findByRole("heading", { name: "BA Studio" });
  return m;
}

describe("BA Studio: the score", () => {
  it("shows the score, the line to reach, the state, the round and the history", async () => {
    await open("LEAD", baView({ history: [{ round: 0, total: 58, capped: false, created_at: "x" }, { round: 1, total: 79, capped: false, created_at: "y" }] }));
    expect(screen.getByTestId("score").textContent).toBe("58");
    expect(screen.getByRole("progressbar", { name: "Score" }).getAttribute("aria-valuenow")).toBe("58");
    expect(screen.getByTestId("score-bar").getAttribute("style")).toContain("width: 58%");
    expect(screen.getByTestId("target-line").getAttribute("style")).toContain("left: 90%");
    expect(screen.getByText("In progress")).toBeTruthy();
    expect(screen.getByText(/The brief can be written once the score reaches/).textContent).toContain("90");
    expect(screen.getByText("Round 0 of up to 5.")).toBeTruthy();
    expect(screen.getByTestId("history").textContent).toBe("Round 0: 58 · Round 1: 79");
    expect(screen.getByTestId("spark").getAttribute("points")).toBe("0,25.2 240,12.6");
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Score history: 58, 79");
    expect(screen.queryByTestId("capped")).toBeNull();
    expect(screen.getByTestId("score").className).not.toContain("text-green-700");
  });

  it("turns green once the line is reached", async () => {
    await open("LEAD", baView({ session: { id: 1, state: "READY", round: 2, current_score: 93, target_score: 90, max_rounds: 5 }, score: baScore({ total: 93 }) }));
    expect(screen.getByTestId("score").className).toContain("text-green-700");
    expect(screen.getByTestId("score-bar").className).toContain("bg-green-600");
    expect(screen.getByText("Ready for the brief")).toBeTruthy();
  });

  it("explains a score held back by a red check", async () => {
    await open("LEAD", baView({ score: baScore({ total: 89, capped: true, total_uncapped: 94 }) }));
    expect(screen.getByTestId("capped").textContent).toContain("holds the score at 89 (it would be 94)");
  });

  it("falls back to the session's score when there is no scored round yet, and hides the history", async () => {
    await open("LEAD", baView({ score: null, history: [] }));
    expect(screen.getByTestId("score").textContent).toBe("58");
    expect(screen.queryByTestId("history")).toBeNull();
    expect(screen.queryByTestId("capped")).toBeNull();
    expect(screen.queryByRole("region", { name: "Dimensions" })).toBeNull();
  });
});

describe("BA Studio: what the analyst found", () => {
  it("shows the must-have checks as passed or not met, with their detail", async () => {
    await open();
    const items = within(screen.getByRole("list", { name: "Gates" })).getAllByRole("listitem");
    expect(items.map((i) => i.getAttribute("data-passed"))).toEqual(["yes", "no"]);
    expect(items[0].className).toContain("bg-green-50");
    expect(items[1].className).toContain("bg-red-50");
    expect(items[1].textContent).toContain("No unresolved conflict between sponsors");
    expect(items[1].textContent).toContain("1 open conflict");
    expect(items[0].querySelector("[aria-label]")!.getAttribute("aria-label")).toBe("Passed");
    expect(items[1].querySelector("[aria-label]")!.getAttribute("aria-label")).toBe("Not met");
  });

  it("shows each area with its marks, bar, reason and a note when it was marked down", async () => {
    await open();
    const d1 = document.querySelector('[data-dimension="D1"]')!;
    const d5 = document.querySelector('[data-dimension="D5"]')!;
    expect(d1.textContent).toContain("Business goals & success measures");
    expect(d1.textContent).toContain("6 of 12");
    expect(d5.textContent).toContain("11.3 of 15");
    expect(screen.getByTestId("bar-D1").getAttribute("style")).toContain("width: 50%");
    expect(screen.getByTestId("bar-D5").getAttribute("style")).toContain("width: 75%");
    expect(d1.textContent).toContain("Goals are clear, no measure yet");
    expect(d1.textContent).not.toContain("marked one level lower");
    expect(d5.textContent).toContain("No evidence was cited for this, so it was marked one level lower.");
  });

  it("highlights the transcript lines a source points at, and nothing for an answer", async () => {
    await open();
    await waitFor(() => expect(lines()).toHaveLength(10));
    expect(lit()).toEqual([]);
    fireEvent.click(within(document.querySelector('[data-dimension="D1"]') as HTMLElement).getByRole("button", { name: "lines 3 to 5" }));
    expect(lit()).toEqual(["3", "4", "5"]);
    fireEvent.click(within(document.querySelector('[data-dimension="D5"]') as HTMLElement).getByRole("button", { name: "line 7" }));
    expect(lit()).toEqual(["7"]);
    fireEvent.click(within(document.querySelector('[data-dimension="D5"]') as HTMLElement).getByRole("button", { name: "answer 12" }));
    expect(lit()).toEqual([]);
    expect(lines()[2].className).not.toContain("bg-yellow-100");
    fireEvent.click(screen.getByRole("button", { name: "line 3" }));                 // the requirement's own source
    expect(lit()).toEqual(["3"]);
    expect(lines()[2].className).toContain("bg-yellow-100");
  });

  it("shows the transcript with numbers and its name", async () => {
    await open();
    await waitFor(() => expect(lines()).toHaveLength(10));
    expect(screen.getByText(/meeting.txt · 10 lines/)).toBeTruthy();
    expect(lines()[0].textContent).toBe("1Speaker 1: line 1");
    expect(lines()[9].textContent).toBe("10Speaker 1: line 10");
  });

  it("shows disagreements with names, and what settled them", async () => {
    const settled = { topic: "Phone numbers", positions: [{ member_id: 2, position: "show them" }, { member_id: 9, position: "hide them" }], resolved: true, resolution: "Show them" };
    await open("LEAD", baView({ score: baScore({ conflicts: [baScore().conflicts[0], settled] }) }));
    const [open1, done] = within(screen.getByRole("region", { name: "Conflicts" })).getAllByRole("listitem").filter((li) => li.hasAttribute("data-resolved"));
    expect(open1.getAttribute("data-resolved")).toBe("no");
    expect(open1.textContent).toContain("Booking online or enquiry only");
    expect(open1.textContent).toContain("Open");
    expect(open1.textContent).toContain("Lakshmi: wants booking");
    expect(open1.textContent).toContain("Ravi: no payments");
    expect(open1.textContent).not.toContain("Settled:");
    expect(done.getAttribute("data-resolved")).toBe("yes");
    expect(done.textContent).toContain("Settled: Show them");
    expect(done.textContent).toContain("Someone: hide them");
    expect(screen.getAllByText("Settled")).toHaveLength(1);
  });

  it("hides the conflicts card when there are none", async () => {
    await open("LEAD", baView({ score: baScore({ conflicts: [] }) }));
    expect(screen.queryByRole("region", { name: "Conflicts" })).toBeNull();
  });

  it("lists the requirements found, who asked and how many checks prove them", async () => {
    const more = { temp_id: "R2", title: "Gallery", description: "Photos.", priority: "COULD", requested_by: [], acceptance_criteria: [], source_refs: [] };
    const two = { temp_id: "R3", title: "Menu", description: "Food.", priority: "SHOULD", requested_by: [2], acceptance_criteria: ["a", "b"], source_refs: ["L1"] };
    await open("LEAD", baView({ score: baScore({ requirements: [baScore().requirements[0], more, two] }) }));
    const region = screen.getByRole("region", { name: "Requirements found" });
    expect(region.textContent).toContain("Requirements found so far (3)");
    const items = within(region).getAllByRole("listitem").filter((li) => li.textContent?.includes("Asked for by"));
    expect(items[0].textContent).toContain("Asked for by Lakshmi, Ravi · 1 check to prove it");
    expect(items[1].textContent).toContain("Asked for by nobody yet · 0 checks to prove it");
    expect(items[2].textContent).toContain("2 checks to prove it");
    expect(within(items[0]).getByText("MUST").className).toContain("bg-red-100");
    expect(within(items[1]).getByText("COULD").className).toContain("bg-gray-100");
    expect(within(items[2]).getByText("SHOULD").className).toContain("bg-amber-100");
    expect(within(items[1]).queryByRole("button")).toBeNull();
  });

  it("says when no requirements were found yet, lists what is out of scope and notes ignored orders", async () => {
    await open("LEAD", baView({ score: baScore({ requirements: [], out_of_scope: [], injection_attempts: ["ignore all rules"] }) }));
    expect(screen.getByText("None yet.")).toBeTruthy();
    expect(screen.queryByText("Out of scope")).toBeNull();
    expect(screen.getByTestId("injection").textContent).toContain("tried to give the AI orders (1 time). It was ignored.");
    cleanup();
    await open("LEAD", baView({ score: baScore({ injection_attempts: ["a", "b"] }) }));
    expect(screen.getByText("Out of scope")).toBeTruthy();
    expect(screen.getByText("Online payments")).toBeTruthy();
    expect(screen.getByTestId("injection").textContent).toContain("(2 times)");
  });

  it("does not show an injection note when nothing was attempted", async () => {
    await open();
    expect(screen.queryByTestId("injection")).toBeNull();
  });
});

describe("BA Studio: questions", () => {
  const qs = [
    baQuestion({ id: 1, round: 0, status: "ANSWERED", can_answer: false, answers: [{ id: 5, member_id: 1, member_name: "Lakshmi", answer_text: "Enquiry form only", selected_option: null }] }),
    baQuestion({ id: 2, round: 1, status: "OPEN", question: "Which pages do you need?", addressed_to: ["ALL"], suggested_options: null }),
    baQuestion({ id: 3, round: 1, status: "SKIPPED", can_answer: false }),
  ];

  it("groups the questions by round with who each is for, the reason and the answers", async () => {
    await open("LEAD", baView({ questions: qs }));
    const rounds = within(screen.getByRole("region", { name: "Questions" })).getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(rounds).toEqual(["Round 1", "Round 0"]);
    const q2 = screen.getByRole("article", { name: "Question 2" });
    expect(q2.textContent).toContain("Functional requirements · for Anyone on the sponsor side");
    expect(q2.textContent).toContain("Which pages do you need?");
    expect(q2.textContent).toContain("The sponsors disagree.");
    expect(q2.getAttribute("data-status")).toBe("OPEN");
    const q1 = screen.getByRole("article", { name: "Question 1" });
    expect(q1.textContent).toContain("for Lakshmi and Ravi");
    expect(q1.textContent).toContain("Answered");
    expect(within(q1).getByRole("list", { name: "Answers" }).textContent).toBe("Lakshmi: Enquiry form only");
    expect(screen.getByRole("article", { name: "Question 3" }).textContent).toContain("Skipped");
    expect(within(q1).queryByLabelText(/Your answer/)).toBeNull();
  });

  it("falls back to the area code and 'Someone' when names are missing", async () => {
    const odd = baQuestion({ id: 9, dimension_name: null, dimension: "D7", status: "ANSWERED", can_answer: false, answers: [{ id: 8, member_id: 3, member_name: null, answer_text: "x", selected_option: null }] });
    await open("LEAD", baView({ questions: [odd] }));
    const q = screen.getByRole("article", { name: "Question 9" });
    expect(q.textContent).toContain("D7 · for");
    expect(within(q).getByRole("list", { name: "Answers" }).textContent).toBe("Someone: x");
  });

  it("answers with a chosen suggestion, sends it, clears the form and reloads", async () => {
    let n = 0;
    const m = await open("LEAD", baView({ questions: [baQuestion()] }), { "GET /projects/1/ba": () => { n += 1; return { body: baView({ questions: [baQuestion()] }) }; }, "POST /ba/questions/1/answers": { status: 201, body: { question_status: "OPEN", round_complete: false } } });
    const before = n;
    const box = screen.getByLabelText("Your answer to question 1") as HTMLTextAreaElement;
    const send = screen.getByRole("button", { name: "Send answer" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    const chip = screen.getByRole("button", { name: "Online booking" });
    fireEvent.click(chip);
    expect(chip.getAttribute("aria-pressed")).toBe("true");
    expect(box.value).toBe("Online booking");
    expect(send.disabled).toBe(false);
    fireEvent.click(chip);
    expect(chip.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(chip);
    fireEvent.change(box, { target: { value: "  Online booking, with a deposit  " } });
    fireEvent.click(send);
    await waitFor(() => expect(n).toBe(before + 1));
    const post = m.calls.find((c) => c.method === "POST")!;
    expect(post.path).toBe("/ba/questions/1/answers");
    expect(body(post)).toEqual({ answer_text: "Online booking, with a deposit", selected_option: "Online booking" });
    await waitFor(() => expect((screen.getByLabelText("Your answer to question 1") as HTMLTextAreaElement).value).toBe(""));
    expect(screen.getByRole("button", { name: "Online booking" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("sends a typed answer with no chosen suggestion, and does not offer suggestions when there are none", async () => {
    const m = await open("LEAD", baView({ questions: [baQuestion({ suggested_options: null })] }), { "POST /ba/questions/1/answers": { status: 201, body: {} } });
    expect(screen.queryByRole("group", { name: "Suggested answers" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Your answer to question 1"), { target: { value: "Boat tours" } });
    fireEvent.click(screen.getByRole("button", { name: "Send answer" }));
    await waitFor(() => expect(m.calls.some((c) => c.method === "POST")).toBe(true));
    expect(body(m.calls.find((c) => c.method === "POST")!)).toEqual({ answer_text: "Boat tours" });
  });

  it("limits the length of an answer", async () => {
    await open();
    expect(screen.getByLabelText("Your answer to question 1").getAttribute("maxlength")).toBe("2000");
  });

  it("shows the server's reason when an answer is refused, and keeps what was typed", async () => {
    await open("LEAD", baView(), { "POST /ba/questions/1/answers": { status: 409, body: { error: { code: "QUESTION_CLOSED", message: "This question is already answered" } } } });
    fireEvent.change(screen.getByLabelText("Your answer to question 1"), { target: { value: "Something" } });
    fireEvent.click(screen.getByRole("button", { name: "Send answer" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This question is already answered");
    expect((screen.getByLabelText("Your answer to question 1") as HTMLTextAreaElement).value).toBe("Something");
    expect((screen.getByRole("button", { name: "Send answer" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("lets only the lead skip an open question", async () => {
    const m = await open("LEAD", baView(), { "POST /ba/questions/1/skip": { body: { question_status: "SKIPPED", round_complete: false } } });
    fireEvent.click(screen.getByRole("button", { name: "Skip this question" }));
    await waitFor(() => expect(m.calls.some((c) => c.method === "POST")).toBe(true));
    expect(m.calls.find((c) => c.method === "POST")!.path).toBe("/ba/questions/1/skip");
    cleanup();
    await open("SPONSOR", baView({ can_run: false }));
    expect(screen.queryByRole("button", { name: "Skip this question" })).toBeNull();
    expect(screen.getByLabelText("Your answer to question 1")).toBeTruthy();              // a sponsor may answer
    cleanup();
    await open("LEAD", baView({ questions: [baQuestion({ status: "ANSWERED", can_answer: false })] }));
    expect(screen.queryByRole("button", { name: "Skip this question" })).toBeNull();
  });

  it("shows the server's reason when a skip is refused", async () => {
    await open("LEAD", baView(), { "POST /ba/questions/1/skip": { status: 409, body: { error: { code: "X", message: "Too late to skip" } } } });
    fireEvent.click(screen.getByRole("button", { name: "Skip this question" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Too late to skip");
  });

  it("will not send an answer twice while the first is on its way", async () => {
    const m = await open("LEAD", baView(), { "POST /ba/questions/1/answers": { status: 201, body: {}, delayMs: 200 } });
    fireEvent.change(screen.getByLabelText("Your answer to question 1"), { target: { value: "Yes" } });
    const send = screen.getByRole("button", { name: "Send answer" }) as HTMLButtonElement;
    fireEvent.click(send);
    await waitFor(() => expect(send.textContent).toBe("Sending..."));
    expect(send.disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Skip this question" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(send);
    await waitFor(() => expect(send.textContent).toBe("Send answer"));
    expect(m.calls.filter((c) => c.method === "POST")).toHaveLength(1);
  });
});

describe("BA Studio: running the analysis", () => {
  it("says what to do when the lead cannot run it because questions are open", async () => {
    await open("LEAD", baView({ can_run: false }));
    expect(screen.getByTestId("why-not-run").textContent).toContain("Answer or skip the open questions first");
    cleanup();
    await open("LEAD", baView({ can_run: true }));
    expect(screen.queryByTestId("why-not-run")).toBeNull();
    cleanup();
    await open("SPONSOR", baView({ can_run: false }));
    expect(screen.queryByTestId("why-not-run")).toBeNull();
    cleanup();
    await open("LEAD", baView({ can_run: false, questions: [baQuestion({ status: "ANSWERED", can_answer: false })] }));
    expect(screen.queryByTestId("why-not-run")).toBeNull();
  });

  it("offers the run only when the server says it can run, with the right words", async () => {
    await open("LEAD", baView({ can_run: true }));
    expect(screen.getByRole("button", { name: "Run the analysis again" })).toBeTruthy();
    cleanup();
    await open("LEAD", baView({ session: null, score: null, history: [], questions: [], can_run: true }));
    expect(screen.getByRole("button", { name: "Start the analysis" })).toBeTruthy();
    cleanup();
    await open("LEAD", baView({ can_run: false }));
    expect(screen.queryByRole("button", { name: /analysis/ })).toBeNull();
  });

  it("explains an analysis that has not started, for the lead and for others", async () => {
    await open("LEAD", baView({ session: null, score: null, history: [], questions: [], can_run: true }));
    expect(screen.getByText("The analysis has not started")).toBeTruthy();
    expect(screen.getByText(/Press “Start the analysis” above/)).toBeTruthy();
    cleanup();
    await open("SPONSOR", baView({ session: null, score: null, history: [], questions: [] }));
    expect(screen.getByText("The lead starts it when the transcript is ready.")).toBeTruthy();
  });

  it("accepts the gaps only after a second, explicit click", async () => {
    let done = false;
    const m = await open("LEAD", baView({ can_finalize: true }), { "POST /projects/1/ba/finalize": () => { done = true; return { body: { state: "FINALIZED", score: 80 } }; } });
    expect(done).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Accept the gaps and move on" }));
    expect(screen.getByText(/Missing details become gaps/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Not yet" }));
    expect(screen.queryByText(/Missing details become gaps/)).toBeNull();
    expect(m.calls.some((c) => c.method === "POST")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Accept the gaps and move on" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, accept the gaps" }));
    await waitFor(() => expect(done).toBe(true));
    await waitFor(() => expect(screen.queryByText(/Missing details become gaps/)).toBeNull());
  });

  it("does not offer to accept the gaps unless the server allows it", async () => {
    await open("LEAD", baView({ can_finalize: false }));
    expect(screen.queryByRole("button", { name: "Accept the gaps and move on" })).toBeNull();
  });

  it("shows the server's reason when finalizing is refused", async () => {
    await open("LEAD", baView({ can_finalize: true }), { "POST /projects/1/ba/finalize": { status: 409, body: { error: { code: "X", message: "Not at the round limit yet" } } } });
    fireEvent.click(screen.getByRole("button", { name: "Accept the gaps and move on" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, accept the gaps" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Not at the round limit yet");
  });

  it("shows the server's reason when a run is refused", async () => {
    await open("LEAD", baView({ can_run: true }), { "POST /projects/1/ba/run": { status: 409, body: { error: { code: "NO_TRANSCRIPT", message: "Upload the meeting transcript first" } } } });
    fireEvent.click(screen.getByRole("button", { name: "Run the analysis again" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Upload the meeting transcript first");
  });
});

describe("BA Studio: the transcript", () => {
  const none = { "GET /projects/1/transcript": { status: 404, body: { error: { code: "NO_TRANSCRIPT", message: "No transcript has been uploaded yet" } } } };
  const empty = baView({ session: null, score: null, history: [], questions: [], can_run: false });

  it("lets the lead paste a transcript, and sends it with its name", async () => {
    let have = false;
    const m = await open("LEAD", empty, {
      "GET /projects/1/transcript": () => (have ? { body: transcript() } : { status: 404, body: { error: { code: "NO_TRANSCRIPT", message: "none" } } }),
      "POST /projects/1/transcripts": () => { have = true; return { status: 201, body: { id: 1 } }; },
    });
    const send = await screen.findByRole("button", { name: "Upload the transcript" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Transcript text"), { target: { value: "  \n " } });
    expect(send.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Transcript text"), { target: { value: "Lakshmi: hello\nRavi: hi" } });
    fireEvent.change(screen.getByLabelText("Where it came from"), { target: { value: "  meeting.txt " } });
    fireEvent.click(send);
    await waitFor(() => expect(m.calls.some((c) => c.method === "POST")).toBe(true));
    expect(body(m.calls.find((c) => c.method === "POST")!)).toEqual({ text: "Lakshmi: hello\nRavi: hi", source_name: "meeting.txt" });
    await waitFor(() => expect(screen.queryByText("No transcript yet")).toBeNull());
  });

  it("tells others that the lead has not uploaded it yet, with no form", async () => {
    await open("SPONSOR", empty, none);
    expect(await screen.findByText("The lead has not uploaded the meeting transcript yet.")).toBeTruthy();
    expect(screen.queryByLabelText("Transcript text")).toBeNull();
    expect(screen.queryByText("The analysis has not started")).toBeNull();
  });

  it("shows the server's reason when the upload is refused, and keeps the text", async () => {
    await open("LEAD", empty, { ...none, "POST /projects/1/transcripts": { status: 422, body: { error: { code: "TRANSCRIPT_TOO_BIG", message: "That transcript is too long" } } } });
    fireEvent.change(await screen.findByLabelText("Transcript text"), { target: { value: "text" } });
    fireEvent.click(screen.getByRole("button", { name: "Upload the transcript" }));
    expect((await screen.findByRole("alert")).textContent).toBe("That transcript is too long");
    expect((screen.getByLabelText("Transcript text") as HTMLTextAreaElement).value).toBe("text");
  });

  it("does not offer an upload when the transcript is there", async () => {
    await open();
    expect(screen.queryByText("No transcript yet")).toBeNull();
  });
});

describe("BA Studio: access", () => {
  it("asks people who are not signed in to sign in, without calling the API", async () => {
    const m = mockFetch({});
    wrapped(<BaPage />);
    expect(await screen.findByText("Sign in to open BA Studio")).toBeTruthy();
    expect(m.calls).toHaveLength(0);
  });

  it("waits for the sign-in check before deciding", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me(), delayMs: 100 }, "GET /projects/1/ba": { body: baView() }, "GET /projects/1/transcript": { body: transcript() }, "GET /projects/1": { body: detail() } });
    wrapped(<BaPage />);
    expect(screen.getByText("Checking who you are...")).toBeTruthy();
    expect(screen.queryByText("Sign in to open BA Studio")).toBeNull();
    await screen.findByRole("heading", { name: "BA Studio" });
  });

  it("shows the server's reason when the person is not on the project", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me() }, "GET /projects/1/ba": { status: 403, body: { error: { code: "FORBIDDEN", message: "You are not on this project" } } }, "GET /projects/1/transcript": { status: 403, body: { error: { code: "FORBIDDEN", message: "x" } } }, "GET /projects/1": { body: detail() } });
    wrapped(<BaPage />);
    expect(await screen.findByText("You are not on this project")).toBeTruthy();
  });

  it("asks for a project when the address has no valid id", async () => {
    for (const q of ["", "id=abc", "id=-1", "id=1234567890"]) {
      nav.query = q;
      const { unmount } = wrapped(<BaPage />);
      expect(await screen.findByText("No project selected")).toBeTruthy();
      unmount();
    }
  });

  it("reloads when a different person signs in", async () => {
    setToken("tok");
    let who = 0;
    const ravi = { id: 2, email: "ravi@velugu.example.com", display_name: "Ravi" };
    const m = mockFetch({
      "GET /auth/me": () => ({ body: who === 0 ? me() : { user: ravi, memberships: [{ member_id: 2, project_id: 1, role: "SPONSOR" }] } }),
      "POST /auth/login": () => { who = 1; return { body: { token: "tok2", user: ravi } }; },
      "GET /projects/1/ba": { body: baView() }, "GET /projects/1/transcript": { body: transcript() }, "GET /projects/1": { body: detail() },
    });
    const { Switch } = await import("./switch");
    wrapped(<><BaPage /><Switch /></>);
    await screen.findByRole("heading", { name: "BA Studio" });
    const count = (p: string) => m.calls.filter((c) => c.path === p).length;
    const before = [count("/projects/1/ba"), count("/projects/1/transcript"), count("/projects/1")];
    fireEvent.click(screen.getByRole("button", { name: "switch person" }));
    await waitFor(() => expect([count("/projects/1/ba"), count("/projects/1/transcript"), count("/projects/1")]).toEqual(before.map((n) => n + 1)));
  });

  it("the Refresh button asks again", async () => {
    const m = await open();
    const before = m.calls.filter((c) => c.path === "/projects/1/ba").length;
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(m.calls.filter((c) => c.path === "/projects/1/ba").length).toBe(before + 1));
  });
});

// last on purpose: these fake the clock
describe("BA Studio: waiting for news", () => {
  it("refreshes on a timer while visible, not while hidden, and keeps the view when a refresh fails", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    let fail = false;
    await open("LEAD", baView(), { "GET /projects/1/ba": () => { n += 1; return fail ? { status: 500, body: { error: { code: "X", message: "boom" } } } : { body: baView() }; } });
    const first = n;
    await act(async () => { await vi.advanceTimersByTimeAsync(BA_REFRESH_MS - 1000); });
    expect(n).toBe(first);
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(n).toBe(first + 1);
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(BA_REFRESH_MS * 2); });
    expect(n).toBe(first + 1);
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    fail = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(BA_REFRESH_MS + 100); });
    expect(await screen.findByText(/Could not refresh just now \(boom\)/)).toBeTruthy();
    expect(screen.getByTestId("score").textContent).toBe("58");
  });

  it("asks about a run it started until it is done, then loads the new score", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let polls = 0;
    let scored = false;
    const m = await open("LEAD", baView({ can_run: true }), {
      "GET /projects/1/ba": () => ({ body: scored ? baView({ score: baScore({ total: 79 }), session: { id: 1, state: "ACTIVE", round: 1, current_score: 79, target_score: 90, max_rounds: 5 } }) : baView({ can_run: true }) }),
      "POST /projects/1/ba/run": { status: 202, body: { job_id: 7 } },
      "GET /jobs/7": () => { polls += 1; if (polls >= 2) scored = true; return { body: { state: polls >= 2 ? "DONE" : "RUNNING", result: null, error: null, attempts: 1 } }; },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run the analysis again" }));
    expect(await screen.findByText("The analyst is working. This takes a short while.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Run the analysis again" }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    expect(polls).toBe(1);
    expect(screen.getByText("The analyst is working. This takes a short while.")).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS); });
    await waitFor(() => expect(screen.getByTestId("score").textContent).toBe("79"));
    expect(screen.queryByText("The analyst is working. This takes a short while.")).toBeNull();
    const seen = polls;
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS * 4); });
    expect(polls).toBe(seen);                                                   // it stops asking once the job is done
    expect(m.calls.filter((c) => c.method === "POST")).toHaveLength(1);
  });

  it("does not ask about any job before a run has been started", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const m = await open("LEAD", baView({ can_run: true }));
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS * 3); });
    expect(m.calls.some((c) => c.path.startsWith("/jobs"))).toBe(false);
  });

  it("says so when the run failed, with the reason, and loads the view again", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const m = await open("LEAD", baView({ can_run: true }), {
      "POST /projects/1/ba/run": { status: 202, body: { job_id: 8 } },
      "GET /jobs/8": { body: { state: "FAILED", result: null, error: "AgentError: no valid answer", attempts: 3 } },
    });
    const before = m.calls.filter((c) => c.path === "/projects/1/ba").length;
    fireEvent.click(screen.getByRole("button", { name: "Run the analysis again" }));
    await screen.findByText("The analyst is working. This takes a short while.");
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    await waitFor(() => expect(m.calls.filter((c) => c.path === "/projects/1/ba").length).toBe(before + 1));
    expect((await screen.findByRole("alert")).textContent).toBe("The analysis failed: AgentError: no valid answer");
    expect(screen.queryByText("The analyst is working. This takes a short while.")).toBeNull();
  });

  it("says so, without a reason, when a failed run gave none", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await open("LEAD", baView({ can_run: true }), { "POST /projects/1/ba/run": { status: 202, body: { job_id: 8 } }, "GET /jobs/8": { body: { state: "FAILED", result: null, error: null, attempts: 3 } } });
    fireEvent.click(screen.getByRole("button", { name: "Run the analysis again" }));
    await screen.findByText("The analyst is working. This takes a short while.");
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    expect((await screen.findByRole("alert")).textContent).toBe("The analysis failed.");
  });

  it("stops waiting and says why when the job cannot be asked about", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await open("LEAD", baView({ can_run: true }), { "POST /projects/1/ba/run": { status: 202, body: { job_id: 9 } }, "GET /jobs/9": { status: 404, body: { error: { code: "JOB_NOT_FOUND", message: "No such job" } } } });
    fireEvent.click(screen.getByRole("button", { name: "Run the analysis again" }));
    await screen.findByText("The analyst is working. This takes a short while.");
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    expect((await screen.findByRole("alert")).textContent).toBe("No such job");
    expect(screen.queryByText("The analyst is working. This takes a short while.")).toBeNull();
  });
});
