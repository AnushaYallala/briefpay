"use client";
import { Empty, ErrorBox, Loading } from "@/components/ui";
import { formatMoney } from "@/lib/money";
import { formatDateTime } from "@/lib/time";
import type { Money } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const PLAN_WORDS: Record<string, string> = {
  CAPTURE_PLEDGES: "Collect the pledges", RELEASE_HOLDS: "Release the holds", FREELANCER_PAYOUT: "Pay the builder", REFUND_CAPTURED: "Refund the pledgers",
};

/** The Money box (SPEC 11, screen 3): what is really in the pool, what is only a hold, and what needs attention. Members only. */
export function MoneyBox({ projectId, currency = "USD" }: { projectId: number; currency?: string }) {
  const { data, error, loading, slow, reload } = useApi<Money>(`/projects/${projectId}/money`);
  return (
    <section aria-label="Money" className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold">Money</h2>
        <button onClick={reload} className="text-sm text-sea-700 hover:underline">Refresh</button>
      </div>
      {loading && <Loading what="Loading the money box" slow={slow} />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && !loading && !error && (
        <div className="space-y-3 text-sm">
          <div>
            <p className="text-xs uppercase tracking-wide text-gray-500">Held in the project pool</p>
            <p className="text-2xl font-bold" data-testid="pool">{formatMoney(data.pool_balance_cents, currency)}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-gray-500">Pledged, not charged</p>
            <p data-testid="holds">{data.holds.count === 0 ? "No holds" : `${formatMoney(data.holds.total_cents, currency)} in ${data.holds.count} hold${data.holds.count === 1 ? "" : "s"}`}</p>
            <p className="text-xs text-gray-500">{data.holds.note}</p>
            {data.next_honor_deadline && <p className="text-xs text-amber-700">Holds must be used or released by {formatDateTime(data.next_honor_deadline)}.</p>}
          </div>
          {data.contract_amount_cents !== null && (
            <p><span className="text-gray-500">Contract price:</span> {formatMoney(data.contract_amount_cents, currency)}</p>
          )}
          {data.open_plans.length > 0 && (
            <div>
              <p className="text-xs uppercase tracking-wide text-gray-500">Money plans in progress</p>
              <ul className="list-disc pl-5">
                {data.open_plans.map((p) => <li key={p.id}>{PLAN_WORDS[p.kind] ?? p.kind}: {p.state.toLowerCase()}</li>)}
              </ul>
            </div>
          )}
          {data.unclaimed_payouts > 0 && (
            <p className="rounded bg-amber-50 p-2 text-amber-800">A payment is waiting for the builder to claim it at PayPal.</p>
          )}
          {data.alerts.length > 0 && (
            <p role="alert" className="rounded bg-red-50 p-2 text-red-800">
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
