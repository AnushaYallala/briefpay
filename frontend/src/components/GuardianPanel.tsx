"use client";
import { Badge } from "@/components/ui";
import { decisionInfo, ruleCounts, ruleStatus } from "@/lib/plans";
import { formatDateTime } from "@/lib/time";
import type { GuardianReview, LlmReview } from "@/lib/types";

/** The rule list of one Guardian review: a mark, the rule's name and its one-line explanation. PayPal-proved rules say so. */
export function RuleList({ review }: { review: GuardianReview }) {
  const n = ruleCounts(review.rules);
  return (
    <div>
      <p className="text-sm text-gray-700" data-testid="rule-counts">{n.PASS} of {review.rules.length} rules passed{n.FAIL ? `, ${n.FAIL} failed` : ""}{n.UNVERIFIED ? `, ${n.UNVERIFIED} could not be proved` : ""}{n.SKIPPED ? `, ${n.SKIPPED} not checked` : ""}.</p>
      <ul className="mt-2 divide-y divide-gray-100 text-sm" aria-label="Guardian rules">
        {review.rules.map((r) => {
          const s = ruleStatus(r.status);
          return (
            <li key={r.id} className={`flex gap-3 py-2 ${r.status === "FAIL" ? "bg-red-50" : ""}`} data-rule={r.id} data-status={r.status}>
              <span aria-label={s.label} title={s.label} className={`w-5 text-center font-bold ${s.tone === "green" ? "text-green-700" : s.tone === "red" ? "text-red-700" : s.tone === "amber" ? "text-amber-700" : "text-gray-400"}`}>{s.symbol}</span>
              <span>
                <span className="font-medium">{r.id} {r.title}</span>
                {r.paypal_verified && <span className="ml-2 rounded bg-sea-100 px-1.5 py-0.5 text-xs text-sea-700">verified with PayPal (APIMatic SDK)</span>}
                <span className="block text-gray-600">{r.detail}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function LlmCard({ llm }: { llm: LlmReview | null }) {
  if (llm === null) return <p className="text-sm text-gray-600">No AI risk review for this plan.</p>;
  if (llm.status === "SKIPPED") return <p className="text-sm text-gray-600">Not run: {llm.reason ?? "a hard rule already blocked the plan"}.</p>;
  if (llm.status === "UNAVAILABLE") return <p role="alert" className="rounded bg-amber-50 p-2 text-sm text-amber-800">{llm.explanation_for_sponsors}</p>;
  return (
    <div className="text-sm">
      <p>Risk level: <Badge tone={llm.risk_level === "high" ? "red" : llm.risk_level === "medium" ? "amber" : "green"}>{llm.risk_level ?? "unknown"}</Badge></p>
      <p className="mt-1 text-gray-700">{llm.explanation_for_sponsors}</p>
      {(llm.findings ?? []).length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-gray-600">{(llm.findings ?? []).map((f, i) => <li key={i}>{f.type}: {f.detail}</li>)}</ul>
      )}
      <p className="mt-1 text-xs text-gray-500">The AI can only raise the caution level. Fixed rules decide.</p>
    </div>
  );
}

/** One review: decision badge, rule list, soft flags and the AI risk card. `simulated` labels a tamper test. */
export function GuardianPanel({ review, title }: { review: GuardianReview; title: string }) {
  const d = decisionInfo(review.decision);
  return (
    <section aria-label={title} className="space-y-3 rounded-xl border border-gray-200 bg-white p-4" data-testid="guardian-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">{title}</h3>
        <span className="flex items-center gap-2"><span className="text-xs text-gray-500">{formatDateTime(review.created_at)}</span><Badge tone={d.tone}>{d.label}</Badge></span>
      </div>
      <p className="text-sm text-gray-600">{d.hint}</p>
      {review.simulated && <p className="rounded bg-blue-50 p-2 text-sm text-blue-800">Simulation: this is a test on a tampered copy. PayPal was never contacted and nothing can run from it.</p>}
      <RuleList review={review} />
      {review.soft_flags.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold">Cautions (a person must look)</h4>
          <ul className="mt-1 list-disc pl-5 text-sm text-amber-800" aria-label="Cautions">
            {review.soft_flags.map((f) => <li key={f.id}>{f.id} {f.title}: {f.detail}</li>)}
          </ul>
        </div>
      )}
      {!review.simulated && (
        <div>
          <h4 className="text-sm font-semibold">AI risk review</h4>
          <LlmCard llm={review.llm} />
        </div>
      )}
    </section>
  );
}
