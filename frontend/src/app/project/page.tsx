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
import { WHAT_NEXT, CTA_OF } from "@/lib/steps";
import type { ProjectDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { MapPin, ArrowRight, ShieldCheck, Lock, Calendar, FileText, CheckCircle2 } from "lucide-react";

function Workspace({ id }: { id: number }) {
  const auth = useAuth();
  // the answer depends on who is asking (members see more), so wait for the sign-in check and reload when the person changes
  const { data: p, error, loading, slow, reload } = useApi<ProjectDetail>(
    auth.status === "loading" ? null : `/projects/${id}`,
    auth.user?.id ?? null
  );

  if (auth.status === "loading" || loading) return <Loading what="Loading the project" slow={slow} />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!p) return null;

  const state = projectState(p.state);
  const c = p.campaign;
  const isMember = p.viewer !== null;

  // Contextual primary CTA depending on project state
  const nextActionCta = (() => {
    switch (p.state) {
      case "DRAFT":
      case "REQUIREMENTS":
        return { label: "Open BA Requirements Studio", href: `/ba?id=${p.id}` };
      case "BRD_REVIEW":
        return { label: "Review & Sign BRD Specification", href: `/brd?id=${p.id}` };
      case "CONTRACTING":
        return { label: "Review & Sign Contract", href: `/contract?id=${p.id}` };
      case "CAMPAIGN_SETUP":
      case "PLEDGING":
        return { label: "View Pledging Campaign", href: `/project?id=${p.id}#campaign` };
      case "IN_PROGRESS":
        return { label: "Freelancer Submission Portal", href: `/submit?id=${p.id}` };
      case "VERIFYING":
        return { label: "View Verification Matrix", href: `/verify?id=${p.id}` };
      case "PAYOUT_READY":
      case "PAYOUT_PENDING":
      case "PAYOUT_FAILED":
        return { label: "Authorize Payout in Payment Guardian", href: `/plans?id=${p.id}` };
      case "PAID":
        return { label: "View Public Immutable Ledger", href: `/ledger?id=${p.id}` };
      default:
        return null;
    }
  })();

  const stepIllustration = (() => {
    switch (p.state) {
      case "REQUIREMENTS": return "step-requirements";
      case "BRD_REVIEW": return "step-brief";
      case "CONTRACTING": return "step-contract";
      case "CAMPAIGN_OPEN":
      case "CAMPAIGN_EXPIRING":
      case "GOAL_REACHED":
      case "CAMPAIGN_FAILED": return "step-campaign";
      case "BUILDING":
      case "IN_PROGRESS": return "step-build";
      case "VERIFYING": return "step-verify";
      case "PAYOUT_PENDING":
      case "PAYOUT_FAILED":
      case "PAID": return "step-payout";
      default: return "step-requirements";
    }
  })();

  return (
    <div className="space-y-6 animate-fade-up">
      {/* Executive Project Hub Header */}
      <div className="card card-pad bg-white rounded-3xl border border-sand-200 shadow-card">
        <div className="mb-3">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-sea-600 hover:text-sea-700 transition"
          >
            <span aria-hidden="true">&larr;</span> All projects
          </Link>
        </div>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-ink-900">
                {p.title}
              </h1>
              <Badge tone={state.tone}>{state.label}</Badge>
            </div>
            {p.location_label && (
              <p className="flex items-center gap-1.5 text-xs font-semibold text-ink-500">
                <MapPin className="w-3.5 h-3.5 text-sea-600 flex-shrink-0" />
                <span>{p.location_label}</span>
              </p>
            )}
          </div>
        </div>

        {p.summary && (
          <p className="mt-3.5 max-w-3xl text-sm text-ink-600 leading-relaxed">
            {p.summary}
          </p>
        )}

        {/* Milestone Stepper Ribbon */}
        <div className="mt-6 border-t border-sand-100 pt-5">
          <Stepper state={p.state} projectId={p.id} />
        </div>
      </div>

      {/* Current Phase & Next Action Banner */}
      <div className="rounded-2xl border border-sea-200/90 bg-gradient-to-r from-sea-50/80 via-white to-sand-50/60 p-5 shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-start sm:items-center gap-3.5">
          <img
            src={`/illustrations/${stepIllustration}.svg`}
            alt=""
            aria-hidden="true"
            className="w-11 h-11 flex-shrink-0 drop-shadow-xs"
          />
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="flex h-2 w-2 rounded-full bg-sea-600 animate-pulse" />
              <span className="text-xs font-bold uppercase tracking-wider text-sea-900">
                Current Phase &amp; Next Action
              </span>
            </div>
            <p className="text-sm font-medium text-sea-950 leading-relaxed" data-testid="what-next">
              {WHAT_NEXT[p.state] ?? ""}
            </p>
          </div>
        </div>

        {nextActionCta && (
          <Link
            href={nextActionCta.href}
            className="inline-flex items-center gap-2 rounded-xl bg-sea-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-sea-700 transition whitespace-nowrap self-stretch sm:self-auto justify-center"
          >
            <span>{nextActionCta.label}</span>
            <span aria-hidden="true">&rarr;</span>
          </Link>
        )}
      </div>

      {/* Transparency Navigation Bar */}
      <div className="rounded-2xl border border-sand-200 bg-white/90 px-4 py-3 text-xs sm:text-sm text-ink-600 shadow-2xs flex flex-wrap items-center gap-2">
        <span className="font-semibold text-ink-800">Transparency Records:</span>
        <Link href={`/ledger?id=${p.id}`} className="font-semibold text-sea-600 hover:text-sea-700 underline">
          Open the public ledger
        </Link>
        : every money and AI event, in order.
        {isMember && (
          <>
            <span className="text-sand-300">|</span>
            <Link href={`/ba?id=${p.id}`} className="font-semibold text-sea-600 hover:text-sea-700 underline">
              Open BA Studio
            </Link>
            : the requirements analysis.
            <span className="text-sand-300">|</span>
            <Link href={`/audit?id=${p.id}`} className="font-semibold text-sea-600 hover:text-sea-700 underline">
              Open the AI audit trail
            </Link>
            : every call to an AI helper.
          </>
        )}
      </div>

      {/* Main 2-Column Split Workspace */}
      <div className="grid gap-6 md:grid-cols-3">
        {/* Left Column: Campaign, Terms */}
        <div className="space-y-6 md:col-span-2">
          {/* Campaign Section */}
          <section aria-label="Campaign" className="card card-pad bg-white rounded-2xl border border-sand-200 shadow-card">
            <div className="flex items-center justify-between mb-4 border-b border-sand-100 pb-3">
              <div>
                <h2 className="font-bold text-ink-900">Campaign</h2>
                <p className="text-2xs text-ink-500">Pledge-If collective funding pool</p>
              </div>
              {c && (
                <span className="inline-flex items-center gap-1 rounded-full bg-sea-50 px-2.5 py-0.5 text-xs font-semibold text-sea-700 ring-1 ring-inset ring-sea-600/20">
                  Round {c.number}: <span className="font-bold">{campaignState(c.state).label}</span>
                </span>
              )}
            </div>

            {c ? (
              <div className="space-y-4">
                <p className="sr-only">Round {c.number}: {campaignState(c.state).label}</p>
                <div className="rounded-xl border border-sand-200 bg-sand-50/70 p-4">
                  <PledgeProgress
                    pledgedCents={c.pledged_cents}
                    goalCents={c.goal_cents}
                    count={c.pledge_count}
                    open={c.state === "OPEN"}
                  />
                </div>
                <div className="flex items-center gap-2 text-xs text-ink-500">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  <span>Pledge-If Guarantee: Holds are released immediately if the goal is missed. Nobody is charged.</span>
                </div>
              </div>
            ) : (
              <Empty title="No campaign yet">
                The campaign starts after the brief is approved and the builder has signed.
              </Empty>
            )}
          </section>

          {/* Terms Section */}
          <section aria-label="Terms" className="card card-pad bg-white rounded-2xl border border-sand-200 shadow-card text-sm">
            <div className="mb-4 border-b border-sand-100 pb-3">
              <h2 className="font-bold text-ink-900">Terms</h2>
              <p className="text-2xs text-ink-500">Agreed commercial contract terms and payout criteria</p>
            </div>

            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="rounded-xl border border-sand-200 bg-sand-50/70 p-3.5">
                <dt className="text-2xs font-bold uppercase tracking-wider text-ink-500">Budget</dt>
                <dd className="mt-1 text-lg font-bold text-ink-900">{formatMoney(p.budget_cents, p.currency)}</dd>
              </div>

              <div className="rounded-xl border border-sand-200 bg-sand-50/70 p-3.5">
                <dt className="text-2xs font-bold uppercase tracking-wider text-ink-500">Delivery time</dt>
                <dd className="mt-1 text-lg font-semibold text-ink-800">
                  {p.delivery_days ? `${p.delivery_days} days` : "not set"}
                </dd>
              </div>

              <div className="rounded-xl border border-sand-200 bg-sand-50/70 p-3.5 sm:col-span-2">
                <dt className="text-2xs font-bold uppercase tracking-wider text-ink-500">Payment to the builder</dt>
                <dd className="mt-1 text-sm font-medium text-ink-800">
                  {p.payout_release_policy === "HUMAN"
                    ? "Approved by a person"
                    : "Released automatically when the safety checks allow"}
                </dd>
              </div>
            </dl>
          </section>
        </div>

        {/* Right Column: Financial Vault & Stakeholder List */}
        <div className="space-y-6">
          {isMember ? (
            <MoneyBox projectId={p.id} currency={p.currency} />
          ) : (
            <section
              aria-label="Money"
              className="card card-pad bg-sand-50/60 rounded-2xl border border-dashed border-sand-300 p-5 text-sm text-ink-600 shadow-2xs"
            >
              <h2 className="mb-2 font-bold text-ink-800">Money</h2>
              {auth.status === "authed" ? (
                <p>Only the people on this project can see its money box.</p>
              ) : (
                <p>
                  <Link href="/login" className="font-semibold text-sea-600 underline">
                    Sign in
                  </Link>{" "}
                  as a member to see the money box.
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
    return (
      <Empty title="No project selected">
        Open a project from <Link href="/" className="text-sea-700 underline">the project list</Link>.
      </Empty>
    );
  }
  return <Workspace id={id} />;
}

export default function ProjectPage() {
  return (
    <Suspense fallback={<Loading what="Loading" />}>
      <FromQuery />
    </Suspense>
  );
}
