import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "@/lib/api";
import { formatMoney, percentOf } from "@/lib/money";
import { CAMPAIGN_STATES, PROJECT_STATES, campaignState, projectState } from "@/lib/states";
import { clearToken, getToken, onTokenCleared, setToken } from "@/lib/token";
import { SLOW_AFTER_MS, watchSlow } from "@/lib/wake";
import { mockFetch } from "./helpers";

/** The error a call fails with, typed. */
async function failure(p: Promise<unknown>): Promise<ApiError> {
  try {
    await p;
  } catch (e) {
    return e as ApiError;
  }
  throw new Error("expected the call to fail");
}

afterEach(() => {
  clearToken();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("money", () => {
  it.each([
    [0, "$0.00"], [5, "$0.05"], [10, "$0.10"], [100, "$1.00"], [1234, "$12.34"], [15000, "$150.00"], [123456789, "$1,234,567.89"],
    [-5, "-$0.05"], [-15050, "-$150.50"], [99, "$0.99"],
  ])("formats %i cents as %s", (cents, text) => expect(formatMoney(cents)).toBe(text));

  it("names other currencies", () => expect(formatMoney(2500, "EUR")).toBe("EUR 25.00"));

  it.each([12.5, NaN, Infinity, -0.1, 1e21, 0.1 + 0.2])("refuses %s: money is whole cents", (bad) => expect(() => formatMoney(bad)).toThrow(TypeError));
  it("refuses a string passed by mistake", () => expect(() => formatMoney("5" as unknown as number)).toThrow(TypeError));

  it.each([[0, 0, 0], [50, 100, 50], [1, 3, 33], [2, 3, 66], [150, 100, 100], [-5, 100, 0], [5, 0, 0], [5, -1, 0], [NaN, 100, 0], [5, NaN, 0], [15000, 40000, 37]])(
    "percentOf(%s, %s) = %s", (part, whole, pct) => expect(percentOf(part, whole)).toBe(pct));
});

describe("token storage", () => {
  it("stores, reads and clears", () => {
    expect(getToken()).toBeNull();
    setToken("abc");
    expect(getToken()).toBe("abc");
    expect(window.localStorage.getItem("briefpay.token")).toBe("abc");
    clearToken();
    expect(getToken()).toBeNull();
    expect(window.localStorage.getItem("briefpay.token")).toBeNull();
  });

  it("keeps working in memory when browser storage throws", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => setToken("mem")).not.toThrow();
    expect(getToken()).toBe("mem");
    expect(() => clearToken()).not.toThrow();
    expect(getToken()).toBeNull();
  });

  it("tells listeners when the token is cleared, until they unsubscribe", () => {
    const seen = vi.fn();
    const off = onTokenCleared(seen);
    setToken("x");
    clearToken();
    expect(seen).toHaveBeenCalledTimes(1);
    off();
    clearToken();
    expect(seen).toHaveBeenCalledTimes(1);
  });
});

