import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import LoginPage from "@/app/login/page";
import { Header } from "@/components/Header";
import { Empty, ErrorBox, Loading, PledgeProgress } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { AuthProvider } from "@/lib/auth";
import { clearToken, getToken, setToken } from "@/lib/token";
import { lakshmi, mockFetch, project } from "./helpers";

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: nav.push }) }));

beforeEach(() => clearToken());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  nav.push.mockReset();
  clearToken();
});

const me = { user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role: "LEAD" }] };
const wrapped = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);

describe("home page", () => {
  it("shows a loading state, then the project cards with state words and the hold promise", async () => {
    mockFetch({ "GET /projects": { body: { projects: [project(), project({ id: 2, title: "Second", state: "PAID", campaign: null, summary: null, location_label: null })] } } });
    render(<Home />);
    expect(screen.getByRole("status").textContent).toContain("Loading projects");
    expect(await screen.findByText("Velugu Cove tourism website")).toBeTruthy();
    expect(screen.getByText("Collecting pledges")).toBeTruthy();
    expect(screen.getByText("Paid")).toBeTruthy();
    expect(screen.getByText(/Pledged \$150\.00 of \$400\.00 by 1 person/)).toBeTruthy();
    expect(screen.getByText(/Nothing is charged unless the goal is reached/)).toBeTruthy();
    expect(screen.getAllByText(/Budget \$400\.00/).length).toBe(2);
    expect(screen.getAllByRole("progressbar").length).toBe(1);                    // the project with no campaign has no bar
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows a friendly empty state", async () => {
    mockFetch({ "GET /projects": { body: { projects: [] } } });
    render(<Home />);
    expect(await screen.findByText("No projects yet")).toBeTruthy();
  });

  it("shows the error and recovers on retry", async () => {
    let calls = 0;
    mockFetch({ "GET /projects": () => (++calls === 1 ? new TypeError("offline") : { body: { projects: [project()] } }) });
    render(<Home />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Could not reach the server");
    fireEvent.click(screen.getByText("Try again"));
    expect(await screen.findByText("Velugu Cove tourism website")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows API errors in words", async () => {
    mockFetch({ "GET /projects": { status: 500, body: { error: { code: "BOOM", message: "The database is down", details: {} } } } });
    render(<Home />);
    expect((await screen.findByRole("alert")).textContent).toContain("The database is down");
  });

  it("tells the visitor the server is waking up when it is slow, and removes the notice when it answers", async () => {
    vi.useFakeTimers();
    let answer!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((r) => (answer = r))));
    render(<Home />);
    expect(screen.queryByText(/Waking up the server/)).toBeNull();
    await act(async () => { vi.advanceTimersByTime(3900); });
    expect(screen.queryByText(/Waking up the server/)).toBeNull();
    await act(async () => { vi.advanceTimersByTime(200); });
    expect(screen.getByText(/Waking up the server/).textContent).toContain("about a minute");
    await act(async () => { answer(new Response(JSON.stringify({ projects: [project()] }), { status: 200 })); });
    vi.useRealTimers();
    expect(await screen.findByText("Velugu Cove tourism website")).toBeTruthy();
    expect(screen.queryByText(/Waking up the server/)).toBeNull();
  });
});

