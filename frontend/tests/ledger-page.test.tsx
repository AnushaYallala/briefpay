import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LedgerPage from "@/app/ledger/page";
import { AuthProvider } from "@/lib/auth";
import { REFRESH_MS } from "@/lib/ledger";
import { clearToken, setToken } from "@/lib/token";
import { ledger, ledgerRow, lakshmi, mockFetch } from "./helpers";

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

const readBlob = (b: Blob) => new Promise<string>((ok, bad) => { const r = new FileReader(); r.onload = () => ok(String(r.result)); r.onerror = bad; r.readAsText(b); });

const rows = [
  ledgerRow({ seq: 1, type: "STATE_CHANGE" }),
  ledgerRow({ seq: 2, type: "PLEDGE_AUTHORIZED", counterparty: "Lakshmi", status: "Held", actor_name: "PayPal", meta: { authorization_id: "SEED-AUTH-1-lak" } }),
  ledgerRow({ seq: 3, type: "PLEDGE_CAPTURED", bucket: "POOL", amount_cents: 15000, running_balance_cents: 15000, counterparty: "Lakshmi", status: "Captured", paypal_ref: "CAPTURE-ABCDEFGHIJKLMNOP", actor_name: "PayPal", meta: { capture_id: "CAPTURE-ABCDEFGHIJKLMNOP", plan_id: 7 } }),
  ledgerRow({ seq: 4, type: "PLEDGE_CAPTURED", bucket: "POOL", amount_cents: 10000, running_balance_cents: 25000, counterparty: "Ravi", status: "Captured", actor_name: "PayPal" }),
  ledgerRow({ seq: 5, type: "PAYOUT_SENT", bucket: "POOL", amount_cents: -25000, running_balance_cents: 0, counterparty: "Arjun", status: "Paid", actor_name: "PayPal" }),
];
const data = (over: Record<string, unknown> = {}) => ledger(rows, { totals: { pool_in_cents: 25000, pool_out_cents: -25000, pool_balance_cents: 0, rows: 5 }, ...over });
const me = { user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role: "LEAD" }] };
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);
const gridRows = () => Array.from(document.querySelectorAll(".ag-grid-scrolling-container .ag-row"));
const pinnedText = () => document.querySelector(".ag-grid-pinned-bottom-rows-container")?.textContent ?? "";

async function open(over: Record<string, unknown> = {}, extra: Record<string, never> = {}) {
  const { calls, fn } = mockFetch({ "GET /projects/1/ledger": { body: data(over) }, ...extra });
  wrapped(<LedgerPage />);
  await screen.findByTestId("ledger-grid");
  await waitFor(() => expect(gridRows().length).toBeGreaterThan(0));
  return { calls, fn };
}

