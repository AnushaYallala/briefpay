"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { MembersPanel } from "@/components/MembersPanel";
import { MoneyBox } from "@/components/MoneyBox";
import { Stepper } from "@/components/Stepper";
import { Badge, Empty, ErrorBox, Loading, PledgeProgress } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { formatMoney } from "@/lib/money";
import { campaignState, projectState } from "@/lib/states";
import { WHAT_NEXT } from "@/lib/steps";
import type { ProjectDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function Workspace({ id }: { id: number }) {
  const auth = useAuth();
  // the answer depends on who is asking (members see more), so wait for the sign-in check and reload when the person changes
  const { data: p, error, loading, slow, reload } = useApi<ProjectDetail>(auth.status === "loading" ? null : `/projects/${id}`, auth.user?.id ?? null);
  if (auth.status === "loading" || loading) return <Loading what="Loading the project" slow={slow} />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!p) return null;
  const state = projectState(p.state);
  const c = p.campaign;
  const isMember = p.viewer !== null;
  return (
    <div className="space-y-5">
      <div>
        <Link href="/" className="text-sm text-sea-700 hover:underline">All projects</Link>
        <div className="mt-1 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">{p.title}</h1>
            {p.location_label && <p className="text-gray-500">{p.location_label}</p>}
          </div>
          <Badge tone={state.tone}>{state.label}</Badge>
        </div>
        {p.summary && <p className="mt-2 max-w-3xl text-gray-700">{p.summary}</p>}
      </div>

      <Stepper state={p.state} />
      <p className="rounded-lg bg-sea-50 p-3 text-sm text-sea-700" data-testid="what-next">{WHAT_NEXT[p.state] ?? ""}</p>
      <p className="text-sm"><Link href={`/ledger?id=${p.id}`} className="text-sea-700 underline">Open the public ledger</Link>: every money and AI event, in order.</p>

      <div className="grid gap-5 md:grid-cols-3">
        <div className="space-y-5 md:col-span-2">
          <section aria-label="Campaign" className="rounded-xl border border-gray-200 bg-white p-4">
            <h2 className="mb-2 font-semibold">Campaign</h2>
            {c ? (
              <>
                <p className="mb-1 text-xs uppercase tracking-wide text-gray-500">Round {c.number}: {campaignState(c.state).label}</p>
                <PledgeProgress pledgedCents={c.pledged_cents} goalCents={c.goal_cents} count={c.pledge_count} open={c.state === "OPEN"} />
              </>
            ) : (
              <Empty title="No campaign yet">The campaign starts after the brief is approved and the builder has signed.</Empty>
            )}
          </section>
          <section aria-label="Terms" className="rounded-xl border border-gray-200 bg-white p-4 text-sm">
            <h2 className="mb-2 font-semibold">Terms</h2>
            <dl className="grid grid-cols-2 gap-y-1">
              <dt className="text-gray-500">Budget</dt><dd>{formatMoney(p.budget_cents, p.currency)}</dd>
              <dt className="text-gray-500">Delivery time</dt><dd>{p.delivery_days ? `${p.delivery_days} days` : "not set"}</dd>
              <dt className="text-gray-500">Payment to the builder</dt><dd>{p.payout_release_policy === "HUMAN" ? "Approved by a person" : "Released automatically when the safety checks allow"}</dd>
            </dl>
          </section>
        </div>
        <div className="space-y-5">
          {isMember ? (
            <MoneyBox projectId={p.id} currency={p.currency} />
          ) : (
            <section aria-label="Money" className="rounded-xl border border-dashed border-gray-300 p-4 text-sm text-gray-600">
              <h2 className="mb-1 font-semibold text-gray-800">Money</h2>
              {auth.status === "authed" ? "Only the people on this project can see its money box." : <><Link href="/login" className="text-sea-700 underline">Sign in</Link> as a member to see the money box.</>}
            </section>
          )}
          <MembersPanel members={p.members} viewerId={p.viewer?.member_id ?? null} />
        </div>
      </div>
    </div>
  );
}

function FromQuery() {
  const raw = useSearchParams().get("id");
  const id = raw !== null && /^\d{1,9}$/.test(raw) ? Number(raw) : null;
  if (id === null) {
    return <Empty title="No project selected">Open a project from <Link href="/" className="text-sea-700 underline">the project list</Link>.</Empty>;
  }
  return <Workspace id={id} />;
}

export default function ProjectPage() {
  return <Suspense fallback={<Loading what="Loading" />}><FromQuery /></Suspense>;
}
