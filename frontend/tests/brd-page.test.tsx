import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BrdPage from "@/app/brd/page";
import { AuthProvider } from "@/lib/auth";
import { BRD_REFRESH_MS } from "@/lib/brd";
import { JOB_POLL_MS } from "@/lib/ba";
import { clearToken, setToken } from "@/lib/token";
import { brdReq, brdView, lakshmi, mockFetch, project } from "./helpers";

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

const members = [
  { id: 1, role: "LEAD", display_name: "Lakshmi", business_name: null, business_type: null },
  { id: 2, role: "SPONSOR", display_name: "Ravi", business_name: null, business_type: null },
];
const detail = (state = "BRD_REVIEW") => ({ ...project({ state }), delivery_days: 5, payout_release_policy: "HUMAN", created_at: "2026-11-09T10:00:00", members, viewer: null });
const me = (role: string) => ({ user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role }] });
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const body = (c: { init: RequestInit }) => JSON.parse(String(c.init.body));
const rows = () => Array.from(document.querySelectorAll(".ag-grid-scrolling-container .ag-row"));
const posts = (m: { calls: { method: string; path: string; init: RequestInit }[] }) => m.calls.filter((c) => c.method === "POST");

async function open(role: string | null = null, view = brdView(), state = "BRD_REVIEW", routes: Record<string, unknown> = {}) {
  if (role) setToken("tok");
  const m = mockFetch({ ...(role ? { "GET /auth/me": { body: me(role) } } : {}), "GET /projects/1/brd": { body: view }, "GET /projects/1": { body: detail(state) }, ...routes } as never);
  wrapped(<BrdPage />);
  await screen.findByTestId("title");
  return m;
}

