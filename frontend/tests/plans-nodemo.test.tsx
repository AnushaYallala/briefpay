import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PlansPage from "@/app/plans/page";
import { AuthProvider } from "@/lib/auth";
import { clearToken, setToken } from "@/lib/token";
import { lakshmi, mockFetch, planDetail, planItem, review } from "./helpers";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams("id=1") }));
vi.mock("@/lib/personas", () => ({ DEMO_MODE: false, PERSONAS: [] }));       // the real site: no demo helpers

afterEach(() => { cleanup(); vi.unstubAllGlobals(); clearToken(); });

describe("plans page outside demo mode", () => {
  it("never offers the tamper test, even to the lead", async () => {
    setToken("tok");
    mockFetch({
      "GET /auth/me": { body: { user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role: "LEAD" }] } },
      "GET /projects/1/plans": { body: { plans: [planItem({ id: 2, state: "REVIEWED", decision: "ALLOW" })] } },
      "GET /plans/2": { body: planDetail({ id: 2, state: "REVIEWED", decision: "ALLOW", reviews: [review()] }) },
    });
    render(<AuthProvider><PlansPage /></AuthProvider>);
    fireEvent.click(await screen.findByRole("button", { name: /Pay the builder/ }));
    await screen.findByTestId("plan-detail");
    expect(screen.queryByRole("region", { name: "Tamper test" })).toBeNull();
    expect(screen.queryByText(/Try to cheat/)).toBeNull();
    expect(screen.getByRole("button", { name: "Approve and run" })).toBeTruthy();       // the rest of the page is unaffected
  });
});
