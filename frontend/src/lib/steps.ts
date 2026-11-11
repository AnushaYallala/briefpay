/** The workspace stepper (SPEC 11, screen 3): Requirements, Brief, Contract, Campaign, Build, Verify, Payout, Ledger. */
export const STEPS = ["Requirements", "Brief", "Contract", "Campaign", "Build", "Verify", "Payout", "Ledger"] as const;

/** Which step each project state belongs to (null: the project left the normal path). A backend test checks every state is here. */
export const STEP_OF: Record<string, number | null> = {
  DRAFT: 0, REQUIREMENTS: 0, BRD_REVIEW: 1, CONTRACTING: 2, CAMPAIGN_SETUP: 3, PLEDGING: 3, CAMPAIGN_FAILED: 3,
  IN_PROGRESS: 4, VERIFYING: 5, PAYOUT_READY: 6, PAYOUT_PENDING: 6, PAYOUT_FAILED: 6, PAID: 7, REFUNDING: null, CANCELLED: null,
};

export type StepStatus = "done" | "current" | "upcoming";

export function stepStatuses(state: string): StepStatus[] {
  const at = STEP_OF[state];
  if (at === undefined || at === null) return STEPS.map(() => "upcoming");
  return STEPS.map((_, i) => (i < at ? "done" : i === at ? "current" : "upcoming"));
}

/** What happens next, in plain words, for a visitor. */
export const WHAT_NEXT: Record<string, string> = {
  DRAFT: "The organiser is about to share the meeting notes.",
  REQUIREMENTS: "The assistant is turning the meeting into clear requirements and asking the sponsors questions.",
  BRD_REVIEW: "Every sponsor must read and approve the written brief before anything else happens.",
  CONTRACTING: "The builder is reviewing the brief and the price. The contract only takes effect if the campaign is funded.",
  CAMPAIGN_SETUP: "The organiser is setting the goal date. Pledges open once the campaign is launched.",
  PLEDGING: "Pledges are open. A pledge is only a hold: nobody is charged unless the goal is reached before the deadline.",
  CAMPAIGN_FAILED: "The goal was missed. Every hold was released and nobody was charged. The organiser can start another round.",
  IN_PROGRESS: "The goal was reached and the pledges were collected. The builder is working; they must submit the work for checking.",
  VERIFYING: "The submitted work is being checked against the agreed brief.",
  PAYOUT_READY: "The work passed its checks. A sponsor can now review and approve the payment to the builder.",
  PAYOUT_PENDING: "The payment has been sent and is waiting for PayPal to confirm it.",
  PAYOUT_FAILED: "The payment did not go through. The money is still held; it can be retried.",
  PAID: "The builder has been paid. The ledger shows every step.",
  REFUNDING: "The project was cancelled. The pledged money is being returned.",
  CANCELLED: "The project was cancelled and every pledger was refunded.",
};

/** Recommended next action CTA for each state */
export const CTA_OF: Record<string, { label: string; href: (id: number) => string } | null> = {
  DRAFT: { label: "Open BA Studio", href: (id) => `/ba?id=${id}` },
  REQUIREMENTS: { label: "Continue in BA Studio", href: (id) => `/ba?id=${id}` },
  BRD_REVIEW: { label: "Review & Sign Brief", href: (id) => `/brd?id=${id}` },
  CONTRACTING: { label: "Review & Sign Contract", href: (id) => `/contract?id=${id}` },
  CAMPAIGN_SETUP: { label: "Configure Campaign", href: (id) => `/project?id=${id}` },
  PLEDGING: { label: "Campaign Live", href: (id) => `/project?id=${id}` },
  CAMPAIGN_FAILED: { label: "Review Release Plans", href: (id) => `/plans?id=${id}` },
  IN_PROGRESS: { label: "Submit Deliverables", href: (id) => `/submit?id=${id}` },
  VERIFYING: { label: "View Verification Report", href: (id) => `/verify?id=${id}` },
  PAYOUT_READY: { label: "Review & Approve Payout", href: (id) => `/plans?id=${id}` },
  PAYOUT_PENDING: { label: "Monitor Money Plan", href: (id) => `/plans?id=${id}` },
  PAYOUT_FAILED: { label: "Retry Money Plan", href: (id) => `/plans?id=${id}` },
  PAID: { label: "View Public Ledger", href: (id) => `/ledger?id=${id}` },
  REFUNDING: { label: "Monitor Refunds", href: (id) => `/plans?id=${id}` },
  CANCELLED: { label: "View Public Ledger", href: (id) => `/ledger?id=${id}` },
};