describe("ledger page", () => {
  it("shows every row in order with plain words, signed amounts and the totals row", async () => {
    await open();
    expect(screen.getByRole("heading", { name: "Ledger" })).toBeTruthy();
    expect(screen.getByTestId("balance").textContent).toBe("$0.00");
    expect(gridRows().length).toBe(5);
    const text = gridRows().map((r) => r.textContent ?? "");
    expect(text[0]).toContain("Project step");
    expect(text[1]).toContain("Pledge held");
    expect(text[1]).toContain("–");                                           // a hold is a memo row, not money
    expect(text[2]).toContain("Pledge collected");
    expect(text[2]).toContain("$150.00");
    expect(text[2]).toContain("CAPTURE-AB…");                                  // PayPal reference shortened
    expect(text[2]).toContain("Pool");
    expect(text[4]).toContain("-$250.00");
    expect(text[4]).toContain("Paid to the builder");
    expect(pinnedText()).toContain("Total of 5 rows");
    expect(pinnedText()).toContain("Totals");
    expect(screen.getByText(/in \$250\.00, out \$250\.00/)).toBeTruthy();
    expect(screen.getByText(/a pledge hold is not money until it is collected/)).toBeTruthy();
  });

  it("keeps the rows in sequence order", async () => {
    await open();
    expect(gridRows().map((r) => r.getAttribute("row-id"))).toEqual(["1", "2", "3", "4", "5"]);
  });

  it("filters by type with chips, updates the totals, and shows all again", async () => {
    await open();
    const chip = screen.getByRole("button", { name: "Pledge collected" });
    expect(chip.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(chip);
    await waitFor(() => expect(gridRows().length).toBe(2));
    expect(chip.getAttribute("aria-pressed")).toBe("true");
    expect(pinnedText()).toContain("Total of 2 rows");
    expect(pinnedText()).toContain("$250.00");                                 // 150 + 100
    fireEvent.click(screen.getByRole("button", { name: "Paid to the builder" }));
    await waitFor(() => expect(gridRows().length).toBe(3));
    fireEvent.click(screen.getByText("Show all"));
    await waitFor(() => expect(gridRows().length).toBe(5));
    expect(screen.queryByText("Show all")).toBeNull();
    fireEvent.click(chip);
    fireEvent.click(chip);                                                     // toggling twice leaves nothing chosen
    await waitFor(() => expect(gridRows().length).toBe(5));
  });

  it("offers a chip only for types that exist", async () => {
    await open();
    expect(screen.queryByRole("button", { name: "Refund" })).toBeNull();
    expect(screen.getAllByRole("button").filter((b) => b.hasAttribute("aria-pressed")).map((b) => b.textContent)).toEqual(["Project step", "Pledge held", "Pledge collected", "Paid to the builder"]);
  });

  it("searches across the shown text", async () => {
    await open();
    fireEvent.change(screen.getByLabelText("Search the ledger"), { target: { value: "Ravi" } });
    await waitFor(() => expect(gridRows().length).toBe(1));
    expect(gridRows()[0].textContent).toContain("Ravi");
    fireEvent.change(screen.getByLabelText("Search the ledger"), { target: { value: "" } });
    await waitFor(() => expect(gridRows().length).toBe(5));
  });

  it("opens the full record of a row and closes it three ways", async () => {
    await open();
    const buttons = screen.getAllByRole("button", { name: "Details" });
    expect(buttons.length).toBe(5);                                            // not on the totals row
    fireEvent.click(buttons[2]);
    const dialog = await screen.findByRole("dialog", { name: "Ledger row 3" });
    expect(within(dialog).getByText(/Row 3: Pledge collected/)).toBeTruthy();
    expect(within(dialog).getByTestId("meta-json").textContent).toContain('"capture_id": "CAPTURE-ABCDEFGHIJKLMNOP"');
    expect(within(dialog).getByTestId("meta-json").textContent).toContain('"plan_id": 7');
    fireEvent.click(dialog);                                                   // a click inside does not close it
    expect(screen.queryByRole("dialog")).not.toBeNull();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getAllByRole("button", { name: "Details" })[1]);
    fireEvent.click(await screen.findByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getAllByRole("button", { name: "Details" })[0]);
    const overlay = (await screen.findByRole("dialog")).parentElement!;
    fireEvent.click(overlay);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("shows record contents as text, so nothing in them can run", async () => {
    mockFetch({ "GET /projects/1/ledger": { body: ledger([ledgerRow({ seq: 1, meta: { comment: "<img src=x onerror=alert(1)><script>alert(2)</script>" } })]) } });
    wrapped(<LedgerPage />);
    await waitFor(() => expect(gridRows().length).toBe(1));
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    const pre = await screen.findByTestId("meta-json");
    expect(pre.textContent).toContain("<script>alert(2)</script>");
    expect(pre.querySelector("script, img")).toBeNull();
  });

  it("exports exactly the rows shown, as safe CSV", async () => {
    let blob: Blob | null = null;
    vi.stubGlobal("URL", { ...URL, createObjectURL: (b: Blob) => { blob = b; return "blob:x"; }, revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    mockFetch({ "GET /projects/1/ledger": { body: data({ rows: [...rows, ledgerRow({ seq: 6, counterparty: "=HYPERLINK(\"http://evil\")" })] }) } });
    wrapped(<LedgerPage />);
    await waitFor(() => expect(gridRows().length).toBe(6));
    fireEvent.click(screen.getByRole("button", { name: "Pledge collected" }));
    await waitFor(() => expect(gridRows().length).toBe(2));
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    expect(click).toHaveBeenCalledTimes(1);
    const text = await readBlob(blob as unknown as Blob);
    expect(text.split("\r\n").length).toBe(4);                                  // header, two rows, trailing end
    expect(text).toContain("150.00") ;
    expect(text).not.toContain("evil");
    fireEvent.click(screen.getByText("Show all"));
    await waitFor(() => expect(gridRows().length).toBe(6));
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    expect(await readBlob(blob as unknown as Blob)).toContain("'=HYPERLINK");
  });

  it("names the file after the project", async () => {
    await open();
    let name = "";
    vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:x", revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { name = this.download; });
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    expect(name).toBe("ledger-project-1.csv");
  });

  it("highlights rows that need attention", async () => {
    mockFetch({ "GET /projects/1/ledger": { body: ledger([ledgerRow({ seq: 1 }), ledgerRow({ seq: 2, alert: true })]) } });
    wrapped(<LedgerPage />);
    await waitFor(() => expect(gridRows().length).toBe(2));
    expect(gridRows()[1].className).toContain("bg-red-50");
    expect(gridRows()[0].className).not.toContain("bg-red-50");
  });

  it("colours money in green, money out in red and memos grey", async () => {
    await open();
    const cell = (i: number) => gridRows()[i].querySelector('[col-id="amount_cents"]')!.className;
    expect(cell(2)).toContain("text-green-700");
    expect(cell(4)).toContain("text-red-700");
    expect(cell(0)).toContain("text-gray-400");
  });
});

describe("who sees what", () => {
  it("tells the public that contact details are hidden and offers no PayPal check", async () => {
    await open({ public: true });
    expect(screen.getByText(/Public view: contact details are hidden/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Check with PayPal" })).toBeNull();
  });

  it("offers members the PayPal check", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/ledger": { body: data() } });
    wrapped(<LedgerPage />);
    expect(await screen.findByRole("button", { name: "Check with PayPal" })).toBeTruthy();
    expect(screen.queryByText(/Public view/)).toBeNull();
  });

  it("waits for the sign-in check before asking for the ledger", async () => {
    setToken("tok");
    const { calls } = mockFetch({ "GET /auth/me": { body: me, delayMs: 30 }, "GET /projects/1/ledger": { body: data() } });
    wrapped(<LedgerPage />);
    await screen.findByTestId("ledger-grid");
    expect(calls.map((c) => c.path)).toEqual(["/auth/me", "/projects/1/ledger"]);
    expect((calls[1].init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });
});

describe("checking with PayPal", () => {
  async function member(match: unknown, status = 200) {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/ledger": { body: data() }, "GET /projects/1/ledger/paypal-match": { status, body: match } });
    wrapped(<LedgerPage />);
    await waitFor(() => expect(gridRows().length).toBe(5));
    fireEvent.click(await screen.findByRole("button", { name: "Check with PayPal" }));
  }
  const result = (status: string, detail: string) => ({ status, detail, paypal_ref: "X" });

  it("puts a symbol on each checked row and says everything agrees", async () => {
    await member({ project_id: 1, results: { "3": result("MATCH", "PayPal captured exactly this amount"), "4": result("MATCH", "ok") }, counts: { MATCH: 2, PENDING: 0, MISMATCH: 0, NOT_FOUND: 0, UNAVAILABLE: 0 }, limited: false, all_match: true });
    expect((await screen.findByRole("status")).textContent).toBe("PayPal agrees with all 2 checked rows.");
    await waitFor(() => expect(within(gridRows()[2] as HTMLElement).getByLabelText("PayPal agrees").textContent).toBe("✓"));
    expect(within(gridRows()[2] as HTMLElement).getByLabelText("PayPal agrees").getAttribute("title")).toContain("PayPal captured exactly this amount");
    expect(gridRows()[0].querySelector('[col-id="match"]')!.textContent).toBe("");        // unchecked rows stay blank
  });

  it("counts disagreements, pending rows and rows it could not check", async () => {
    await member({ project_id: 1, results: { "3": result("MISMATCH", "PayPal captured 15100 cents"), "4": result("NOT_FOUND", "no such capture"), "5": result("PENDING", "not final") },
                   counts: { MATCH: 0, PENDING: 1, MISMATCH: 1, NOT_FOUND: 1, UNAVAILABLE: 2 }, limited: true, all_match: false });
    expect((await screen.findByRole("status")).textContent).toBe("2 rows disagree with PayPal, 1 not final yet, 2 could not be checked. Only the newest rows were checked.");
    await waitFor(() => expect(within(gridRows()[2] as HTMLElement).getByLabelText("PayPal disagrees").textContent).toBe("✗"));
    expect(within(gridRows()[3] as HTMLElement).getByLabelText("PayPal has no such record").textContent).toBe("✗");
    expect(within(gridRows()[4] as HTMLElement).getByLabelText("Not final at PayPal yet").textContent).toBe("⏳");
  });

  it("says 'disagrees' for exactly one row", async () => {
    await member({ project_id: 1, results: { "3": result("MISMATCH", "x") }, counts: { MATCH: 0, PENDING: 0, MISMATCH: 1, NOT_FOUND: 0, UNAVAILABLE: 0 }, limited: false, all_match: false });
    expect((await screen.findByRole("status")).textContent).toBe("1 row disagrees with PayPal, 0 not final yet, 0 could not be checked.");
  });

  it("explains when there is nothing to check yet", async () => {
    await member({ project_id: 1, results: {}, counts: { MATCH: 0, PENDING: 0, MISMATCH: 0, NOT_FOUND: 0, UNAVAILABLE: 0 }, limited: false, all_match: false });
    expect((await screen.findByRole("status")).textContent).toBe("There are no PayPal-backed rows to check yet.");
  });

  it("reports a failed check in words and lets the person try again", async () => {
    await member({ error: { code: "NOT_A_MEMBER", message: "You are not a member of this project", details: {} } }, 403);
    expect((await screen.findByRole("status")).textContent).toBe("You are not a member of this project");
    expect((screen.getByRole("button", { name: "Check with PayPal" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("disables the button while it asks", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me }, "GET /projects/1/ledger": { body: data() },
                "GET /projects/1/ledger/paypal-match": { body: { project_id: 1, results: {}, counts: { MATCH: 0, PENDING: 0, MISMATCH: 0, NOT_FOUND: 0, UNAVAILABLE: 0 }, limited: false, all_match: false }, delayMs: 60 } });
    wrapped(<LedgerPage />);
    await waitFor(() => expect(gridRows().length).toBe(5));
    fireEvent.click(await screen.findByRole("button", { name: "Check with PayPal" }));
    const busy = (await screen.findByRole("button", { name: "Checking..." })) as HTMLButtonElement;
    expect(busy.disabled).toBe(true);
    await screen.findByRole("button", { name: "Check with PayPal" });
  });
});

describe("states and live refresh", () => {
  it("says so when the ledger is empty", async () => {
    mockFetch({ "GET /projects/1/ledger": { body: ledger([]) } });
    wrapped(<LedgerPage />);
    expect(await screen.findByText("The ledger is empty")).toBeTruthy();
    expect(screen.queryByTestId("ledger-grid")).toBeNull();
  });

  it("shows an error with a retry when the server fails first", async () => {
    let n = 0;
    mockFetch({ "GET /projects/1/ledger": () => (++n === 1 ? { status: 500, body: { error: { code: "X", message: "The database is down", details: {} } } } : { body: data() }) });
    wrapped(<LedgerPage />);
    expect((await screen.findByRole("alert")).textContent).toContain("The database is down");
    fireEvent.click(screen.getByText("Try again"));
    await screen.findByTestId("ledger-grid");
  });

  it("refuses a bad project link without calling the API", () => {
    nav.query = "id=abc";
    const { fn } = mockFetch({});
    wrapped(<LedgerPage />);
    expect(screen.getByText("No project selected")).toBeTruthy();
    expect(fn).not.toHaveBeenCalled();
  });

  it("links back to the project", async () => {
    await open();
    expect(screen.getByRole("link", { name: "Back to the project" }).getAttribute("href")).toBe("/project?id=1");
  });

  it("asks again every fifteen seconds while the page is visible, without blanking the table", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const { calls } = mockFetch({ "GET /projects/1/ledger": { body: data(), delayMs: 40 } });
    wrapped(<LedgerPage />);
    await waitFor(() => expect(gridRows().length).toBe(5));
    expect(calls.length).toBe(1);
    await act(async () => { vi.advanceTimersByTime(REFRESH_MS - 1); });
    expect(calls.length).toBe(1);
    await act(async () => { vi.advanceTimersByTime(1); });
    expect(calls.length).toBe(2);
    expect(gridRows().length).toBe(5);                                          // the old rows stay while the new answer is on its way
    await act(async () => { vi.advanceTimersByTime(REFRESH_MS); });
    expect(calls.length).toBe(3);
  });

  it("does not ask while the tab is hidden, and stops when the page is left", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const { calls } = mockFetch({ "GET /projects/1/ledger": { body: data() } });
    const { unmount } = wrapped(<LedgerPage />);
    await waitFor(() => expect(gridRows().length).toBe(5));
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await act(async () => { vi.advanceTimersByTime(REFRESH_MS * 3); });
    expect(calls.length).toBe(1);
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    unmount();
    await act(async () => { vi.advanceTimersByTime(REFRESH_MS * 3); });
    expect(calls.length).toBe(1);
  });

  it("the refresh button asks right away", async () => {
    const { calls } = await open();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(calls.length).toBe(2));
  });

  it("picks up new rows after a refresh", async () => {
    let n = 0;
    mockFetch({ "GET /projects/1/ledger": () => ({ body: n++ === 0 ? data() : data({ rows: [...rows, ledgerRow({ seq: 6, type: "PLAN_EXECUTED" })] }) }) });
    wrapped(<LedgerPage />);
    await waitFor(() => expect(gridRows().length).toBe(5));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(gridRows().length).toBe(6));
    expect(screen.getByRole("button", { name: "Plan finished" })).toBeTruthy();
  });
});

describe("gaps found by the mutation check", () => {
  it("pins the sequence column on the left", async () => {
    await open();
    expect(document.querySelector(".ag-root")!.className).toContain("ag-has-left-pinned-cols");
    expect(gridRows()[0].querySelector('[col-id="seq"]')!.className).toContain("ag-cell-last-left-pinned");
    expect(gridRows()[0].querySelector('[col-id="type"]')!.className).not.toContain("pinned");
  });

  it("lets a small ledger grow to its natural height and gives a large one a scrolling window", async () => {
    await open();
    expect(document.querySelector(".ag-root")!.className).toContain("ag-layout-auto-height");
    expect(screen.getByTestId("ledger-grid").className).not.toContain("h-[600px]");
    cleanup();
    const many = Array.from({ length: 201 }, (_, i) => ledgerRow({ seq: i + 1 }));
    mockFetch({ "GET /projects/1/ledger": { body: ledger(many) } });
    wrapped(<LedgerPage />);
    await screen.findByTestId("ledger-grid");
    await waitFor(() => expect(document.querySelector(".ag-root")).not.toBeNull());
    expect(document.querySelector(".ag-root")!.className).toContain("ag-layout-normal");
    expect(screen.getByTestId("ledger-grid").className).toContain("h-[600px]");
  });

  it("the totals row has no time and never says 'none' in the time column", async () => {
    await open();
    const totals = document.querySelector(".ag-grid-pinned-bottom-rows-container .ag-row")!;
    expect(totals.querySelector('[col-id="created_at"]')!.textContent).toBe("");
    expect(totals.querySelector('[col-id="seq"]')!.textContent).toBe("");
    expect(pinnedText()).not.toContain("none");
  });

  it("shows the PayPal reference short, with the whole reference on hover and in search", async () => {
    await open();
    const ref = gridRows()[2].querySelector('[col-id="paypal_ref"] span') as HTMLElement;
    expect([ref.textContent, ref.getAttribute("title")]).toEqual(["CAPTURE-AB…", "CAPTURE-ABCDEFGHIJKLMNOP"]);
    expect(gridRows()[0].querySelector('[col-id="paypal_ref"] span')).toBeNull();
    fireEvent.change(screen.getByLabelText("Search the ledger"), { target: { value: "ABCDEFGHIJKLMNOP" } });
    await waitFor(() => expect(gridRows().length).toBe(1));
  });

  it("search finds a row by the plain words of its type as well as the raw code", async () => {
    await open();
    const box = screen.getByLabelText("Search the ledger");
    fireEvent.change(box, { target: { value: "Paid to the builder" } });
    await waitFor(() => expect(gridRows().length).toBe(1));
    fireEvent.change(box, { target: { value: "PLEDGE_CAPTURED" } });
    await waitFor(() => expect(gridRows().length).toBe(2));
  });

  it("a chip toggles on and off", async () => {
    await open();
    const chip = screen.getByRole("button", { name: "Pledge collected" });
    fireEvent.click(chip);
    expect(chip.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Show all")).toBeTruthy();
    fireEvent.click(chip);
    expect(chip.getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByText("Show all")).toBeNull();
    await waitFor(() => expect(gridRows().length).toBe(5));
  });

  it("keeps the rows on screen when a refresh fails, and says so", async () => {
    let n = 0;
    mockFetch({ "GET /projects/1/ledger": () => (n++ === 0 ? { body: data() } : { status: 500, body: { error: { code: "X", message: "The database is down", details: {} } } }) });
    wrapped(<LedgerPage />);
    await waitFor(() => expect(gridRows().length).toBe(5));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Could not refresh the ledger just now (The database is down)");
    expect(gridRows().length).toBe(5);
    expect(screen.getByTestId("ledger-grid")).toBeTruthy();
  });

  it("stops its timer when the page is left", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    mockFetch({ "GET /projects/1/ledger": { body: data() } });
    const { unmount } = wrapped(<LedgerPage />);
    await waitFor(() => expect(gridRows().length).toBe(5));
    expect(vi.getTimerCount()).toBeGreaterThan(0);                              // the page's refresh timer (and the grid's own)
    unmount();
    expect(vi.getTimerCount()).toBe(0);                                         // nothing is left running
  });
});

describe("time column", () => {
  it("shows each time in UTC words, not the raw timestamp", async () => {
    await open();
    expect(gridRows()[0].querySelector('[col-id="created_at"]')!.textContent).toBe("Nov 10, 12:00 UTC");
    expect(gridRows()[0].textContent).not.toContain("2026-11-10T");
  });
});
