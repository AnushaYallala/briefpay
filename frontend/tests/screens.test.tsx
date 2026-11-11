import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BrdPage from "@/app/brd/page";
import SubmitPage from "@/app/submit/page";
import VerifyPage from "@/app/verify/page";
import { AuthProvider } from "@/lib/auth";
import { clearToken, setToken } from "@/lib/token";
import { BRD_STATUS, brdIsOpen, brdStatus, checkTarget } from "@/lib/verifyview";
import { brdView, lakshmi, mockFetch, project, subDetail, subItem } from "./helpers";

// Tests for the brief, submit and verify screens: what they show is what the API really sends.
const nav = vi.hoisted(() => ({ query: "id=1" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams(nav.query) }));

beforeEach(() => { clearToken(); nav.query = "id=1"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); clearToken(); });

const members = [
  { id: 1, role: "LEAD", display_name: "Lakshmi", email: "lakshmi@velugu.example.com", business_name: null, business_type: null },
  { id: 2, role: "SPONSOR", display_name: "Ravi", email: "ravi@velugu.example.com", business_name: null, business_type: null },
];
const detail = (state = "BRD_REVIEW", role = "LEAD") => ({ ...project({ state }), delivery_days: 5, payout_release_policy: "HUMAN", created_at: "2026-11-09T10:00:00", members, viewer: { role, member_id: 1 } });
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const body = (c: { init: RequestInit }) => JSON.parse(String(c.init.body));
const me = (memberships: { member_id: number; project_id: number; role: string }[], user = lakshmi) => ({ user, memberships });

describe("the words and helpers", () => {
  it("has words for every brief status and says which one is open for decisions", () => {
    expect(Object.keys(BRD_STATUS).sort()).toEqual(["APPROVED", "DRAFT", "PENDING_APPROVAL", "SUPERSEDED"]);
    expect(brdStatus("PENDING_APPROVAL")).toEqual({ label: "Waiting for the sponsors", tone: "amber" });
    expect(brdStatus("APPROVED")).toEqual({ label: "Approved and locked", tone: "green" });
    expect(brdStatus("SUPERSEDED")).toEqual({ label: "Replaced by a newer version", tone: "grey" });
    expect(brdStatus("DRAFT").tone).toBe("grey");
    expect(brdStatus("ODD")).toEqual({ label: "ODD", tone: "grey" });
    expect(["PENDING_APPROVAL", "APPROVED", "SUPERSEDED", "DRAFT", "LOCKED"].map(brdIsOpen)).toEqual([true, false, false, false, false]);
  });

  it("describes what a check looked at, and nothing for the repository and commit checks", () => {
    expect(checkTarget({ deployed_url: "https://x.example", path: "/stay" })).toBe("/stay");
    expect(checkTarget({ deployed_url: "https://x.example", path: "/menu", text: "Fish" })).toBe("/menu contains “Fish”");
    expect(checkTarget({ path: "/menu", text: "" })).toBe("/menu");
    expect(checkTarget({ repo_url: "https://github.com/a/b", commit_sha: "abc", path: "src/app.ts" })).toBe("src/app.ts");
    for (const none of [{}, null, undefined, { path: 5 }, { text: "x" }]) expect(checkTarget(none as never), JSON.stringify(none)).toBe("");
  });
});

