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
