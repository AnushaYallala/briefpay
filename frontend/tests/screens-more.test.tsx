import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BrdPage from "@/app/brd/page";
import ContractPage from "@/app/contract/page";
import SubmitPage from "@/app/submit/page";
import VerifyPage from "@/app/verify/page";
import { AuthProvider } from "@/lib/auth";
import { clearToken, setToken } from "@/lib/token";
import { leadName, memberName, problemText } from "@/lib/verifyview";
import { brdView, lakshmi, mockFetch, project, subDetail, subItem } from "./helpers";

// More tests for the brief, contract, submit and verify screens: real names, visible failures, and the contract forms.
const nav = vi.hoisted(() => ({ query: "id=1" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams(nav.query) }));

beforeEach(() => { clearToken(); nav.query = "id=1"; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); clearToken(); });

const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const body = (c: { init: RequestInit }) => JSON.parse(String(c.init.body));
const me = (memberships: { member_id: number; project_id: number; role: string }[], user: { id: number; email: string; display_name: string } = lakshmi) => ({ user, memberships });
const people = [
  { id: 1, role: "LEAD", display_name: "Priya", email: "priya@example.com", business_name: null, business_type: null },
  { id: 3, role: "FREELANCER", display_name: "Dev", email: "dev@example.com", business_name: null, business_type: null },
];
const detail = (state: string, role: string | null, budget = 25000) => ({
  ...project({ state }), budget_cents: budget, delivery_days: 5, payout_release_policy: "HUMAN", created_at: "2026-11-09T10:00:00", members: people,
  viewer: role ? { role, member_id: role === "FREELANCER" ? 3 : 1 } : null,
});

describe("helpers for names and problems", () => {
  it("names real people and falls back politely", () => {
    const members = [{ id: 1, role: "LEAD", display_name: "Priya" }, { id: 3, role: "FREELANCER", display_name: "Dev" }];
    expect(memberName(members, 3, "The builder")).toBe("Dev");
    expect(memberName(members, 9, "The builder")).toBe("The builder");
    expect(memberName(members, null, "The builder")).toBe("The builder");
    expect(memberName(undefined, 3, "The builder")).toBe("The builder");
    expect(leadName(members)).toBe("Priya");
    expect(leadName([{ role: "SPONSOR", display_name: "Ravi" }])).toBe("the project lead");
    expect(leadName(undefined)).toBe("the project lead");
  });

  it("shows the server's words for a problem, or the fallback", () => {
    expect(problemText(new Error("Not allowed"))).toBe("Not allowed");
    expect(problemText(new Error(""), "Could not load X.")).toBe("Could not load X.");
    expect(problemText("boom")).toBe("Could not load this just now.");
    expect(problemText(null, "Fallback")).toBe("Fallback");
  });
});