describe("header and sign-in state", () => {
  it("offers sign-in to a visitor", async () => {
    mockFetch({});
    wrapped(<Header />);
    const link = await screen.findByText("Sign in");
    expect(link.getAttribute("href")).toBe("/login");
  });

  it("shows the signed-in person and signs them out", async () => {
    setToken("tok");
    const { calls } = mockFetch({ "GET /auth/me": { body: me } });
    wrapped(<Header />);
    expect(await screen.findByText("Lakshmi")).toBeTruthy();
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
    fireEvent.click(screen.getByText("Sign out"));
    expect(await screen.findByText("Sign in")).toBeTruthy();
    expect(getToken()).toBeNull();
  });

  it("treats a rejected token as signed out", async () => {
    setToken("old");
    mockFetch({ "GET /auth/me": { status: 401, body: { error: { code: "BAD_TOKEN", message: "bad", details: {} } } } });
    wrapped(<Header />);
    expect(await screen.findByText("Sign in")).toBeTruthy();
    expect(getToken()).toBeNull();
  });

  it("does not sign anyone out just because the server is asleep", async () => {
    setToken("keep");
    mockFetch({ "GET /auth/me": new TypeError("offline") });
    wrapped(<><Header /><LoginPage /></>);
    expect(await screen.findByText(/could not be reached/)).toBeTruthy();
    expect(getToken()).toBe("keep");
  });

  it("lets the demo switch person with one click", async () => {
    const ravi = { id: 2, email: "ravi@velugu.example.com", display_name: "Ravi" };
    const { calls } = mockFetch({
      "POST /auth/login": (init) => ({ body: { token: "ravi-token", user: ravi, echo: JSON.parse(String(init.body)) } }),
      "GET /auth/me": { body: { user: ravi, memberships: [] } },
    });
    wrapped(<Header />);
    const select = (await screen.findByLabelText("Switch demo person")) as HTMLSelectElement;
    expect(select.value).toBe("");
    fireEvent.change(select, { target: { value: "ravi" } });
    await waitFor(() => expect(screen.getByText("Ravi", { selector: "span.text-gray-700" })).toBeTruthy());
    expect(calls[0]).toMatchObject({ method: "POST", path: "/auth/login" });
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ email: "ravi@velugu.example.com", display_name: "Ravi" });
    expect(getToken()).toBe("ravi-token");
    expect((select.querySelectorAll("option").length)).toBe(5);
  });

  it("reports a failed switch instead of failing silently", async () => {
    mockFetch({ "POST /auth/login": { status: 500, body: { error: { code: "X", message: "Login is broken", details: {} } } } });
    wrapped(<Header />);
    fireEvent.change(await screen.findByLabelText("Switch demo person"), { target: { value: "meena" } });
    expect((await screen.findByRole("alert")).textContent).toBe("Login is broken");
  });
});

describe("login page", () => {
  it("signs in with an email and name, then goes home", async () => {
    const { calls } = mockFetch({ "POST /auth/login": { body: { token: "t1", user: lakshmi } }, "GET /auth/me": { body: me } });
    wrapped(<LoginPage />);
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "  lakshmi@velugu.example.com " } });
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: " Lakshmi " } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/"));
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ email: "lakshmi@velugu.example.com", display_name: "Lakshmi" });
    expect(getToken()).toBe("t1");
  });

  it("shows why a sign-in failed and stays on the page", async () => {
    mockFetch({ "POST /auth/login": { status: 422, body: { detail: [{ loc: ["body", "email"], msg: "value is not a valid email address", type: "x" }] } } });
    wrapped(<LoginPage />);
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "a@b.c" } });
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "A" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect((await screen.findByRole("alert")).textContent).toBe("email: value is not a valid email address");
    expect(nav.push).not.toHaveBeenCalled();
    expect(getToken()).toBeNull();
  });

  it("offers the demo people as one-click sign-ins", async () => {
    const { calls } = mockFetch({ "POST /auth/login": { body: { token: "ar", user: { ...lakshmi, id: 4, email: "arjun@velugu.example.com", display_name: "Arjun" } } }, "GET /auth/me": { body: me } });
    wrapped(<LoginPage />);
    fireEvent.click(await screen.findByText("Freelancer"));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/"));
    expect(JSON.parse(String(calls[0].init.body)).email).toBe("arjun@velugu.example.com");
    expect(screen.getAllByRole("button").length).toBeGreaterThanOrEqual(5);
  });

  it("disables the buttons while signing in", async () => {
    mockFetch({ "POST /auth/login": { body: { token: "t", user: lakshmi }, delayMs: 30 }, "GET /auth/me": { body: me } });
    wrapped(<LoginPage />);
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "l@x.com" } });
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "L" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(((await screen.findByRole("button", { name: "Signing in..." })) as HTMLButtonElement).disabled).toBe(true);
    await waitFor(() => expect(nav.push).toHaveBeenCalled());
  });
});

