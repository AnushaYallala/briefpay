/** Ledger logic kept apart from the grid so it can be tested on its own (SPEC 11, screen 12). */
import { formatMoney } from "./money";
import type { LedgerRow, MatchStatus } from "./types";

/** How often the open ledger asks for new rows (SPEC 11: live refresh). */
export const REFRESH_MS = 15000;

/** Plain words for the ledger row types (SPEC 6.2). A back-end test keeps this equal to the ledger's own list. */
export const TYPE_LABELS: Record<string, string> = {
  PLEDGE_AUTHORIZED: "Pledge held",
  PLEDGE_CAPTURED: "Pledge collected",
  PLEDGE_VOIDED: "Hold released",
  PLEDGE_EXPIRED: "Hold expired",
  REFUND: "Refund",
  PAYOUT_SENT: "Paid to the builder",
  PAYOUT_RETURNED: "Payment returned",
  STATE_CHANGE: "Project step",
  BRD_LOCKED: "Brief locked",
  CONTRACT_SIGNED: "Contract signed",
  GUARDIAN_DECISION: "Safety check",
  APPROVAL: "Approval",
  PLAN_EXECUTED: "Plan finished",
};

export function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type;
}

/** Only rows of the chosen types; no choice means everything. */
export function filterRows(rows: LedgerRow[], chosen: ReadonlySet<string>): LedgerRow[] {
  return chosen.size === 0 ? rows : rows.filter((r) => chosen.has(r.type));
}

/** The pinned bottom row: how many rows are shown and what they add up to. The balance is the ledger's own, not recomputed from a filter. */
export function totalsRow(shown: LedgerRow[], balanceCents: number): LedgerRow {
  return {
    seq: 0, created_at: "", bucket: "NONE", type: "TOTALS", counterparty: `Total of ${shown.length} row${shown.length === 1 ? "" : "s"}`,
    amount_cents: shown.reduce((sum, r) => sum + r.amount_cents, 0), running_balance_cents: balanceCents, status: null, paypal_ref: null,
    actor: "", actor_name: "", ref_type: null, ref_id: null, paypal_match: null, alert: false, meta: {},
  };
}

/** The types present, in the order of their first appearance, for the filter chips. */
export function typesPresent(rows: LedgerRow[]): string[] {
  return [...new Set(rows.map((r) => r.type))];
}

export const MATCH_SYMBOL: Record<MatchStatus, { symbol: string; label: string }> = {
  MATCH: { symbol: "✓", label: "PayPal agrees" },
  PENDING: { symbol: "⏳", label: "Not final at PayPal yet" },
  MISMATCH: { symbol: "✗", label: "PayPal disagrees" },
  NOT_FOUND: { symbol: "✗", label: "PayPal has no such record" },
  UNAVAILABLE: { symbol: "?", label: "PayPal could not be asked" },
};

/** Shorten a PayPal reference for the grid; the full text stays in the tooltip. */
export function shortRef(ref: string | null, keep = 10): string {
  if (!ref) return "";
  return ref.length <= keep + 1 ? ref : `${ref.slice(0, keep)}…`;
}

/** The signed amount for display: zero means a note, not money. */
export function amountText(cents: number): string {
  return cents === 0 ? "–" : formatMoney(cents);
}

/**
 * CSV export (SPEC 11): text that starts with = + - @ (or a tab or carriage return) could run as a formula when the file is
 * opened in a spreadsheet, so it is prefixed with an apostrophe. Numbers are exported as whole cents-derived text, never touched.
 */
export function csvSafe(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /^[=+\-@\t\r]/.test(text) && Number.isNaN(Number(text)) ? `'${text}` : text;
}

export function csvCell(value: unknown): string {
  const text = csvSafe(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

const CSV_COLUMNS: [string, (r: LedgerRow) => unknown][] = [
  ["seq", (r) => r.seq], ["time", (r) => r.created_at], ["bucket", (r) => r.bucket], ["type", (r) => r.type], ["counterparty", (r) => r.counterparty],
  ["amount", (r) => (r.amount_cents / 100).toFixed(2)], ["pool_balance", (r) => (r.running_balance_cents / 100).toFixed(2)], ["status", (r) => r.status],
  ["paypal_ref", (r) => r.paypal_ref], ["by", (r) => r.actor_name],
];

export function toCsv(rows: LedgerRow[]): string {
  const lines = [CSV_COLUMNS.map(([name]) => name).join(",")];
  for (const r of rows) lines.push(CSV_COLUMNS.map(([, get]) => csvCell(get(r))).join(","));
  return lines.join("\r\n") + "\r\n";
}