describe("a failed load is shown, not hidden", () => {
  async function open(Page: () => React.JSX.Element, routes: Record<string, unknown>) {
    setToken("tok");
    mockFetch({
      "GET /auth/me": { body: me([{ member_id: 1, project_id: 1, role: "LEAD" }]) }, "GET /projects/1": { body: detail("VERIFYING", "LEAD") },
      "GET /projects/1/contract": { body: { id: 1, status: "SIGNED", amount_cents: 40000, currency: "USD", delivery_days: 5, conditional: true, terms_md: "t", terms_sha256: "h", brd_version: 1, brd_sha256: "b", freelancer_member_id: 3, signed_at: "2026-11-10T10:00:00", effective_at: null } },
      ...routes,
    } as never);
    wrapped(<Page />);
  }
  const boom = (message: string) => ({ status: 500, body: { error: { code: "BOOM", message } } });

  it.each([["submit", SubmitPage], ["verify", VerifyPage]] as const)("the %s screen says why the submissions could not be loaded", async (_n, Page) => {
    await open(Page, { "GET /projects/1/submissions": boom("The database is down") });
    expect((await screen.findByRole("alert")).textContent).toBe("The database is down");
  });

  it.each([["submit", SubmitPage], ["verify", VerifyPage]] as const)("the %s screen says why one submission could not be loaded", async (_n, Page) => {
    await open(Page, { "GET /projects/1/submissions": { body: { submissions: [subItem()] } }, "GET /submissions/5": boom("That submission is gone") });
    expect((await screen.findByRole("alert")).textContent).toBe("That submission is gone");
  });

  it.each([["submit", SubmitPage], ["verify", VerifyPage]] as const)("the %s screen shows no alert when everything loads", async (_n, Page) => {
    await open(Page, { "GET /projects/1/submissions": { body: { submissions: [subItem()] } }, "GET /submissions/5": { body: subDetail() } });
    await screen.findByText(/URL_REACHABLE/);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("the contract screen", () => {
  const contract = (over: Record<string, unknown> = {}) => ({
    id: 1, status: "OFFERED", amount_cents: 25000, currency: "USD", delivery_days: 7, conditional: true, terms_md: "Terms", terms_sha256: "t".repeat(64), brd_version: 1,
    brd_sha256: "b".repeat(64), freelancer_member_id: 3, signed_at: null, effective_at: null, freelancer_paypal_email: null, ...over,
  });
  const noContract = { status: 404, body: { error: { code: "NO_CONTRACT", message: "No contract has been offered yet" } } };

  async function open(role: string | null, contractReply: unknown, budget = 25000, extra: Record<string, unknown> = {}) {
    if (role) setToken("tok");
    const asFreelancer = role === "FREELANCER";
    const m = mockFetch({
      ...(role ? { "GET /auth/me": { body: me([{ member_id: asFreelancer ? 3 : 1, project_id: 1, role }], asFreelancer ? { id: 5, email: "dev@example.com", display_name: "Dev" } : lakshmi) } } : {}),
      "GET /projects/1": { body: detail("CONTRACTING", role, budget) },
      "GET /projects/1/contract": contractReply, "GET /projects/1/brd": { body: brdView() }, ...extra,
    } as never);
    wrapped(<ContractPage />);
    await screen.findByRole("heading", { name: "Contract Agreement" });
    return m;
  }

  it("starts the lead's offer at the project's own budget, not a fixed number, and sends what was typed in cents (whole dollars only)", async () => {
    const m = await open("LEAD", noContract, 25000, { "POST /projects/1/contract/offer": { status: 201, body: {} } });
    const amount = (await screen.findByLabelText("Contract Budget (USD)")) as HTMLInputElement;
    expect(amount.value).toBe("250");
    fireEvent.change(amount, { target: { value: "300" } });
    fireEvent.change(screen.getByLabelText("Delivery Timeframe (Days)"), { target: { value: "9" } });
    fireEvent.click(screen.getByRole("button", { name: "Send Contract Offer to Freelancer" }));
    await waitFor(() => expect(m.calls.some((c) => c.method === "POST")).toBe(true));
    expect(body(m.calls.find((c) => c.method === "POST")!)).toEqual({ amount_cents: 30000, delivery_days: 9 });
  });

  it("sends the project's budget as is when the lead does not change it", async () => {
    const m = await open("LEAD", noContract, 123400, { "POST /projects/1/contract/offer": { status: 201, body: {} } });
    expect(((await screen.findByLabelText("Contract Budget (USD)")) as HTMLInputElement).value).toBe("1234");
    fireEvent.click(screen.getByRole("button", { name: "Send Contract Offer to Freelancer" }));
    await waitFor(() => expect(m.calls.some((c) => c.method === "POST")).toBe(true));
    expect(body(m.calls.find((c) => c.method === "POST")!).amount_cents).toBe(123400);
  });

  it("refuses an amount that is not a positive number, and shows the server's reason otherwise", async () => {
    const m = await open("LEAD", noContract, 25000, { "POST /projects/1/contract/offer": { status: 409, body: { error: { code: "OVER_BUDGET", message: "That is over the project budget" } } } });
    const amount = (await screen.findByLabelText("Contract Budget (USD)")) as HTMLInputElement;
    for (const bad of ["0", "-5"]) {
      fireEvent.change(amount, { target: { value: bad } });
      fireEvent.submit(amount.closest("form")!);
      expect(await screen.findByText("Please enter a valid positive dollar amount."), bad).toBeTruthy();
    }
    expect(m.calls.some((c) => c.method === "POST")).toBe(false);
    fireEvent.change(amount, { target: { value: "999" } });
    fireEvent.click(screen.getByRole("button", { name: "Send Contract Offer to Freelancer" }));
    expect(await screen.findByText("That is over the project budget")).toBeTruthy();
    expect(screen.queryByText("Please enter a valid positive dollar amount.")).toBeNull();
  });

  it("lets the freelancer sign with the exact fingerprints they were shown, and a trimmed PayPal address", async () => {
    const m = await open("FREELANCER", { body: contract() }, 25000, { "POST /projects/1/contract/accept": { body: {} } });
    const email = (await screen.findByLabelText(/Your PayPal Account Email/)) as HTMLInputElement;
    expect(email.value).toBe("");                                                    // the payout address is typed on purpose, never guessed from the login
    fireEvent.change(email, { target: { value: "  dev-paypal@example.com  " } });
    fireEvent.click(screen.getByRole("button", { name: "Sign & Accept Contract" }));
    await waitFor(() => expect(m.calls.some((c) => c.method === "POST")).toBe(true));
    expect(body(m.calls.find((c) => c.method === "POST")!)).toEqual({ paypal_email: "dev-paypal@example.com", brd_sha256: "b".repeat(64), terms_sha256: "t".repeat(64) });
  });

  it("refuses a PayPal address without an @, and shows the server's reason when signing is refused", async () => {
    const m = await open("FREELANCER", { body: contract() }, 25000, { "POST /projects/1/contract/accept": { status: 409, body: { error: { code: "HASH_MISMATCH", message: "The brief changed since you looked" } } } });
    const email = (await screen.findByLabelText(/Your PayPal Account Email/)) as HTMLInputElement;
    fireEvent.change(email, { target: { value: "not-an-address" } });
    fireEvent.submit(email.closest("form")!);
    expect(await screen.findByText("Please enter a valid PayPal account email.")).toBeTruthy();
    expect(m.calls.some((c) => c.method === "POST")).toBe(false);
    fireEvent.change(email, { target: { value: "dev@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign & Accept Contract" }));
    expect(await screen.findByText("The brief changed since you looked")).toBeTruthy();
    expect(screen.queryByText("Please enter a valid PayPal account email.")).toBeNull();
  });

  it("tells everyone else the contract is waiting for the freelancer, with no forms", async () => {
    await open("LEAD", { body: contract() });
    expect(await screen.findByText("Awaiting Freelancer Signature")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Sign & Accept Contract" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Send Contract Offer to Freelancer" })).toBeNull();
  });

  it("names the real freelancer, the terms and the payout address once signed, and offers no forms", async () => {
    await open("LEAD", { body: contract({ status: "SIGNED", signed_at: "2026-11-10T10:00:00", freelancer_paypal_email: "dev-paypal@example.com" }) });
    const banner = await screen.findByRole("region", { name: "Contract signed" });
    expect(banner.textContent).toContain("Dev accepted the delivery terms (7 days, $250.00)");
    expect(banner.textContent).toContain("dev-paypal@example.com");
    expect(banner.textContent).not.toContain("Arjun");
    expect(screen.getByText("Signed & Locked")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Sign & Accept Contract" })).toBeNull();
  });

  it("says 'The builder' when the freelancer cannot be found among the members", async () => {
    await open("LEAD", { body: contract({ status: "SIGNED", signed_at: "2026-11-10T10:00:00", freelancer_member_id: 99 }) });
    expect((await screen.findByRole("region", { name: "Contract signed" })).textContent).toContain("The builder accepted the delivery terms");
  });

  it("shows a visitor that no contract has been offered, and no forms", async () => {
    await open(null, noContract);
    expect(await screen.findByText("No Contract Offered Yet")).toBeTruthy();
    expect(screen.queryByLabelText("Contract Budget (USD)")).toBeNull();
  });
});

describe("the brief screen names the real lead", () => {
  it("says who the brief is waiting for, not a fixed name", async () => {
    setToken("tok");
    mockFetch({
      "GET /auth/me": { body: me([{ member_id: 2, project_id: 1, role: "SPONSOR" }]) },
      "GET /projects/1": { body: { ...detail("REQUIREMENTS", "SPONSOR"), members: [{ id: 1, role: "LEAD", display_name: "Priya", email: null, business_name: null, business_type: null }] } },
      "GET /projects/1/brd": { status: 404, body: { error: { code: "NO_BRD", message: "No BRD has been generated yet" } } },
    } as never);
    wrapped(<BrdPage />);
    expect(await screen.findByText("Awaiting Priya to generate the official BRD.")).toBeTruthy();
    expect(document.body.textContent).not.toContain("Lakshmi");
  });
});
