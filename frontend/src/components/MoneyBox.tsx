"use client";
import { Empty, ErrorBox, Loading } from "@/components/ui";
import Link from "next/link";
import { formatMoney } from "@/lib/money";
import { PLAN_WORDS } from "@/lib/plans";
import { formatDateTime } from "@/lib/time";
import type { Money } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { DollarSign, ShieldAlert, AlertTriangle, ArrowRight, RefreshCw } from "lucide-react";

/** The Money box (SPEC 11, screen 3): what is really in the pool, what is only a hold, and what needs attention. Members only. */
export function MoneyBox({ projectId, currency = "USD" }: { projectId: number; currency?: string }) {
  const { data, error, loading, slow, reload } = useApi<Money>(`/projects/${projectId}/money`);

  return (
    <section aria-label="Money" className="card card-pad bg-white rounded-2xl border border-sand-200 shadow-card">
      <div className="mb-4 flex items-center justify-between border-b border-sand-100 pb-3">
        <div className="flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-sea-600" />
          <h2 className="font-bold text-ink-900">Money</h2>
          <span className="rounded-full bg-sand-100 border border-sand-200/60 px-2 py-0.5 text-2xs font-semibold text-ink-600">
            PayPal Vault
          </span>
        </div>
        <button
          onClick={reload}
          className="text-xs font-semibold text-sea-600 hover:text-sea-700 hover:underline transition-colors flex items-center gap-1"
        >
          <span>Refresh</span>
        </button>
      </div>

      {loading && <Loading what="Loading the money box" slow={slow} />}
      {error && <ErrorBox error={error} onRetry={reload} />}

      {data && !loading && !error && (
        <div className="space-y-4 text-sm">
          {/* Pool Tile */}
          <div className="rounded-2xl border border-sea-200/80 bg-gradient-to-br from-sea-50/70 to-white p-4 shadow-2xs">
            <p className="text-2xs font-bold uppercase tracking-wider text-sea-800">
              Held in the project pool
            </p>
            <p className="mt-1 text-2xl sm:text-3xl font-extrabold tracking-tight text-ink-900" data-testid="pool">
              {formatMoney(data.pool_balance_cents, currency)}
            </p>
          </div>

          {/* Holds Tile */}
          <div className="rounded-2xl border border-sand-200 bg-sand-50/60 p-4 space-y-1.5 shadow-2xs">
            <p className="text-2xs font-bold uppercase tracking-wider text-ink-500">
              Pledged, not charged
            </p>
            <p className="text-base font-bold text-ink-900" data-testid="holds">
              {data.holds.count === 0
                ? "No holds"
                : `${formatMoney(data.holds.total_cents, currency)} in ${data.holds.count} hold${
                    data.holds.count === 1 ? "" : "s"
                  }`}
            </p>
            <p className="text-xs text-ink-500 leading-relaxed">{data.holds.note}</p>
            {data.next_honor_deadline && (
              <p className="text-xs font-medium text-amber-700 flex items-center gap-1 pt-1">
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                <span>Holds must be used or released by {formatDateTime(data.next_honor_deadline)}.</span>
              </p>
            )}
          </div>

          {data.contract_amount_cents !== null && (
            <div className="flex items-center justify-between text-xs py-1 border-b border-sand-100">
              <span className="font-semibold text-ink-500">Contract price:</span>
              <span className="font-bold text-ink-900">{formatMoney(data.contract_amount_cents, currency)}</span>
            </div>
          )}

          {data.open_plans.length > 0 && (
            <div className="rounded-xl border border-sea-200 bg-sea-50/50 p-3.5 space-y-2">
              <p className="text-2xs font-bold uppercase tracking-wider text-sea-800">
                Money plans in progress
              </p>
              <ul className="list-disc pl-5 space-y-1 text-xs">
                {data.open_plans.map((p) => (
                  <li key={p.id}>
                    <Link
                      href={`/plans?id=${projectId}&plan=${p.id}`}
                      className="font-semibold text-sea-700 hover:text-sea-800 underline"
                    >
                      {PLAN_WORDS[p.kind] ?? p.kind}
                    </Link>
                    : {p.state.toLowerCase()}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="pt-1">
            <Link
              href={`/plans?id=${projectId}`}
              className="inline-flex items-center gap-1 text-xs font-semibold text-sea-600 hover:text-sea-700 underline group"
            >
              <span>See all the money plans</span>
              <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </div>

          {data.unclaimed_payouts > 0 && (
            <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-medium text-amber-900 shadow-2xs">
              A payment is waiting for the builder to claim it at PayPal.
            </p>
          )}

          {data.alerts.length > 0 && (
            <p role="alert" className="rounded-xl border border-coral-200 bg-coral-50 p-3 text-xs font-medium text-coral-900 shadow-2xs">
              {data.alerts.length} item{data.alerts.length === 1 ? "" : "s"} need attention: PayPal reported something different from our records.
            </p>
          )}

          {data.pool_balance_cents === 0 &&
            data.holds.count === 0 &&
            data.open_plans.length === 0 &&
            data.alerts.length === 0 && (
              <Empty title="No money has moved yet" />
            )}
        </div>
      )}
    </section>
  );
}
