"use client";
import { Empty, ErrorBox, Loading } from "@/components/ui";
import Link from "next/link";
import { formatMoney } from "@/lib/money";
import { PLAN_WORDS } from "@/lib/plans";
import { formatDateTime } from "@/lib/time";
import type { Money } from "@/lib/types";
import { useApi } from "@/lib/useApi";


/** The Money box (SPEC 11, screen 3): what is really in the pool, what is only a hold, and what needs attention. Members only. */
export function MoneyBox({ projectId, currency = "USD" }: { projectId: number; currency?: string }) {
  const { data, error, loading, slow, reload } = useApi<Money>(`/projects/${projectId}/money`);
  return (
    <section aria-label="Money" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
      <div className="mb-4 flex items-center justify-between border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2">
          <h2 className="font-bold text-slate-900">Money</h2>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">PayPal Vault</span>
        </div>
        <button onClick={reload} className="text-xs font-semibold text-sea-700 hover:text-sea-800 hover:underline transition">Refresh</button>
      </div>
      {loading && <Loading what="Loading the money box" slow={slow} />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && !loading && !error && (
        <div className="space-y-4 text-sm">
          <div className="rounded-xl border border-slate-100 bg-slate-50/80 p-3.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Held in the project pool</p>
            <p className="mt-0.5 text-2xl font-black tracking-tight text-slate-900" data-testid="pool">{formatMoney(data.pool_balance_cents, currency)}</p>
          </div>
          <div className="rounded-xl border border-slate-100 bg-slate-50/80 p-3.5 space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Pledged, not charged</p>
            <p className="text-base font-bold text-slate-900" data-testid="holds">{data.holds.count === 0 ? "No holds" : `${formatMoney(data.holds.total_cents, currency)} in ${data.holds.count} hold${data.holds.count === 1 ? "" : "s"}`}</p>
            <p className="text-xs text-slate-500 leading-relaxed">{data.holds.note}</p>
            {data.next_honor_deadline && <p className="text-xs font-medium text-amber-700">Holds must be used or released by {formatDateTime(data.next_honor_deadline)}.</p>}
          </div>
          {data.contract_amount_cents !== null && (
            <p className="text-xs text-slate-600"><span className="font-semibold text-slate-500">Contract price:</span> <span className="font-bold text-slate-900">{formatMoney(data.contract_amount_cents, currency)}</span></p>
          )}
          {data.open_plans.length > 0 && (
            <div className="rounded-xl border border-sea-100 bg-sea-50/40 p-3 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-sea-800">Money plans in progress</p>
              <ul className="list-disc pl-5 space-y-1 text-xs">
                {data.open_plans.map((p) => <li key={p.id}><Link href={`/plans?id=${projectId}&plan=${p.id}`} className="font-semibold text-sea-700 underline">{PLAN_WORDS[p.kind] ?? p.kind}</Link>: {p.state.toLowerCase()}</li>)}
              </ul>
            </div>
          )}
          <p className="pt-1 text-xs"><Link href={`/plans?id=${projectId}`} className="font-semibold text-sea-700 hover:text-sea-800 underline">See all the money plans</Link></p>
          {data.unclaimed_payouts > 0 && (
            <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-medium text-amber-900 shadow-2xs">A payment is waiting for the builder to claim it at PayPal.</p>
          )}
          {data.alerts.length > 0 && (
            <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-900 shadow-2xs">
              {data.alerts.length} item{data.alerts.length === 1 ? "" : "s"} need attention: PayPal reported something different from our records.
            </p>
          )}
          {data.pool_balance_cents === 0 && data.holds.count === 0 && data.open_plans.length === 0 && data.alerts.length === 0 && (
            <Empty title="No money has moved yet" />
          )}
        </div>
      )}
    </section>
  );
}