describe("the brief screen", () => {
  async function open(memberships: { member_id: number; project_id: number; role: string }[], view = brdView(), user = lakshmi, state = "BRD_REVIEW") {
    setToken("tok");
    const m = mockFetch({
      "GET /auth/me": { body: me(memberships, user) }, "GET /projects/1/brd": { body: view }, "GET /projects/1": { body: detail(state) },
      "POST /projects/1/brd/1/decision": { body: {} },
    } as never);
    wrapped(<BrdPage />);
    await screen.findByText("Business Requirements Document");
    return m;
  }
  const lead = [{ member_id: 1, project_id: 1, role: "LEAD" }];

  it("shows a version waiting for decisions in words, and offers a sponsor the decision", async () => {
    await open(lead);
    expect(screen.getByText("Waiting for the sponsors")).toBeTruthy();
    expect(screen.queryByText("PENDING_APPROVAL")).toBeNull();
    expect(screen.getByRole("button", { name: /Approve BRD/ })).toBeTruthy();
  });

  it("sends the decision with the exact fingerprint of the version that was read", async () => {
    const m = await open(lead);
    fireEvent.click(screen.getByRole("button", { name: /Approve BRD/ }));
    await waitFor(() => expect(m.calls.some((c) => c.method === "POST")).toBe(true));
    const post = m.calls.find((c) => c.method === "POST")!;
    expect(post.path).toBe("/projects/1/brd/1/decision");
    expect(body(post)).toEqual({ decision: "APPROVE", brd_sha256: "a".repeat(64), comment: null });
  });

  it("shows an approved version as locked, and a replaced one as replaced, with no decision form for either", async () => {
    await open(lead, brdView({ status: "APPROVED" }));
    expect(screen.getByText("Approved and locked").className).toContain("green");
    expect(screen.queryByRole("button", { name: /Approve BRD/ })).toBeNull();
    cleanup();
    await open(lead, brdView({ status: "SUPERSEDED" }));
    expect(screen.getByText("Replaced by a newer version")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Approve BRD/ })).toBeNull();
  });

  it("offers no decision to a supporter, a freelancer, a stranger, or someone who already decided", async () => {
    for (const role of ["SUPPORTER", "FREELANCER"]) {
      cleanup();
      await open([{ member_id: 3, project_id: 1, role }]);
      expect(screen.queryByRole("button", { name: /Approve BRD/ }), role).toBeNull();
    }
    cleanup();
    await open([]);
    expect(screen.queryByRole("button", { name: /Approve BRD/ })).toBeNull();
    cleanup();
    await open([{ member_id: 2, project_id: 1, role: "SPONSOR" }]);                             // Ravi, who already approved in the fixture
    expect(screen.queryByRole("button", { name: /Approve BRD/ })).toBeNull();
  });

  it("does not take someone for a sponsor because their name or email matches a member's", async () => {
    const stranger = { id: 99, email: "lakshmi@velugu.example.com", display_name: "Lakshmi" };      // same name and email as the lead, but not on this project
    await open([{ member_id: 7, project_id: 2, role: "LEAD" }], brdView(), stranger);
    expect(screen.queryByRole("button", { name: /Approve BRD/ })).toBeNull();
  });

  it("renders every chapter of the BRD specification like a structured book without leaking emails", async () => {
    await open(lead);
    expect(screen.getByRole("complementary", { name: "Table of contents" })).toBeTruthy();
    const book = screen.getByRole("article", { name: "Specification book" });
    const text = book.textContent ?? "";
    for (const expected of [
      "Executive summary",
      "One website for the whole cove.",
      "Business goals and success measures",
      "More enquiries",
      "20 enquiries a month",
      "Stakeholders",
      "Sea Breeze Homestay",
      "Show the rooms",
      "Audience",
      "Tourists planning a trip",
      "Site structure",
      "/stay",
      "Requirements",
      "REQ-001",
      "the page / loads",
      "Non-functional requirements",
      "Works on a phone",
      "Who provides the content",
      "Photos of the rooms",
      "Constraints",
      "$400.00",
      "5 days",
      "velugucove.example",
      "Out of scope",
      "Online payments",
      "Open items",
      "Hosting is not decided",
      "Glossary",
      "A message from a visitor",
    ]) {
      expect(text, expected).toContain(expected);
    }
    expect(text).not.toContain("@");
  });
});

describe("the submit and verify screens", () => {
  async function open(Page: () => React.JSX.Element, sub = subDetail()) {
    setToken("tok");
    mockFetch({
      "GET /auth/me": { body: me([{ member_id: 1, project_id: 1, role: "LEAD" }]) }, "GET /projects/1": { body: detail("VERIFYING") },
      "GET /projects/1/contract": { body: { id: 1, status: "SIGNED", amount_cents: 40000, currency: "USD", delivery_days: 5, conditional: true, terms_md: "t", terms_sha256: "h", brd_version: 1, brd_sha256: "b", freelancer_member_id: 3, signed_at: "2026-11-10T10:00:00", effective_at: null } },
      "GET /projects/1/submissions": { body: { submissions: [subItem()] } }, "GET /submissions/5": { body: sub },
    } as never);
    wrapped(<Page />);
  }

  it.each([["submit", SubmitPage], ["verify", VerifyPage]] as const)("the %s screen says what each automatic check looked at, never 'undefined'", async (_name, Page) => {
    await open(Page);
    expect(await screen.findByText(/URL_REACHABLE/)).toBeTruthy();
    const text = document.body.textContent ?? "";
    expect(text).toContain("/menu contains “Fish”");
    expect(text).toContain("/stay");
    expect(text).toContain("REPO_PUBLIC");
    expect(text).not.toContain("undefined");
    expect(text).not.toContain("[object Object]");
  });

  it("the submit screen writes the check type and what it looked at, with no stray colon for the repository check", async () => {
    await open(SubmitPage);
    await screen.findByText(/URL_REACHABLE/);
    const rows = Array.from(document.querySelectorAll("span")).map((s) => s.textContent ?? "");
    expect(rows).toContain("PAGE_CONTAINS: /menu contains “Fish”");
    expect(rows).toContain("URL_REACHABLE: /stay");
    expect(rows).toContain("REPO_PUBLIC");
  });
});