describe("the brief, as anyone reads it", () => {
  it("shows the version, state, fingerprint, summary, goals and audience", async () => {
    await open();
    expect(screen.getByTestId("title").textContent).toBe("Velugu Cove tourism website · version 1");
    expect(screen.getByText("Waiting for the sponsors")).toBeTruthy();
    expect(screen.getByText(/Every sponsor must approve this exact document/)).toBeTruthy();
    const fp = screen.getByTitle("a".repeat(64));
    expect(fp.textContent).toBe("a".repeat(12));
    expect(screen.getByText(/Written when the analysis scored 93\./)).toBeTruthy();
    const summary = screen.getByRole("region", { name: "Summary" });
    expect(summary.textContent).toContain("One website for the whole cove.");
    expect(within(summary).getByRole("region", { name: "Goals" }).textContent).toContain("More enquiries");
    expect(within(summary).getByRole("region", { name: "How we will know it worked" }).textContent).toContain("20 enquiries a month");
    expect(summary.textContent).toContain("Tourists planning a trip");
    expect(screen.getByText("Download as text").getAttribute("href")).toBe("http://api.test/api/projects/1/brd/1.md");
  });

  it("names the sponsors and their needs, the pages, and who provides what", async () => {
    await open();
    const st = screen.getByRole("region", { name: "Stakeholders" });
    expect(st.textContent).toContain("Lakshmi (Sea Breeze Homestay)");
    expect(st.textContent).toContain("Show the rooms");
    expect(st.textContent).toContain("Ravi");
    expect(st.textContent).not.toContain("Ravi (");
    const pages = screen.getByRole("region", { name: "Pages" });
    expect(pages.textContent).toContain("/stay");
    expect(pages.textContent).toContain("Rooms");
    const who = screen.getByRole("region", { name: "Content to provide" });
    expect(who.textContent).toContain("Photos of the rooms: Lakshmi, by Nov 20");
    expect(who.textContent).toContain("Menu text: nobody yet");
    expect(who.textContent).not.toContain("Menu text: nobody yet, by");
  });

  it("shows terms, out of scope, non-functional needs, the glossary and what is still open", async () => {
    await open();
    const d = screen.getByRole("region", { name: "Details" });
    expect(d.textContent).toContain("Budget$400.00");
    expect(d.textContent).toContain("Delivery time5 days");
    expect(d.textContent).toContain("Hostingnot set");
    expect(d.textContent).toContain("Domainvelugucove.example");
    expect(within(d).getByRole("region", { name: "Out of scope" }).textContent).toContain("Online payments");
    expect(within(d).getByRole("region", { name: "Non-functional needs" }).textContent).toContain("Works on a phone");
    expect(within(d).getByRole("region", { name: "Glossary" }).textContent).toContain("Enquiry: A message from a visitor");
    expect(screen.getByRole("region", { name: "Open items" }).textContent).toContain("Hosting is not decided");
  });

  it("leaves out sections that are empty, and says 'not set' for a missing delivery time", async () => {
    const v = brdView();
    v.content = { ...v.content, stakeholders: [], content_responsibilities: [], glossary: [], out_of_scope: [], non_functional: [], constraints: { ...v.content.constraints, delivery_days: null, domain: null, hosting: "Render" } };
    v.open_items = [];
    await open(null, v);
    for (const name of ["Stakeholders", "Content to provide", "Glossary", "Out of scope", "Non-functional needs", "Open items"]) expect(screen.queryByRole("region", { name }), name).toBeNull();
    const d = screen.getByRole("region", { name: "Details" });
    expect(d.textContent).toContain("Delivery timenot set");
    expect(d.textContent).toContain("HostingRender");
    expect(d.textContent).toContain("Domainnot set");
  });

  it("shows the decisions by name and who is still to decide, but no form to a visitor", async () => {
    await open();
    expect(screen.getByTestId("progress").textContent).toBe("1 of 2 sponsors approved");
    const [only] = within(screen.getByRole("list", { name: "Decisions" })).getAllByRole("listitem");
    expect(only.getAttribute("data-decision")).toBe("APPROVE");
    expect(only.textContent).toContain("Approved");
    expect(only.textContent).toContain("Ravi: “Looks right”");
    expect(screen.getByTestId("awaiting").textContent).toBe("Still to decide: Lakshmi.");
    expect(screen.getByTestId("not-yours")).toBeTruthy();
    expect(screen.queryByLabelText("Your comment")).toBeNull();
    expect(screen.queryByRole("button", { name: /Write/ })).toBeNull();
  });

  it("shows a rejection in red words, a decision without a comment, and nobody waiting", async () => {
    const v = brdView({ approvals: [{ member_id: 2, member_name: null, decision: "REJECT", comment: null, created_at: "2026-11-10T13:00:00" }], awaiting: [] });
    await open(null, v);
    const [only] = within(screen.getByRole("list", { name: "Decisions" })).getAllByRole("listitem");
    expect(only.textContent).toContain("Asked for changes");
    expect(only.textContent).toContain("Someone");
    expect(only.textContent).not.toContain("“");
    expect(screen.queryByTestId("awaiting")).toBeNull();
    expect(screen.getByTestId("progress").textContent).toBe("0 of 0 sponsors approved");
    expect(within(only).getByText("Asked for changes").className).toContain("bg-red-100");
  });

  it("shows an approved version as locked, with when", async () => {
    await open(null, brdView({ status: "APPROVED", locked_at: "2026-11-10T14:00:00", awaiting: [], approvals: [brdView().approvals[0], { ...brdView().approvals[0], member_id: 1, member_name: "Lakshmi" }] }));
    expect(screen.getByText("Approved and locked").className).toContain("bg-green-100");
    expect(screen.getByText(/Locked Nov 10, 14:00 UTC\./)).toBeTruthy();
    expect(screen.queryByTestId("not-yours")).toBeNull();
    expect(screen.getByTestId("progress").textContent).toBe("2 of 2 sponsors approved");
  });

  it("does not claim a score or a lock time that is missing", async () => {
    await open(null, brdView({ score_at_generation: null }));
    expect(screen.queryByText(/Written when the analysis scored/)).toBeNull();
    expect(screen.queryByText(/Locked /)).toBeNull();
  });

  it("calls an untitled brief untitled", async () => {
    const v = brdView();
    v.content = { ...v.content, title: "" };
    await open(null, v);
    expect(screen.getByTestId("title").textContent).toBe("Untitled brief · version 1");
  });
});

