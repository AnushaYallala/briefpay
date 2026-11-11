"use client";
import { useCallback, useState } from "react";
import { Badge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { nudgeLabel, percentWords, whatsappUrl } from "@/lib/campaign";
import { formatMoney } from "@/lib/money";
import { formatDateTime } from "@/lib/time";
import type { StrategistReport } from "@/lib/types";
import { useJob } from "@/lib/useJob";

const said = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

/** The Strategist's report for the lead: an honest estimate, deadline advice with one-click apply, and nudge drafts to copy or send. The AI only words it; the numbers are computed by code. */
export function StrategistCard({ campaignId, currency, report, missing, reload, onApplied }: {
  campaignId: number; currency: string; report: StrategistReport | null; missing: boolean; reload: () => void; onApplied: () => void;
}) {
  const [job, setJob] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [copied, setCopied] = useState<number | null>(null);
  const done = useCallback(() => { setJob(null); reload(); }, [reload]);
  const failed = useCallback((m: string) => { setJob(null); setProblem(`The Strategist could not finish. ${m}`); }, []);
  useJob(job, done, failed);

  async function run() {
    setBusy("run");
    setProblem(null);
    try { const r = await api<{ job_id: number }>(`/campaigns/${campaignId}/strategist/run`, { method: "POST" }); setJob(r.job_id); } catch (e) { setProblem(said(e)); } finally { setBusy(null); }
  }
  async function apply(deadline: string) {
    setBusy("apply");
    setProblem(null);
    try { await api(`/campaigns/${campaignId}/strategist/apply`, { method: "POST", body: { deadline_at: deadline } }); onApplied(); reload(); } catch (e) { setProblem(said(e)); } finally { setBusy(null); }
  }
  async function copy(i: number, text: string) {
    try { await navigator.clipboard.writeText(text); setCopied(i); } catch { setProblem("Could not copy. Select the message and copy it by hand."); }
  }

  const f = report?.forecast;
  const adv = report?.suggestions.deadline ?? null;
  return (
    <section aria-label="Strategist" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-bold text-slate-900">Strategist</h2>
        <button disabled={busy !== null || job !== null} onClick={() => void run()} className="rounded bg-sea-600 px-3 py-1.5 text-sm text-white hover:bg-sea-700 disabled:opacity-60">{report ? "Update the forecast" : "Run the Strategist"}</button>
      </div>
      {job !== null && <p role="status" className="rounded bg-sea-50 p-2 text-sm text-sea-700">The Strategist is working. This takes a short while.</p>}
      {problem && <p role="alert" className="rounded bg-red-50 p-2 text-sm text-red-800">{problem}</p>}
      {!report && missing && job === null && <p className="text-sm text-gray-600" data-testid="no-report">No forecast yet. Run the Strategist to see how likely the goal is and who to nudge.</p>}
      {report && f && (
        <div className="space-y-3">
          <div data-testid="forecast">
            <p className="text-xs uppercase tracking-wide text-gray-500">{f.label}</p>
            <p className="text-lg font-semibold" data-testid="headline">{report.narrative.headline}</p>
            <p className="text-sm text-gray-700">{report.narrative.explanation}</p>
            <p className="mt-1 text-sm text-gray-600">Chance of reaching the goal: <strong data-testid="probability">{percentWords(f.probability)}</strong> · expected {formatMoney(f.projected_cents, currency)} of {formatMoney(f.goal_cents, currency)} · {f.hours_left} h left</p>
            {report.narrative.risk_factors.length > 0 && <ul className="mt-1 list-disc pl-5 text-sm text-amber-800" aria-label="Risks">{report.narrative.risk_factors.map((r, i) => <li key={i}>{r}</li>)}</ul>}
            <p className="mt-1 text-xs text-gray-500" data-testid="source">{report.narrative.source === "TEMPLATE" ? "Worded by a template" : "Worded by the AI"}; every number is computed by the system. Made {formatDateTime(report.created_at)}.</p>
          </div>
          {adv && (
            <div className="rounded-lg bg-sea-50 p-3 text-sm" data-testid="advice">
              <p className="font-medium">Suggested deadline: {formatDateTime(adv.deadline_at)}</p>
              <p className="text-gray-700">{adv.reason}</p>
              <button disabled={busy !== null} onClick={() => void apply(adv.deadline_at)} className="mt-2 rounded border border-sea-600 bg-white px-3 py-1 text-sea-700 hover:bg-sea-100 disabled:opacity-60">{busy === "apply" ? "Applying..." : "Apply this deadline"}</button>
            </div>
          )}
          {report.suggestions.applied_extension && <p className="text-sm text-gray-600" data-testid="extended">The deadline was extended once, from {formatDateTime(report.suggestions.applied_extension.from)} to {formatDateTime(report.suggestions.applied_extension.to)}. It cannot be extended again.</p>}
          {report.nudges.length > 0 && (
            <div>
              <h3 className="font-medium">Messages to send</h3>
              <ul className="space-y-2" aria-label="Nudges">
                {report.nudges.map((n, i) => (
                  <li key={n.member_id} className="rounded border border-gray-200 p-2 text-sm" data-source={n.source}>
                    <p className="flex items-center justify-between gap-2"><strong>{n.name}</strong><Badge tone={n.source === "TEMPLATE" ? "grey" : "blue"}>{nudgeLabel(n)}</Badge></p>
                    <p className="text-xs text-gray-500">{report.suggestions.nudge_targets.find((t) => t.member_id === n.member_id)?.reason}</p>
                    <p className="mt-1 whitespace-pre-wrap">{n.message}</p>
                    <div className="mt-1 flex gap-3">
                      <button onClick={() => void copy(i, n.message)} className="text-sea-700 underline">{copied === i ? "Copied" : "Copy"}</button>
                      <a href={whatsappUrl(n.message)} target="_blank" rel="noopener noreferrer" className="text-sea-700 underline">Open in WhatsApp</a>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

