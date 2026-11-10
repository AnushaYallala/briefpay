/** BA Studio logic (SPEC 11, screen 4), kept apart from the screens so it can be tested on its own. */
import type { Tone } from "./states";
import type { BaDimension, BaHistory, BaQuestion } from "./types";

/** How often the open studio asks for news, and how often it asks about a run it started. */
export const BA_REFRESH_MS = 8000;
export const JOB_POLL_MS = 2000;

export const SESSION_STATES: Record<string, { label: string; tone: Tone; hint: string }> = {
  ACTIVE: { label: "In progress", tone: "blue", hint: "The analyst is still collecting details." },
  READY: { label: "Ready for the brief", tone: "green", hint: "The score has reached the line. The brief can be written." },
  MAX_ROUNDS: { label: "Round limit reached", tone: "amber", hint: "The lead can accept the gaps that are left and move on." },
  FINALIZED: { label: "Accepted with gaps", tone: "amber", hint: "The lead accepted what is known. The brief can be written." },
  BRD_GENERATED: { label: "Brief written", tone: "green", hint: "The analysis is closed: the brief has been written." },
};

export const QUESTION_STATES: Record<string, { label: string; tone: Tone }> = {
  OPEN: { label: "Waiting for an answer", tone: "amber" },
  ANSWERED: { label: "Answered", tone: "green" },
  SKIPPED: { label: "Skipped", tone: "grey" },
};

export const sessionState = (state: string) => SESSION_STATES[state] ?? { label: state, tone: "grey" as Tone, hint: "" };
export const questionState = (status: string) => QUESTION_STATES[status] ?? { label: status, tone: "grey" as Tone };

/** A source reference points at transcript lines ("L3", "L3-L5") or at an answer ("answer:12"). Lines come back as a range, answers as null. */
export function parseRef(ref: string): { from: number; to: number } | null {
  const m = /^L(\d+)(?:-L(\d+))?$/.exec(ref.trim());
  if (!m) return null;
  const from = Number(m[1]);
  const to = m[2] === undefined ? from : Number(m[2]);
  return from >= 1 && to >= from ? { from, to } : null;
}

/** Every transcript line named by these references. */
export function refLines(refs: string[]): Set<number> {
  const out = new Set<number>();
  for (const r of refs) {
    const p = parseRef(r);
    if (p) for (let n = p.from; n <= p.to && n - p.from < 5000; n += 1) out.add(n);
  }
  return out;
}

export const refWords = (ref: string) => {
  if (ref.startsWith("answer:")) return `answer ${ref.slice(7)}`;
  const p = parseRef(ref);
  return p ? (p.from === p.to ? `line ${p.from}` : `lines ${p.from} to ${p.to}`) : ref;
};

/** Marks of 100 this dimension earned (its weight times what the evidence supports) and out of how many. */
export const points = (d: Pick<BaDimension, "weight" | "coverage_effective">) => Math.round(d.weight * d.coverage_effective * 10) / 10;

export const percent = (fraction: number) => Math.max(0, Math.min(100, Math.round(fraction * 100)));

/** Who a question is for, in words. "ALL" means any sponsor may answer. */
export function addressedText(addressed: (number | string)[], names: Record<number, string>): string {
  if (addressed.includes("ALL")) return "Anyone on the sponsor side";
  const who = addressed.map((a) => (typeof a === "number" ? names[a] ?? "someone" : "someone"));
  return who.join(" and ");
}

/** Questions grouped by round, newest round first; inside a round, open ones first. */
export function groupQuestions(questions: BaQuestion[]): { round: number; questions: BaQuestion[] }[] {
  const rounds = [...new Set(questions.map((q) => q.round))].sort((a, b) => b - a);
  return rounds.map((round) => ({
    round,
    questions: questions.filter((q) => q.round === round).sort((a, b) => Number(b.status === "OPEN") - Number(a.status === "OPEN") || a.id - b.id),
  }));
}

/** Points for a small line chart of the score after each round (x spread evenly, y from 0 to 100 top to bottom). */
export function sparkPoints(history: Pick<BaHistory, "total">[], width: number, height: number): string {
  const step = history.length === 1 ? 0 : width / (history.length - 1);
  return history.map((h, i) => `${Math.round(i * step * 10) / 10},${Math.round((height - (Math.max(0, Math.min(100, h.total)) / 100) * height) * 10) / 10}`).join(" ");
}

export const sparkY = (score: number, height: number) => Math.round((height - (Math.max(0, Math.min(100, score)) / 100) * height) * 10) / 10;

/** The transcript text for a pasted upload needs something in it. */
export const canUpload = (text: string) => text.trim().length > 0;
