/** BRD page logic (SPEC 11, screen 5), kept apart from the screens so it can be tested on its own. */
import type { Tone } from "./states";
import type { BrdView } from "./types";

/** How often a document that is waiting for decisions asks for news. */
export const BRD_REFRESH_MS = 10000;

export const BRD_STATES: Record<string, { label: string; tone: Tone; hint: string }> = {
  DRAFT: { label: "Draft", tone: "grey", hint: "Not open for decisions yet." },
  PENDING_APPROVAL: { label: "Waiting for the sponsors", tone: "amber", hint: "Every sponsor must approve this exact document before it is locked." },
  APPROVED: { label: "Approved and locked", tone: "green", hint: "Every sponsor approved. This document can no longer change; the contract is built from it." },
  SUPERSEDED: { label: "Replaced by a newer version", tone: "grey", hint: "This version was replaced. Only the newest version can be decided." },
};

export const EVIDENCE_WORDS: Record<string, string> = {
  SCREENSHOT: "a screenshot", LIVE_URL_CHECK: "a check of the live page", CODE_SNIPPET: "a piece of code", REPO_PATH: "a file in the repository", TEXT: "a written note",
};

export const brdState = (status: string) => BRD_STATES[status] ?? { label: status, tone: "grey" as Tone, hint: "" };

export const priorityTone = (priority: string): Tone => (priority === "MUST" ? "red" : priority === "SHOULD" ? "amber" : "grey");

export const evidenceWords = (types: string[]) => types.map((t) => EVIDENCE_WORDS[t] ?? t).join(", ");

/** What the platform can check by itself for one acceptance criterion, in words. */
export function hintWords(hint: { type: string; path: string | null; text: string | null } | null): string | null {
  if (hint === null) return null;
  switch (hint.type) {
    case "URL_REACHABLE": return `The page ${hint.path} opens`;
    case "PAGE_CONTAINS": return `The page ${hint.path} contains “${hint.text}”`;
    case "FILE_EXISTS": return `The file ${hint.path} exists`;
    case "MOBILE_VIEWPORT": return "The page works on a phone screen";
    default: return hint.type;
  }
}

export const shortHash = (hash: string, keep = 12) => hash.slice(0, keep);
export const nameOf = (names: Record<number, string>, id: number | null) => (id === null ? "nobody yet" : names[id] ?? "someone");
export const namesOf = (names: Record<number, string>, ids: number[]) => (ids.length === 0 ? "nobody yet" : ids.map((i) => nameOf(names, i)).join(", "));

export const progressText = (approved: number, required: number) => `${approved} of ${required} sponsor${required === 1 ? "" : "s"} approved`;

/** Counts the sponsors whose latest decision on this document is an approval. */
export function approvedCount(approvals: BrdView["approvals"]): number {
  return approvals.filter((a) => a.decision === "APPROVE").length;
}

/** Whether this person may decide: a sponsor or the lead, while the project is in review and the document is the open one. */
export const mayDecide = (role: string | null, brdStatus: string, projectState: string) =>
  (role === "LEAD" || role === "SPONSOR") && brdStatus === "PENDING_APPROVAL" && projectState === "BRD_REVIEW";

/** The lead may write the brief while the project is still gathering requirements. */
export const mayGenerate = (role: string | null, projectState: string) => role === "LEAD" && projectState === "REQUIREMENTS";

/** A rejection must say what should change. */
export const rejectReady = (comment: string) => comment.trim() !== "";

export const markdownUrl = (apiBase: string, projectId: number, version: number) => `${apiBase}/projects/${projectId}/brd/${version}.md`;
