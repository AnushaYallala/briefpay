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
    <div className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs">
        <div className="mb-2">
          <Link href="/" className="inline-flex items-center gap-1 text-xs font-semibold text-sea-700 hover:text-sea-800 transition">
            <span aria-hidden="true">&larr;</span> All projects
          </Link>
        </div>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">{p.title}</h1>
            {p.location_label && (
              <p className="mt-1 flex items-center gap-1.5 text-xs font-medium text-slate-500">
                <span>📍</span>
                <span>{p.location_label}</span>
              </p>
            )}
          </div>
          <Badge tone={state.tone}>{state.label}</Badge>
        </div>
        {p.summary && <p className="mt-3 max-w-3xl text-sm text-slate-600 leading-relaxed">{p.summary}</p>}

        <div className="mt-6 border-t border-slate-100 pt-5">
          <Stepper state={p.state} />
        </div>
      </div>

      <div className="rounded-xl border border-sea-200/80 bg-sea-50/50 p-4 shadow-xs">
        <div className="flex items-center gap-2 mb-1">
          <span className="flex h-2 w-2 rounded-full bg-sea-600" />
          <span className="text-xs font-bold uppercase tracking-wider text-sea-800">Current Phase & Next Action</span>
        </div>
        <p className="text-sm font-medium text-sea-900 leading-relaxed" data-testid="what-next">{WHAT_NEXT[p.state] ?? ""}</p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs sm:text-sm text-slate-600 shadow-xs flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-800">Transparency Records:</span>
        <Link href={`/ledger?id=${p.id}`} className="font-semibold text-sea-700 hover:text-sea-800 underline">Open the public ledger</Link>: every money and AI event, in order.
        {isMember && (
          <>
            <span className="text-slate-300">|</span>
            <Link href={`/audit?id=${p.id}`} className="font-semibold text-sea-700 hover:text-sea-800 underline">Open the AI audit trail</Link>: every call to an AI helper.
          </>
        )}
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <div className="space-y-6 md:col-span-2">
          <section aria-label="Campaign" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3 border-b border-slate-100 pb-3">
              <h2 className="font-bold text-slate-900">Campaign</h2>
              {c && (
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Round {c.number}: <span className="text-sea-700 font-bold">{campaignState(c.state).label}</span>
                </span>
              )}
            </div>
            {c ? (
              <div className="space-y-2">
                <p className="sr-only">Round {c.number}: {campaignState(c.state).label}</p>
                <PledgeProgress pledgedCents={c.pledged_cents} goalCents={c.goal_cents} count={c.pledge_count} open={c.state === "OPEN"} />
              </div>
            ) : (
              <Empty title="No campaign yet">The campaign starts after the brief is approved and the builder has signed.</Empty>
            )}
          </section>

          <section aria-label="Terms" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs text-sm">
            <h2 className="font-bold text-slate-900 mb-4 border-b border-slate-100 pb-3">Terms</h2>
            <dl className="grid grid-cols-2 gap-y-3">
              <dt className="text-xs font-semibold uppercase tracking-wider text-slate-500">Budget</dt>
              <dd className="font-bold text-slate-900">{formatMoney(p.budget_cents, p.currency)}</dd>
              <dt className="text-xs font-semibold uppercase tracking-wider text-slate-500">Delivery time</dt>
              <dd className="font-medium text-slate-800">{p.delivery_days ? `${p.delivery_days} days` : "not set"}</dd>
              <dt className="text-xs font-semibold uppercase tracking-wider text-slate-500">Payment to the builder</dt>
              <dd className="font-medium text-slate-800">{p.payout_release_policy === "HUMAN" ? "Approved by a person" : "Released automatically when the safety checks allow"}</dd>
            </dl>
          </section>
        </div>

        <div className="space-y-6">
          {isMember ? (
            <MoneyBox projectId={p.id} currency={p.currency} />
          ) : (
            <section aria-label="Money" className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/50 p-5 text-sm text-slate-600 shadow-xs">
              <h2 className="mb-2 font-bold text-slate-800">Money</h2>
              {auth.status === "authed" ? (
                <p>Only the people on this project can see its money box.</p>
              ) : (
                <p>
                  <Link href="/login" className="font-semibold text-sea-700 underline">Sign in</Link> as a member to see the money box.
                </p>
              )}
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
