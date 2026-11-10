/** Plain-words labels for the project and campaign states (SPEC 6.1). A backend test keeps these lists equal to the state machines. */
export type Tone = "grey" | "blue" | "teal" | "amber" | "green" | "red";

export const PROJECT_STATES: Record<string, { label: string; tone: Tone }> = {
  DRAFT: { label: "Draft", tone: "grey" },
  REQUIREMENTS: { label: "Gathering requirements", tone: "blue" },
  BRD_REVIEW: { label: "Brief awaiting approval", tone: "blue" },
  CONTRACTING: { label: "Contract with the builder", tone: "blue" },
  CAMPAIGN_SETUP: { label: "Campaign being set up", tone: "teal" },
  PLEDGING: { label: "Collecting pledges", tone: "teal" },
  CAMPAIGN_FAILED: { label: "Goal missed: nobody was charged", tone: "amber" },
  IN_PROGRESS: { label: "Funded: being built", tone: "green" },
  VERIFYING: { label: "Work being checked", tone: "amber" },
  PAYOUT_READY: { label: "Verified: ready to pay", tone: "green" },
  PAYOUT_PENDING: { label: "Payment on its way", tone: "amber" },
  PAYOUT_FAILED: { label: "Payment failed", tone: "red" },
  PAID: { label: "Paid", tone: "green" },
  REFUNDING: { label: "Refunding pledgers", tone: "amber" },
  CANCELLED: { label: "Cancelled and refunded", tone: "grey" },
};

export const CAMPAIGN_STATES: Record<string, { label: string; tone: Tone }> = {
  SETUP: { label: "Not open yet", tone: "grey" },
  OPEN: { label: "Open for pledges", tone: "teal" },
  CAPTURING: { label: "Collecting the pledged money", tone: "amber" },
  CAPTURED: { label: "Funded", tone: "green" },
  FAILING: { label: "Releasing holds", tone: "amber" },
  FAILED: { label: "Goal missed: holds released", tone: "amber" },
  CANCELLED: { label: "Cancelled", tone: "grey" },
};

export function projectState(state: string): { label: string; tone: Tone } {
  return PROJECT_STATES[state] ?? { label: state, tone: "grey" };
}

export function campaignState(state: string): { label: string; tone: Tone } {
  return CAMPAIGN_STATES[state] ?? { label: state, tone: "grey" };
}
