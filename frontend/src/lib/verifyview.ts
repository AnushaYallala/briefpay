/** Small, tested helpers for the brief, submit and verify screens, so what they show is what the API really sends. */
import type { Tone } from "./states";

export const BRD_STATUS: Record<string, { label: string; tone: Tone }> = {
  DRAFT: { label: "Draft", tone: "grey" },
  PENDING_APPROVAL: { label: "Waiting for the sponsors", tone: "amber" },
  APPROVED: { label: "Approved and locked", tone: "green" },
  SUPERSEDED: { label: "Replaced by a newer version", tone: "grey" },
};

export const brdStatus = (status: string) => BRD_STATUS[status] ?? { label: status, tone: "grey" as Tone };

/** Sponsors can decide only on the version that is open for decisions. */
export const brdIsOpen = (status: string) => status === "PENDING_APPROVAL";

/** What one automatic check looked at, in a few words. Gate checks (the repository, the commit) look at nothing in particular. */
export function checkTarget(input: Record<string, unknown> | null | undefined): string {
  const i = input ?? {};
  const path = typeof i.path === "string" ? i.path : "";
  const text = typeof i.text === "string" ? i.text : "";
  if (path && text) return `${path} contains “${text}”`;
  return path;
}

/** The server's own words when it refused, otherwise a plain fallback. Used to show a failed load instead of a blank page. */
export function problemText(err: unknown, fallback = "Could not load this just now."): string {
  const message = err instanceof Error ? err.message : "";
  return message || fallback;
}

/** The display name of a project member, for sentences that must name the real person, never a demo one. */
export function memberName(members: { id: number; display_name: string }[] | undefined, id: number | null | undefined, fallback: string): string {
  return members?.find((m) => m.id === id)?.display_name || fallback;
}

export function leadName(members: { role: string; display_name: string }[] | undefined): string {
  return members?.find((m) => m.role === "LEAD")?.display_name || "the project lead";
}