describe("shared pieces", () => {
  it("the progress bar tells the truth about holds", () => {
    const { rerender } = render(<PledgeProgress pledgedCents={15000} goalCents={40000} count={1} open />);
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("37");
    expect(screen.getByText(/by 1 person$/)).toBeTruthy();
    expect(screen.getByText(/a pledge is only a hold/)).toBeTruthy();
    rerender(<PledgeProgress pledgedCents={40000} goalCents={40000} count={3} open={false} />);
    expect(screen.getByText(/by 3 people$/)).toBeTruthy();
    expect(screen.queryByText(/only a hold/)).toBeNull();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("100");
    rerender(<PledgeProgress pledgedCents={0} goalCents={0} count={0} open />);
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("0");
  });

  it("loading, error and empty states render their words", () => {
    render(<><Loading what="Loading plans" /><ErrorBox error={new ApiError(409, "X", "Not now")} /><Empty title="Nothing here">Try later</Empty></>);
    expect(screen.getByRole("status").textContent).toBe("Loading plans...");
    expect(screen.getByRole("alert").textContent).toContain("Something went wrong");
    expect(screen.getByRole("alert").textContent).toContain("Not now");
    expect(screen.queryByText("Try again")).toBeNull();
    expect(screen.getByText("Try later")).toBeTruthy();
  });
});

describe("gaps found by the mutation check", () => {
  it("signing in never sends the old token", async () => {
    setToken("old-token");
    const { calls } = mockFetch({ "GET /auth/me": { body: me }, "POST /auth/login": { body: { token: "new-token", user: lakshmi } } });
    wrapped(<LoginPage />);
    await screen.findByText("Sign in", { selector: "h1" });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "l@x.com" } });
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "L" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(getToken()).toBe("new-token"));
    const login = calls.find((c) => c.path === "/auth/login")!;
    expect((login.init.headers as Record<string, string>).Authorization).toBeUndefined();
    const meAfter = calls.filter((c) => c.path === "/auth/me").at(-1)!;
    expect((meAfter.init.headers as Record<string, string>).Authorization).toBe("Bearer new-token");
  });

  it("does not offer 'Sign in' while the account is still loading", async () => {
    setToken("tok");
    mockFetch({ "GET /auth/me": { body: me, delayMs: 40 } });
    wrapped(<Header />);
    expect(screen.queryByText("Sign in")).toBeNull();
    expect(await screen.findByText("Lakshmi")).toBeTruthy();
    expect(screen.queryByText("Sign in")).toBeNull();
  });

  it("a slow earlier answer never overwrites a newer one", async () => {
    const { useApi } = await import("@/lib/useApi");
    const { renderHook } = await import("@testing-library/react");
    mockFetch({ "GET /slow": { body: { name: "old" }, delayMs: 80 }, "GET /fast": { body: { name: "new" } } });
    const { result, rerender } = renderHook(({ path }) => useApi<{ name: string }>(path), { initialProps: { path: "/slow" } });
    rerender({ path: "/fast" });
    await waitFor(() => expect(result.current.data?.name).toBe("new"));
    await new Promise((r) => setTimeout(r, 150));
    expect(result.current.data?.name).toBe("new");
    expect(result.current.loading).toBe(false);
  });

  it("cancels the request when the screen goes away", async () => {
    const { useApi } = await import("@/lib/useApi");
    const { renderHook } = await import("@testing-library/react");
    const { fn } = mockFetch({ "GET /x": { body: {}, delayMs: 50 } });
    const { unmount } = renderHook(() => useApi("/x"));
    const signal = (fn.mock.calls[0][1] as RequestInit).signal as AbortSignal;
    expect(signal.aborted).toBe(false);
    unmount();
    expect(signal.aborted).toBe(true);
  });

  it("a null path loads nothing", async () => {
    const { useApi } = await import("@/lib/useApi");
    const { renderHook } = await import("@testing-library/react");
    const { fn } = mockFetch({});
    const { result } = renderHook(() => useApi(null));
    expect(fn).not.toHaveBeenCalled();
    expect([result.current.loading, result.current.data, result.current.error]).toEqual([false, null, null]);
  });
});
