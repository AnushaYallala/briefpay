/** AI audit trail logic (SPEC 11, screen 13), kept apart from the grid so it can be tested on its own. */
import type { AgentRun } from "./types";
import type { Tone } from "./states";

/** How often the open audit trail asks for new rows. */
export const AUDIT_REFRESH_MS = 20000;

/** Plain words for every agent that writes audit rows. A back-end test keeps this equal to the agents' own names. */
export const AGENT_LABELS: Record<string, string> = {
  BA_SCORE: "Business analyst: scoring",
  BA_QUESTIONS: "Business analyst: questions",
  BRD_GEN: "Brief writer",
  VERIFY_QUESTIONS: "Verifier: questions",
  VERIFY_JUDGE: "Verifier: judge",
  GUARDIAN_LLM: "Guardian: second opinion",
  STRATEGIST: "Strategist",
};

export const RUN_STATUS: Record<string, { label: string; tone: Tone }> = {
  OK: { label: "Answered", tone: "green" },
  REPLAYED: { label: "Replayed from a recording", tone: "blue" },
  SCHEMA_INVALID: { label: "Answer was malformed", tone: "red" },
  ERROR: { label: "Failed", tone: "red" },
};

export const agentLabel = (agent: string) => AGENT_LABELS[agent] ?? agent;
export const statusInfo = (status: string) => RUN_STATUS[status] ?? { label: status, tone: "grey" as Tone };

/** Only the runs of the chosen agent; null means all. */
export function filterRuns(runs: AgentRun[], agent: string | null): AgentRun[] {
  return agent === null ? runs : runs.filter((r) => r.agent === agent);
}

/** The agents present, in the order of first appearance, for the filter chips. */
export function agentsPresent(runs: AgentRun[]): string[] {
  return [...new Set(runs.map((r) => r.agent))];
}

export type AuditSummary = { runs: number; failed: number; avgLatencyMs: number; tokens: number };

export function summarize(runs: AgentRun[]): AuditSummary {
  const failed = runs.filter((r) => r.status === "ERROR" || r.status === "SCHEMA_INVALID").length;
  const latency = runs.reduce((s, r) => s + r.latency_ms, 0);
  const tokens = runs.reduce((s, r) => s + (r.input_tokens ?? 0) + (r.output_tokens ?? 0), 0);
  return { runs: runs.length, failed, avgLatencyMs: runs.length === 0 ? 0 : Math.round(latency / runs.length), tokens };
}

/** First characters of a hash for the grid; the full text stays in the tooltip. */
export function shortHash(hash: string, keep = 8): string {
  return hash.slice(0, keep);
}

export function latencyText(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}
