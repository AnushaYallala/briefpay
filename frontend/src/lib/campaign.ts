/** Campaign page logic (SPEC 11, screens 7 and 8), kept apart from the screens so it can be tested on its own. */
import type { Tone } from "./states";
import type { CampaignView, LedgerRow, Nudge } from "./types";

/** How often an open campaign asks for news, and how often its clock redraws. */
export const CAMPAIGN_REFRESH_MS = 10000;
export const CLOCK_MS = 30000;

export const CLOSE_POLICY_WORDS: Record<string, string> = {
  EARLY_ON_GOAL: "Closes as soon as the goal is reached, so the money is collected promptly.",
  AT_DEADLINE: "Stays open until the deadline, even after the goal is reached.",
};

/** What a visitor should understand about the money in each state (SPEC 8.2: a pledge is only a hold until it is collected). */
export const MONEY_NOTES: Record<string, string> = {
  SETUP: "This campaign has not opened yet. Nothing can be pledged.",
  OPEN: "Nothing is charged unless the goal is reached. A pledge is only a hold on your PayPal account.",
  CAPTURING: "The goal was reached. The held money is being collected now.",
  CAPTURED: "Funded. The pledged money has been collected.",
  FAILING: "The goal was missed. Every hold is being released: nobody pays.",
  FAILED: "The goal was missed. Every hold was released: nobody was charged.",
  CANCELLED: "This campaign was cancelled. Every hold is released: nobody pays.",
};

export const moneyNote = (state: string) => MONEY_NOTES[state] ?? "";

/** Time left until the deadline, in the two largest units; "Closed" once it has passed. */
export function countdownText(deadlineIso: string, nowMs: number, parse: (iso: string) => Date): string {
  const left = Math.floor((parse(deadlineIso).getTime() - nowMs) / 1000);
  if (left <= 0) return "Closed";
  const d = Math.floor(left / 86400);
  const h = Math.floor((left % 86400) / 3600);
  const m = Math.floor((left % 3600) / 60);
  if (d > 0) return `${d} day${d === 1 ? "" : "s"} ${h} hour${h === 1 ? "" : "s"} left`;
  if (h > 0) return `${h} hour${h === 1 ? "" : "s"} ${m} minute${m === 1 ? "" : "s"} left`;
  return m > 0 ? `${m} minute${m === 1 ? "" : "s"} left` : "Less than a minute left";
}

export type BoardRow = { pledge: string; name: string; status: "AUTHORIZED" | "CAPTURED" | "VOIDED" | "EXPIRED"; amount_cents: number | null; at: string };

export const BOARD_STATUS: Record<string, { label: string; tone: Tone }> = {
  AUTHORIZED: { label: "Held", tone: "teal" },
  CAPTURED: { label: "Collected", tone: "green" },
  VOIDED: { label: "Released", tone: "grey" },
  EXPIRED: { label: "Expired", tone: "amber" },
};

const FROM_TYPE: Record<string, BoardRow["status"]> = { PLEDGE_AUTHORIZED: "AUTHORIZED", PLEDGE_CAPTURED: "CAPTURED", PLEDGE_VOIDED: "VOIDED", PLEDGE_EXPIRED: "EXPIRED" };

/**
 * The pledge board, built from the public ledger: one row per pledge, showing its latest step. Only pledges from the time the campaign
 * opened count. The amount is known once a pledge is collected; a hold has no amount on the ledger, so it shows as held.
 */
export function boardRows(rows: LedgerRow[], opensAt: string | null, parse: (iso: string) => Date): BoardRow[] {
  if (opensAt === null) return [];
  const since = parse(opensAt).getTime();
  const byPledge = new Map<string, BoardRow>();
  for (const r of rows) {
    const status = FROM_TYPE[r.type];
    if (!status || r.ref_type !== "pledge" || r.ref_id === null || parse(r.created_at).getTime() < since) continue;
    const prev = byPledge.get(r.ref_id);
    byPledge.set(r.ref_id, {
      pledge: r.ref_id, name: r.counterparty ?? prev?.name ?? "A supporter", status,
      amount_cents: status === "CAPTURED" ? r.amount_cents : prev?.amount_cents ?? null, at: r.created_at,
    });
  }
  return [...byPledge.values()].sort((a, b) => b.at.localeCompare(a.at) || Number(b.pledge) - Number(a.pledge));
}

/** A "datetime-local" box has no zone: we read what is typed as UTC and say so beside it. Empty or invalid gives null. */
export function deadlineToIso(local: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local)) return null;     // an empty box would otherwise read as the year 2000
  const d = new Date(`${local}:00Z`);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export const isoToLocalInput = (iso: string, parse: (iso: string) => Date) => parse(iso).toISOString().slice(0, 16);

/** Whole dollars typed in a box to cents; blank means "not set" (null); anything else that is not a non-negative amount is rejected. */
export function dollarsToCents(text: string): number | null | "bad" {
  const t = text.trim();
  if (t === "") return null;
  if (!/^\d{1,6}(\.\d{1,2})?$/.test(t)) return "bad";
  return Math.round(Number(t) * 100);
}

export const centsToDollars = (cents: number | null) => (cents === null ? "" : (cents / 100).toFixed(2));

/** Whether a typed deadline is inside the window the server allows. */
export function deadlineProblem(local: string, earliestIso: string, latestIso: string, parse: (iso: string) => Date): string | null {
  const iso = deadlineToIso(local);
  if (iso === null) return "Choose a date and time for the deadline.";
  const t = new Date(iso).getTime();
  if (t < parse(earliestIso).getTime()) return "That is too soon: the campaign needs at least a little time to collect pledges.";
  if (t > parse(latestIso).getTime()) return "That is too late: PayPal only guarantees a hold for three days, so the campaign must end sooner.";
  return null;
}

/** Plain words for the Strategist's probability. */
export const percentWords = (p: number) => `${Math.round(p * 100)}%`;

export const whatsappUrl = (message: string) => `https://wa.me/?text=${encodeURIComponent(message)}`;

export const mayLaunch = (view: CampaignView) => view.state === "SETUP" && view.lead?.can_launch === true;

export const isLive = (state: string) => state === "SETUP" || state === "OPEN";

export const nudgeLabel = (n: Pick<Nudge, "source">) => (n.source === "TEMPLATE" ? "Draft from a template" : "Draft written by the AI, checked by the system");
