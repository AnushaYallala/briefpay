"use client";
import { useCallback, useState } from "react";
import { AlertTriangle, CalendarCheck2, Check, Copy, ExternalLink, Loader2, RefreshCw, Sparkles } from "lucide-react";
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
    <section aria-label="Strategist" className="rounded-2xl border border-slate-200/90 bg-white shadow-card overflow-hidden">
      <div className="border-b border-slate-100 bg-gradient-to-r from-slate-50/90 to-white px-5 py-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-700 border border-blue-100">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-base font-bold text-slate-900">Campaign Strategist</h2>
            <p className="text-xs text-slate-500 mt-0.5">Deterministic forecast &amp; stakeholder outreach guidance</p>
          </div>
        </div>
        <button
          disabled={busy !== null || job !== null}
          onClick={() => void run()}
          className="btn-primary px-3.5 py-1.5 text-xs sm:text-sm"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${job !== null ? "animate-spin" : ""}`} aria-hidden="true" />
          <span>{report ? "Update the forecast" : "Run the Strategist"}</span>
        </button>
      </div>

      <div className="p-5 sm:p-6 space-y-4">
        {job !== null && (
          <p role="status" className="flex items-center gap-2.5 rounded-xl border border-sea-200 bg-sea-50/80 px-3.5 py-2.5 text-sm font-medium text-sea-900">
            <Loader2 className="h-4 w-4 animate-spin text-sea-600 shrink-0" aria-hidden="true" />
            <span>The Strategist is working. This takes a short while.</span>
          </p>
        )}
        {problem && (
          <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm font-medium text-red-800">
            {problem}
          </p>
        )}
        {!report && missing && job === null && (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-4 text-sm text-slate-600" data-testid="no-report">
            No forecast yet. Run the Strategist to see how likely the goal is and who to nudge.
          </div>
        )}

        {report && f && (
          <div className="space-y-4">
            <div className="rounded-xl border border-slate-200/90 bg-slate-50/60 p-4 space-y-3" data-testid="forecast">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{f.label}</p>
                <span className="inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-0.5 text-xs font-bold text-sea-800 border border-slate-200 shadow-2xs">
                  Success probability:{" "}
                  <strong className="text-sea-700" data-testid="probability">{percentWords(f.probability)}</strong>
                </span>
              </div>
              <p className="text-base sm:text-lg font-bold text-slate-900 leading-snug" data-testid="headline">
                {report.narrative.headline}
              </p>
              <p className="text-sm text-slate-700 leading-relaxed">{report.narrative.explanation}</p>
              <p className="text-xs font-medium text-slate-600 pt-1 border-t border-slate-200/70">
                Chance of reaching the goal: <span className="font-bold text-slate-800">{percentWords(f.probability)}</span> · expected {formatMoney(f.projected_cents, currency)} of {formatMoney(f.goal_cents, currency)} · {f.hours_left} h left
              </p>
              {report.narrative.risk_factors.length > 0 && (
                <div className="rounded-lg border border-amber-200/80 bg-amber-50/70 p-3">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-amber-800 flex items-center gap-1.5 mb-1">
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    <span>Key Risk Signals</span>
                  </p>
                  <ul className="list-disc pl-5 text-xs sm:text-sm text-amber-900 space-y-0.5" aria-label="Risks">
                    {report.narrative.risk_factors.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}
              <p className="text-xs text-slate-500" data-testid="source">
                {report.narrative.source === "TEMPLATE" ? "Worded by a template" : "Worded by the AI"}; every number is computed by the system. Made {formatDateTime(report.created_at)}.
              </p>
            </div>

            {adv && (
              <div className="rounded-xl border border-sea-200 bg-sea-50/60 p-4 text-sm space-y-2" data-testid="advice">
                <div className="flex items-start gap-2">
                  <CalendarCheck2 className="h-4 w-4 text-sea-700 mt-0.5 shrink-0" aria-hidden="true" />
                  <div>
                    <p className="font-bold text-slate-900">Suggested deadline: {formatDateTime(adv.deadline_at)}</p>
                    <p className="text-xs sm:text-sm text-slate-700 mt-0.5 leading-relaxed">{adv.reason}</p>
                  </div>
                </div>
                <button
                  disabled={busy !== null}
                  onClick={() => void apply(adv.deadline_at)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-sea-600 bg-white px-3.5 py-1.5 text-xs sm:text-sm font-semibold text-sea-700 hover:bg-sea-50 transition disabled:opacity-60"
                >
                  {busy === "apply" ? "Applying..." : "Apply this deadline"}
                </button>
              </div>
            )}

            {report.suggestions.applied_extension && (
              <p className="rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs sm:text-sm text-slate-700" data-testid="extended">
                The deadline was extended once, from {formatDateTime(report.suggestions.applied_extension.from)} to {formatDateTime(report.suggestions.applied_extension.to)}. It cannot be extended again.
              </p>
            )}

            {report.nudges.length > 0 && (
              <div className="space-y-3 pt-1">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">Stakeholder Outreach Drafts</h3>
                  <span className="text-xs text-slate-400">{report.nudges.length} outreach draft{report.nudges.length === 1 ? "" : "s"}</span>
                </div>
                <ul className="space-y-3" aria-label="Nudges">
                  {report.nudges.map((n, i) => (
                    <li key={n.member_id} className="rounded-xl border border-slate-200 bg-slate-50/50 p-3.5 text-sm space-y-2" data-source={n.source}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <strong className="text-slate-900 font-bold">{n.name}</strong>
                        <Badge tone={n.source === "TEMPLATE" ? "grey" : "blue"}>{nudgeLabel(n)}</Badge>
                      </div>
                      <p className="text-xs text-slate-500 first-letter:uppercase">
                        {report.suggestions.nudge_targets.find((t) => t.member_id === n.member_id)?.reason}
                      </p>
                      <p className="whitespace-pre-wrap rounded-lg border border-slate-200/80 bg-white p-3 text-xs sm:text-sm text-slate-800 leading-relaxed">
                        {n.message}
                      </p>
                      <div className="flex flex-wrap items-center gap-2 pt-0.5">
                        <button
                          onClick={() => void copy(i, n.message)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                        >
                          {copied === i ? <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />}
                          <span>{copied === i ? "Copied" : "Copy"}</span>
                        </button>
                        <a
                          href={whatsappUrl(n.message)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800 hover:bg-emerald-100 transition"
                        >
                          <ExternalLink className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />
                          <span>Open in WhatsApp</span>
                        </a>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