describe("api client", () => {
  it("sends the Bearer token and JSON, and returns the parsed body", async () => {
    setToken("tok");
    const { calls } = mockFetch({ "POST /things": { body: { id: 7 } } });
    const out = await api<{ id: number }>("/things", { method: "POST", body: { a: 1 } });
    expect(out).toEqual({ id: 7 });
    const h = calls[0].init.headers as Record<string, string>;
    expect(h.Authorization).toBe("Bearer tok");
    expect(h["Content-Type"]).toBe("application/json");
    expect(calls[0].init.body).toBe('{"a":1}');
  });

  it("sends no token when signed out, and none when asked not to", async () => {
    const { calls } = mockFetch({ "GET /a": { body: {} }, "POST /auth/login": { body: {} } });
    await api("/a");
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBeUndefined();
    setToken("tok");
    await api("/auth/login", { method: "POST", body: {}, auth: false });
    expect((calls[1].init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("sends no body header on a plain read", async () => {
    const { calls } = mockFetch({ "GET /a": { body: {} } });
    await api("/a");
    expect((calls[0].init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
    expect(calls[0].init.body).toBeUndefined();
  });

  it("turns the API's error shape into an ApiError", async () => {
    mockFetch({ "GET /x": { status: 409, body: { error: { code: "PROJECT_STATE", message: "Not now", details: { state: "DRAFT" } } } } });
    const e = await failure(api("/x"));
    expect(e).toBeInstanceOf(ApiError);
    expect([e.status, e.code, e.message, e.details, e.isNetwork]).toEqual([409, "PROJECT_STATE", "Not now", { state: "DRAFT" }, false]);
  });

  it("explains FastAPI validation errors in words", async () => {
    mockFetch({ "POST /v": { status: 422, body: { detail: [{ loc: ["body", "email"], msg: "value is not a valid email address", type: "x" }] } } });
    const e = await failure(api("/v", { method: "POST", body: {} }));
    expect([e.status, e.code, e.message]).toEqual([422, "VALIDATION", "email: value is not a valid email address"]);
  });

  it("copes with plain-text detail, an empty error body and a non-JSON error page", async () => {
    mockFetch({ "GET /a": { status: 404, body: { detail: "Not Found" } }, "GET /b": { status: 500, text: "" }, "GET /c": { status: 502, text: "<html>Bad gateway</html>" } });
    expect(await api("/a").catch((e) => e)).toMatchObject({ status: 404, code: "HTTP_404", message: "Not Found" });
    expect(await api("/b").catch((e) => e)).toMatchObject({ status: 500, code: "HTTP_500" });
    expect(await api("/c").catch((e) => e)).toMatchObject({ status: 502, code: "HTTP_502" });
  });

  it("reports a server that cannot be reached as a network error", async () => {
    mockFetch({ "GET /x": new TypeError("Failed to fetch") });
    const e = await failure(api("/x"));
    expect(e).toBeInstanceOf(ApiError);
    expect([e.status, e.code, e.isNetwork]).toEqual([0, "NETWORK", true]);
    expect(e.message).toContain("wake up");
  });

  it("lets an aborted request stay an abort, not an error to show", async () => {
    mockFetch({ "GET /x": new DOMException("aborted", "AbortError") });
    const e = (await api("/x").catch((err) => err)) as DOMException;
    expect(e).toBeInstanceOf(DOMException);
    expect(e.name).toBe("AbortError");
  });

  it("signs the user out when the server says the token is bad, but not for other 401s or other codes", async () => {
    mockFetch({ "GET /me": { status: 401, body: { error: { code: "BAD_TOKEN", message: "bad", details: {} } } },
                "GET /me2": { status: 401, body: { error: { code: "UNAUTHENTICATED", message: "no", details: {} } } },
                "GET /other": { status: 401, body: { error: { code: "SOMETHING_ELSE", message: "x", details: {} } } },
                "GET /forbidden": { status: 403, body: { error: { code: "BAD_TOKEN", message: "x", details: {} } } } });
    setToken("t");
    await api("/other").catch(() => {});
    await api("/forbidden").catch(() => {});
    expect(getToken()).toBe("t");
    await api("/me").catch(() => {});
    expect(getToken()).toBeNull();
    setToken("t2");
    await api("/me2").catch(() => {});
    expect(getToken()).toBeNull();
  });

  it("returns nothing for an empty success body", async () => {
    mockFetch({ "DELETE /x": { status: 204 } });
    expect(await api("/x", { method: "DELETE" })).toBeNull();
  });

  it("uses the configured API base", async () => {
    const { calls } = mockFetch({ "GET /a": { body: {} } });
    await api("/a");
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("http://api.test/api/a");
    expect(calls.length).toBe(1);
  });
});

describe("slow-server notice", () => {
  it("fires once when the work takes too long, and not when it is quick", async () => {
    vi.useFakeTimers();
    const slow = vi.fn();
    const quick = watchSlow(Promise.resolve("fast"), slow);
    expect(await quick).toBe("fast");
    vi.advanceTimersByTime(SLOW_AFTER_MS + 1);
    expect(slow).not.toHaveBeenCalled();

    let finish!: (v: string) => void;
    const long = watchSlow(new Promise<string>((r) => (finish = r)), slow);
    vi.advanceTimersByTime(SLOW_AFTER_MS - 1);
    expect(slow).not.toHaveBeenCalled();
    vi.advanceTimersByTime(2);
    expect(slow).toHaveBeenCalledTimes(1);
    finish("done");
    expect(await long).toBe("done");
    vi.advanceTimersByTime(60000);
    expect(slow).toHaveBeenCalledTimes(1);
  });

  it("passes the work's error through and still cleans up", async () => {
    vi.useFakeTimers();
    const slow = vi.fn();
    await expect(watchSlow(Promise.reject(new Error("boom")), slow)).rejects.toThrow("boom");
    vi.advanceTimersByTime(SLOW_AFTER_MS * 2);
    expect(slow).not.toHaveBeenCalled();
  });

  it("waits four seconds", () => expect(SLOW_AFTER_MS).toBe(4000));
});

describe("state labels", () => {
  it("every project and campaign state has words and a tone", () => {
    for (const table of [PROJECT_STATES, CAMPAIGN_STATES]) {
      for (const [key, v] of Object.entries(table)) {
        expect(v.label.length, key).toBeGreaterThan(3);
        expect(["grey", "blue", "teal", "amber", "green", "red"]).toContain(v.tone);
      }
    }
  });
  it("falls back to the raw name for an unknown state", () => {
    expect(projectState("NEW_STATE")).toEqual({ label: "NEW_STATE", tone: "grey" });
    expect(campaignState("NEW")).toEqual({ label: "NEW", tone: "grey" });
    expect(projectState("PAID").label).toBe("Paid");
    expect(campaignState("OPEN").label).toBe("Open for pledges");
  });
  it("says plainly that a missed goal charged nobody", () => {
    expect(projectState("CAMPAIGN_FAILED").label).toContain("nobody was charged");
    expect(campaignState("FAILED").label).toContain("holds released");
  });
});

describe("gaps found by the mutation check", () => {
  it("falls back to memory when storage accepts nothing but reads fine", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
    setToken("only-in-memory");
    expect(window.localStorage.getItem("briefpay.token")).toBeNull();
    expect(getToken()).toBe("only-in-memory");
  });
});
