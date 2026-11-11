import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CampaignPage from "@/app/campaign/page";
import { AuthProvider } from "@/lib/auth";
import { clearToken, setToken } from "@/lib/token";
import { campaignView, lakshmi, leadPart, ledger, mockFetch } from "./helpers";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams("id=1") }));
vi.mock("@/lib/personas", () => ({ DEMO_MODE: false, PERSONAS: [] }));       // the real site: no demo helpers
afterEach(() => { cleanup(); vi.unstubAllGlobals(); clearToken(); });

describe("the lead's buttons on the real site (not the demo)", () => {
  it("do not include the early-deadline shortcut, which only exists in demo mode", async () => {
    setToken("tok");
    mockFetch({
      "GET /auth/me": { body: { user: lakshmi, memberships: [{ member_id: 1, project_id: 1, role: "LEAD" }] } },
      "GET /campaigns/1": { body: campaignView({ lead: leadPart() }) }, "GET /projects/1/ledger": { body: ledger([]) },
      "GET /campaigns/1/strategist": { status: 404, body: { error: { code: "NO_REPORT", message: "none" } } },
    } as never);
    render(<AuthProvider><CampaignPage /></AuthProvider>);
    await screen.findByTestId("title");
    expect(screen.getByRole("button", { name: /Close and collect now/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Try the deadline early/ })).toBeNull();
  });
});