describe("the requirements table", () => {
  it("lists every requirement with a priority chip, weight, who asked and how many checks", async () => {
    await open();
    await waitFor(() => expect(rows()).toHaveLength(2));
    const text = rows().map((r) => r.textContent ?? "");
    expect(text[0]).toContain("REQ-001");
    expect(text[0]).toContain("Welcome page");
    expect(text[0]).toContain("MUST");
    expect(text[0]).toContain("Lakshmi, Ravi");
    expect(text[1]).toContain("Menu page");
    expect(text[1]).toContain("SHOULD");
    expect(rows().map((r) => r.getAttribute("row-id"))).toEqual(["REQ-001", "REQ-002"]);
    expect(rows()[0].querySelector('[col-id="priority"] span')!.className).toContain("bg-red-100");
    expect(rows()[1].querySelector('[col-id="priority"] span')!.className).toContain("bg-amber-100");
    expect(rows()[0].querySelector('[col-id="checks"]')!.textContent).toBe("1");
    expect(rows()[1].querySelector('[col-id="checks"]')!.textContent).toBe("0");
    expect(rows()[0].querySelector('[col-id="weight"]')!.textContent).toBe("3");
    expect(screen.getByText("Requirements (2)")).toBeTruthy();
    expect(document.querySelector(".ag-root")!.className).toContain("ag-has-left-pinned-cols");
  });

  it("finds requirements by search", async () => {
    await open();
    await waitFor(() => expect(rows()).toHaveLength(2));
    fireEvent.change(screen.getByLabelText("Search the requirements"), { target: { value: "menu" } });
    await waitFor(() => expect(rows()).toHaveLength(1));
    fireEvent.change(screen.getByLabelText("Search the requirements"), { target: { value: "Ravi" } });
    await waitFor(() => expect(rows()).toHaveLength(2));
  });

  it("opens a requirement with its checks, the proof needed and what the platform checks itself", async () => {
    await open();
    await waitFor(() => expect(rows()).toHaveLength(2));
    fireEvent.click(rows()[0].querySelector("button")!);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.getAttribute("aria-label")).toBe("Requirement REQ-001");
    expect(dialog.textContent).toContain("REQ-001: Welcome page");
    expect(dialog.textContent).toContain("A home page that says what Velugu Cove is.");
    expect(dialog.textContent).toContain("Asked for by Lakshmi, Ravi · weight 3 of 5 · from lines 3 to 4");
    const [ac] = within(dialog).getAllByRole("listitem");
    expect(ac.textContent).toContain("AC-1");
    expect(ac.textContent).toContain("Given a visitor opens the site");
    expect(ac.textContent).toContain("When the home page loads");
    expect(ac.textContent).toContain("Then it welcomes them");
    expect(ac.textContent).toContain("Proof: a check of the live page, a screenshot");
    expect(within(dialog).getByTestId("hint").textContent).toBe("The platform can check this itself: The page / opens.");
    expect(within(dialog).getByText("MUST").className).toContain("bg-red-100");
  });

  it("says when a requirement has no checks or sources yet, and when a check cannot be automated", async () => {
    const v = brdView();
    v.content.requirements = [brdReq({ code: "REQ-005", acceptance_criteria: [], source_refs: [], requested_by: [] }), brdReq({ code: "REQ-006", acceptance_criteria: [{ id: "AC-1", given: "g", when: "w", then: "t", evidence: ["TEXT"], auto_check_hint: null }] })];
    await open(null, v);
    await waitFor(() => expect(rows()).toHaveLength(2));
    fireEvent.click(rows()[0].querySelector("button")!);
    let dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("No checks yet.");
    expect(dialog.textContent).toContain("Asked for by nobody yet · weight 3 of 5");
    expect(dialog.textContent).not.toContain(" · from ");
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(rows()[1].querySelector("button")!);
    dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByTestId("hint")).toBeNull();
    expect(dialog.textContent).toContain("Proof: a written note");
  });

  it("closes with Escape, the button or a click outside, but not on a click inside or another key", async () => {
    await open();
    await waitFor(() => expect(rows()).toHaveLength(2));
    const openIt = async () => { fireEvent.click(rows()[0].querySelector("button")!); return screen.findByRole("dialog"); };
    let d = await openIt();
    fireEvent.click(d);
    fireEvent.keyDown(window, { key: "Enter" });
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    d = await openIt();
    fireEvent.click(d.parentElement!);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    d = await openIt();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("deciding on the brief", () => {
  it("approves the exact document that was read, with an optional comment, and says what happened", async () => {
    const m = await open("SPONSOR", brdView(), "BRD_REVIEW", { "POST /projects/1/brd/1/decision": { body: { changed: true, brd_version: 1, brd_status: "PENDING_APPROVAL", project_state: "BRD_REVIEW", approved: 2, required: 3, locked: false } } });
    expect(screen.getByTestId("why-not-reject").textContent).toBe("To ask for changes, say what should change.");
    fireEvent.change(screen.getByLabelText("Your comment"), { target: { value: "  Good  " } });
    fireEvent.click(screen.getByRole("button", { name: "Approve this version" }));
    expect((await screen.findByRole("status")).textContent).toBe("Your approval is recorded. 2 of 3 sponsors approved.");
    expect(posts(m)[0].path).toBe("/projects/1/brd/1/decision");
    expect(body(posts(m)[0])).toEqual({ decision: "APPROVE", brd_sha256: "a".repeat(64), comment: "Good" });
    expect((screen.getByLabelText("Your comment") as HTMLTextAreaElement).value).toBe("");
  });

  it("sends no comment key when there is none, and tells everyone when the last approval locks it", async () => {
    const m = await open("LEAD", brdView(), "BRD_REVIEW", { "POST /projects/1/brd/1/decision": { body: { changed: true, brd_version: 1, brd_status: "APPROVED", project_state: "CONTRACTING", approved: 2, required: 2, locked: true } } });
    fireEvent.click(screen.getByRole("button", { name: "Approve this version" }));
    expect((await screen.findByRole("status")).textContent).toBe("Every sponsor approved. The brief is locked and the contract comes next.");
    expect(body(posts(m)[0])).toEqual({ decision: "APPROVE", brd_sha256: "a".repeat(64) });
  });

  it("makes asking for changes wait for a comment, then sends it", async () => {
    const m = await open("LEAD", brdView(), "BRD_REVIEW", { "POST /projects/1/brd/1/decision": { body: { changed: true, brd_version: 1, brd_status: "SUPERSEDED", project_state: "REQUIREMENTS", approved: 0, required: 2, locked: false } } });
    const reject = screen.getByRole("button", { name: "Ask for changes" }) as HTMLButtonElement;
    expect(reject.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Your comment"), { target: { value: "   " } });
    expect(reject.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Your comment"), { target: { value: " Add a gallery " } });
    expect(reject.disabled).toBe(false);
    expect(screen.queryByTestId("why-not-reject")).toBeNull();
    fireEvent.click(reject);
    expect((await screen.findByRole("status")).textContent).toBe("Your request for changes is recorded. The analyst will ask how the brief should change.");
    expect(body(posts(m)[0])).toEqual({ decision: "REJECT", brd_sha256: "a".repeat(64), comment: "Add a gallery" });
    expect((screen.getByLabelText("Your comment") as HTMLTextAreaElement).value).toBe("");
  });

  it("reminds a person of their earlier decision", async () => {
    await open("SPONSOR", brdView({ approvals: [{ member_id: 1, member_name: "Lakshmi", decision: "APPROVE", comment: null, created_at: "2026-11-10T13:00:00" }] }));
    expect(screen.getByTestId("mine").textContent).toBe("You approved this version. You can change your mind while it is open.");
    cleanup();
    await open("SPONSOR", brdView({ approvals: [{ member_id: 1, member_name: "Lakshmi", decision: "REJECT", comment: "x", created_at: "2026-11-10T13:00:00" }] }));
    expect(screen.getByTestId("mine").textContent).toBe("You asked for changes to this version. You can change your mind while it is open.");
    cleanup();
    await open("SPONSOR", brdView({ approvals: [{ member_id: 2, member_name: "Ravi", decision: "APPROVE", comment: null, created_at: "x" }] }));
    expect(screen.queryByTestId("mine")).toBeNull();
  });

  it("limits the comment length", async () => {
    await open("LEAD");
    expect(screen.getByLabelText("Your comment").getAttribute("maxlength")).toBe("2000");
  });

  it("shows the server's reason when a decision is refused, keeps the comment, and re-reads the brief when the text changed under the reader", async () => {
    let n = 0;
    const m = await open("LEAD", brdView(), "BRD_REVIEW", {
      "GET /projects/1/brd": () => { n += 1; return { body: brdView() }; },
      "POST /projects/1/brd/1/decision": { status: 409, body: { error: { code: "HASH_MISMATCH", message: "That is not the document you are deciding on", details: { current_sha256: "b".repeat(64) } } } },
    });
    const before = n;
    fireEvent.change(screen.getByLabelText("Your comment"), { target: { value: "Fine" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve this version" }));
    expect((await screen.findByRole("alert")).textContent).toBe("That is not the document you are deciding on");
    await waitFor(() => expect(n).toBe(before + 1));
    expect((screen.getByLabelText("Your comment") as HTMLTextAreaElement).value).toBe("Fine");
    expect(posts(m)).toHaveLength(1);
  });

  it("does not re-read the brief for other refusals", async () => {
    let n = 0;
    await open("LEAD", brdView(), "BRD_REVIEW", { "GET /projects/1/brd": () => { n += 1; return { body: brdView() }; }, "POST /projects/1/brd/1/decision": { status: 409, body: { error: { code: "BRD_CLOSED", message: "No longer open" } } } });
    const before = n;
    fireEvent.click(screen.getByRole("button", { name: "Approve this version" }));
    expect((await screen.findByRole("alert")).textContent).toBe("No longer open");
    await new Promise((r) => setTimeout(r, 60));
    expect(n).toBe(before);
  });

  it("clears an earlier problem or message when the next try starts", async () => {
    let k = 0;
    await open("LEAD", brdView(), "BRD_REVIEW", { "POST /projects/1/brd/1/decision": () => (k++ === 0 ? { status: 409, body: { error: { code: "X", message: "Try later" } } } : { body: { changed: true, brd_version: 1, brd_status: "PENDING_APPROVAL", project_state: "BRD_REVIEW", approved: 1, required: 2, locked: false } }) });
    fireEvent.click(screen.getByRole("button", { name: "Approve this version" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Try later");
    fireEvent.click(screen.getByRole("button", { name: "Approve this version" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect((await screen.findByRole("status")).textContent).toContain("Your approval is recorded");
  });

  it("will not send a decision twice while the first is on its way", async () => {
    const m = await open("LEAD", brdView(), "BRD_REVIEW", { "POST /projects/1/brd/1/decision": { body: { changed: true, brd_version: 1, brd_status: "PENDING_APPROVAL", project_state: "BRD_REVIEW", approved: 1, required: 2, locked: false }, delayMs: 200 } });
    const approve = screen.getByRole("button", { name: "Approve this version" }) as HTMLButtonElement;
    fireEvent.change(screen.getByLabelText("Your comment"), { target: { value: "no" } });
    fireEvent.click(approve);
    await waitFor(() => expect(approve.textContent).toBe("Approving..."));
    expect(approve.disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Ask for changes" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(approve);
    await screen.findByRole("status");
    expect(posts(m)).toHaveLength(1);
  });

  it("shows the 'Sending...' state while asking for changes", async () => {
    await open("LEAD", brdView(), "BRD_REVIEW", { "POST /projects/1/brd/1/decision": { body: { changed: true, brd_version: 1, brd_status: "SUPERSEDED", project_state: "REQUIREMENTS", approved: 0, required: 2, locked: false }, delayMs: 150 } });
    fireEvent.change(screen.getByLabelText("Your comment"), { target: { value: "change it" } });
    const reject = screen.getByRole("button", { name: "Ask for changes" }) as HTMLButtonElement;
    fireEvent.click(reject);
    await waitFor(() => expect(reject.textContent).toBe("Sending..."));
    await screen.findByRole("status");
  });

  it("offers a decision only to the lead and sponsors, on the open version, during review", async () => {
    await open("SPONSOR");
    expect(screen.getByRole("button", { name: "Approve this version" })).toBeTruthy();
    expect(screen.queryByTestId("not-yours")).toBeNull();
    for (const [role, view, state] of [["SUPPORTER", brdView(), "BRD_REVIEW"], ["FREELANCER", brdView(), "BRD_REVIEW"], ["LEAD", brdView({ status: "SUPERSEDED" }), "BRD_REVIEW"], ["LEAD", brdView({ status: "APPROVED" }), "CONTRACTING"], ["LEAD", brdView(), "REQUIREMENTS"]] as const) {
      cleanup();
      await open(role, view, state);
      expect(screen.queryByRole("button", { name: "Approve this version" }), `${role} ${view.status} ${state}`).toBeNull();
    }
    cleanup();
    await open("SUPPORTER");
    expect(screen.getByTestId("not-yours")).toBeTruthy();
  });
});

describe("writing the brief and reading other versions", () => {
  const none = { "GET /projects/1/brd": { status: 404, body: { error: { code: "NO_BRD", message: "No BRD has been generated yet" } } } };

  it("explains that there is no brief yet, and offers to write it to the lead only while gathering requirements", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me("LEAD") }, ...none, "GET /projects/1": { body: detail("REQUIREMENTS") } });
    wrapped(<BrdPage />);
    expect(await screen.findByText("No brief has been written yet")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Write the brief" })).toBeTruthy();
    cleanup();
    for (const [role, state] of [["SPONSOR", "REQUIREMENTS"], ["LEAD", "BRD_REVIEW"], ["LEAD", "PLEDGING"]]) {
      setToken("tok");
      mockFetch({ "GET /auth/me": { body: me(role) }, ...none, "GET /projects/1": { body: detail(state) } });
      wrapped(<BrdPage />);
      await screen.findByText("No brief has been written yet");
      expect(screen.queryByRole("button", { name: "Write the brief" }), `${role} ${state}`).toBeNull();
      cleanup();
    }
  });

  it("shows no brief and no button to a visitor", async () => {
    mockFetch({ ...none, "GET /projects/1": { body: detail("REQUIREMENTS") } });
    wrapped(<BrdPage />);
    expect(await screen.findByText("No brief has been written yet")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the server's reason when writing is refused", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me("LEAD") }, ...none, "GET /projects/1": { body: detail("REQUIREMENTS") }, "POST /projects/1/brd/generate": { status: 409, body: { error: { code: "BA_NOT_READY", message: "The analysis must reach the target score first" } } } });
    wrapped(<BrdPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Write the brief" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The analysis must reach the target score first");
    expect(screen.getByText("No brief has been written yet")).toBeTruthy();
  });

  it("offers a new version to the lead while gathering requirements, with the right words", async () => {
    await open("LEAD", brdView({ status: "SUPERSEDED" }), "REQUIREMENTS");
    expect(screen.getByRole("button", { name: "Write a new version" })).toBeTruthy();
    expect(screen.getByText("Replaced by a newer version")).toBeTruthy();
  });

  it("shows version chips only when there are several, and loads the one chosen", async () => {
    await open("LEAD");
    expect(screen.queryByRole("button", { name: "Version 1" })).toBeNull();
    cleanup();
    const v2 = brdView({ version: 2, sha256: "c".repeat(64), versions: [{ version: 1, status: "SUPERSEDED", sha256: "a".repeat(64) }, { version: 2, status: "PENDING_APPROVAL", sha256: "c".repeat(64) }] });
    const v1 = brdView({ version: 1, status: "SUPERSEDED", versions: v2.versions });
    const m = await open("LEAD", v2, "BRD_REVIEW", { "GET /projects/1/brd?version=1": { body: v1 } });
    expect(screen.getByRole("button", { name: "Version 2" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Version 1" }).getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Version 1" }));
    await waitFor(() => expect(screen.getByTestId("title").textContent).toContain("version 1"));
    expect(m.calls.some((c) => c.path === "/projects/1/brd?version=1")).toBe(true);
    expect(screen.getByRole("button", { name: "Version 1" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Download as text").getAttribute("href")).toContain("/brd/1.md");
  });
});

describe("access and errors", () => {
  it("waits for the sign-in check before deciding what to show", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me("LEAD"), delayMs: 100 }, "GET /projects/1/brd": { body: brdView() }, "GET /projects/1": { body: detail() } });
    wrapped(<BrdPage />);
    expect(screen.getByText("Checking who you are...")).toBeTruthy();
    await screen.findByTestId("title");
    expect(screen.getByRole("button", { name: "Approve this version" })).toBeTruthy();
  });

  it("shows the server's reason when the brief cannot be loaded", async () => {
    mockFetch({ "GET /projects/1/brd": { status: 500, body: { error: { code: "BOOM", message: "The database is down" } } }, "GET /projects/1": { body: detail() } });
    wrapped(<BrdPage />);
    expect(await screen.findByText("The database is down")).toBeTruthy();
  });

  it("asks for a project when the address has no valid id", async () => {
    for (const q of ["", "id=abc", "id=-1", "id=1234567890"]) {
      nav.query = q;
      const { unmount } = wrapped(<BrdPage />);
      expect(await screen.findByText("No project selected")).toBeTruthy();
      unmount();
    }
  });

  it("reloads when a different person signs in", async () => {
    setToken("tok");
    let who = 0;
    const ravi = { id: 2, email: "ravi@velugu.example.com", display_name: "Ravi" };
    const m = mockFetch({
      "GET /auth/me": () => ({ body: who === 0 ? me("LEAD") : { user: ravi, memberships: [{ member_id: 2, project_id: 1, role: "SPONSOR" }] } }),
      "POST /auth/login": () => { who = 1; return { body: { token: "tok2", user: ravi } }; },
      "GET /projects/1/brd": { body: brdView() }, "GET /projects/1": { body: detail() },
    });
    const { Switch } = await import("./switch");
    wrapped(<><BrdPage /><Switch /></>);
    await screen.findByTestId("title");
    const count = (p: string) => m.calls.filter((c) => c.path === p).length;
    const before = [count("/projects/1/brd"), count("/projects/1")];
    fireEvent.click(screen.getByRole("button", { name: "switch person" }));
    await waitFor(() => expect([count("/projects/1/brd"), count("/projects/1")]).toEqual(before.map((n) => n + 1)));
  });
});

// last on purpose: these fake the clock
describe("waiting for news", () => {
  it("refreshes a document waiting for decisions on a timer while visible, not while hidden, and keeps it when a refresh fails", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    let fail = false;
    await open(null, brdView(), "BRD_REVIEW", { "GET /projects/1/brd": () => { n += 1; return fail ? { status: 500, body: { error: { code: "X", message: "boom" } } } : { body: brdView() }; } });
    const first = n;
    await act(async () => { await vi.advanceTimersByTimeAsync(BRD_REFRESH_MS - 1000); });
    expect(n).toBe(first);
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(n).toBe(first + 1);
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(BRD_REFRESH_MS * 2); });
    expect(n).toBe(first + 1);
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    fail = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(BRD_REFRESH_MS + 100); });
    expect(await screen.findByText(/Could not refresh just now \(boom\)/)).toBeTruthy();
    expect(screen.getByTestId("title")).toBeTruthy();
  });

  it("does not ask for news about a document that is no longer waiting", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    await open(null, brdView({ status: "APPROVED" }), "CONTRACTING", { "GET /projects/1/brd": () => { n += 1; return { body: brdView({ status: "APPROVED" }) }; } });
    const first = n;
    await act(async () => { await vi.advanceTimersByTimeAsync(BRD_REFRESH_MS * 3); });
    expect(n).toBe(first);
  });

  it("follows the writing of the brief until it is done, then shows it", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let polls = 0;
    let written = false;
    setToken("tok");
    mockFetch({
      "GET /auth/me": { body: me("LEAD") },
      "GET /projects/1/brd": () => (written ? { body: brdView() } : { status: 404, body: { error: { code: "NO_BRD", message: "none" } } }),
      "GET /projects/1": { body: detail("REQUIREMENTS") },
      "POST /projects/1/brd/generate": { status: 202, body: { job_id: 5 } },
      "GET /jobs/5": () => { polls += 1; if (polls >= 2) written = true; return { body: { state: polls >= 2 ? "DONE" : "RUNNING", result: null, error: null, attempts: 1 } }; },
    });
    wrapped(<BrdPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Write the brief" }));
    expect(await screen.findByText("The brief is being written. This takes a short while.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Write the brief" }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    expect(polls).toBe(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS); });
    expect(await screen.findByTestId("title")).toBeTruthy();
    expect(screen.queryByText("The brief is being written. This takes a short while.")).toBeNull();
    const seen = polls;
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS * 4); });
    expect(polls).toBe(seen);
  });

  it("says so, with the reason, when writing failed", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setToken("tok");
    mockFetch({
      "GET /auth/me": { body: me("LEAD") }, "GET /projects/1/brd": { status: 404, body: { error: { code: "NO_BRD", message: "none" } } }, "GET /projects/1": { body: detail("REQUIREMENTS") },
      "POST /projects/1/brd/generate": { status: 202, body: { job_id: 6 } }, "GET /jobs/6": { body: { state: "FAILED", result: null, error: "AgentError: bad answer", attempts: 3 } },
    });
    wrapped(<BrdPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Write the brief" }));
    await screen.findByText("The brief is being written. This takes a short while.");
    await act(async () => { await vi.advanceTimersByTimeAsync(JOB_POLL_MS + 100); });
    expect((await screen.findByRole("alert")).textContent).toBe("The brief could not be written. It failed: AgentError: bad answer");
    expect(screen.queryByText("The brief is being written. This takes a short while.")).toBeNull();
    expect((screen.getByRole("button", { name: "Write the brief" }) as HTMLButtonElement).disabled).toBe(false);
  });
});
