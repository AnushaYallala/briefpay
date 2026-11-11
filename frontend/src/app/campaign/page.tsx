"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Check, Share2, ShieldCheck, Users, Wallet } from "lucide-react";
import { LeadPanel } from "@/components/LeadPanel";
import { PledgeBoard } from "@/components/PledgeBoard";
import { StrategistCard } from "@/components/StrategistCard";
import { WorkflowNav } from "@/components/WorkflowNav";
import { Badge, Empty, ErrorBox, Loading, PledgeProgress } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { CAMPAIGN_REFRESH_MS, CLOCK_MS, CLOSE_POLICY_WORDS, boardRows, countdownText, isLive, moneyNote } from "@/lib/campaign";
import { formatMoney } from "@/lib/money";
import { roleOn } from "@/lib/plans";
import { campaignState } from "@/lib/states";
import { formatDateTime, parseApiDate } from "@/lib/time";
import type { CampaignView, LedgerResponse, ProjectDetail, StrategistReport } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const num = (raw: string | null) => (raw !== null && /^\d{1,9}$/.test(raw) ? Number(raw) : null);

function projectStateFromCampaign(state: string): string {
  switch (state) {
    case "SETUP": return "CAMPAIGN_SETUP";
    case "OPEN":
    case "CAPTURING": return "PLEDGING";
    case "CAPTURED": return "IN_PROGRESS";
    case "FAILING":
    case "FAILED": return "CAMPAIGN_FAILED";
    case "CANCELLED": return "CANCELLED";
    default: return "PLEDGING";
  }
}

function Campaign({ idParam, projectParam }: { idParam: number | null; projectParam: number | null }) {
  const auth = useAuth();
  const ready = auth.status !== "loading";
  const key = auth.user?.id ?? null;
  const project = useApi<ProjectDetail>(ready && idParam === null && projectParam !== null ? `/projects/${projectParam}` : null, key);
  const cid = idParam ?? project.data?.campaign?.id ?? null;
  const view = useApi<CampaignView>(ready && cid !== null ? `/campaigns/${cid}` : null, key);
  const v = view.data;
  const pid = v?.project_id ?? projectParam;
  const ledger = useApi<LedgerResponse>(v && v.opens_at ? `/projects/${v.project_id}/ledger` : null, key);
  const role = pid === null ? null : roleOn(auth.memberships, pid);
  const lead = v?.lead !== undefined;
  const report = useApi<StrategistReport>(lead && v && isLive(v.state) ? `/campaigns/${v.id}/strategist` : null, key);
  const [now, setNow] = useState(() => Date.now());
  const [copied, setCopied] = useState(false);
  const { reload: reloadView } = view;
  const { reload: reloadLedger } = ledger;
  const { reload: reloadProject } = project;
  const open = v?.state === "OPEN";

  useEffect(() => {                                   // the clock redraws; an open campaign also asks for news
    if (!open) return;
    const tick = setInterval(() => setNow(Date.now()), CLOCK_MS);
    const news = setInterval(() => { if (document.visibilityState === "visible") { reloadView(); reloadLedger(); } }, CAMPAIGN_REFRESH_MS);
    return () => { clearInterval(tick); clearInterval(news); };
  }, [open, reloadView, reloadLedger]);

  const changed = useCallback(() => { reloadView(); reloadLedger(); reloadProject(); }, [reloadView, reloadLedger, reloadProject]);
  const board = useMemo(() => (v && ledger.data ? boardRows(ledger.data.rows, v.opens_at, parseApiDate) : []), [v, ledger.data]);

  if (!ready) return <Loading what="Checking who you are" />;
  if (idParam === null && projectParam === null) return <Empty title="No campaign selected">Open the campaign from a <Link href="/" className="text-sea-700 underline">project</Link>.</Empty>;
  if (project.loading && !project.data) return <Loading what="Loading the project" slow={project.slow} />;
  if (project.error && !project.data) return <ErrorBox error={project.error} onRetry={project.reload} />;
  if (cid !== null && view.loading && !v) return <Loading what="Loading the campaign" slow={view.slow} />;
  if (view.error && !v) return <ErrorBox error={view.error} onRetry={reloadView} />;

  if (v === null && cid === null) {
    const isLead = role === "LEAD" && project.data?.state === "CAMPAIGN_SETUP";
    return (
      <div className="space-y-6 animate-fade-up">
        <WorkflowNav
          projectId={projectParam!}
          projectTitle={project.data?.title}
          projectState={project.data?.state}
          currentStep="Campaign"
        />
        <div className="card-pad hero-mesh space-y-2">
          <Link href={`/project?id=${projectParam}`} className="inline-flex items-center gap-1 text-xs font-semibold text-sea-700 hover:underline">
            Back to the project
          </Link>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">Campaign</h1>
            <Badge tone="teal">Pledge-If Funding Setup</Badge>
          </div>
          <p className="text-sm text-slate-600 max-w-2xl">
            All-or-nothing funding using PayPal authorization holds. Nobody is charged unless the goal is met before the deadline.
          </p>
        </div>
        {isLead ? (
          <LeadPanel projectId={projectParam!} campaign={null} onChanged={changed} />
        ) : (
          <Empty title="No campaign yet">The campaign starts after the brief is approved and the builder has signed.</Empty>
        )}
      </div>
    );
  }
  if (!v) return null;

  const st = campaignState(v.state);
  const policy = CLOSE_POLICY_WORDS[v.close_policy] ?? v.close_policy;
  const inferredProjectState = projectStateFromCampaign(v.state);
  const pledgeReady = v.state === "OPEN" || v.state === "SETUP";

  return (
    <div className="space-y-6 animate-fade-up">
      <WorkflowNav
        projectId={v.project_id}
        projectTitle={v.project_title}
        projectState={inferredProjectState}
        currentStep="Campaign"
        nextAction={v.state === "CAPTURED" ? {
          label: "Proceed to Delivery",
          href: `/submit?id=${v.project_id}`,
          badge: "Funded",
          description: "The funding goal was met and collected. The builder can now submit project deliverables.",
        } : null}
      />

      {/* Executive Campaign Header Card */}
      <div className="card-pad hero-mesh space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Link href={`/project?id=${v.project_id}`} className="inline-flex items-center gap-1 text-xs font-semibold text-sea-700 hover:underline">
            Back to the project
          </Link>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-white/90 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-800">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />
            <span>Pledge-If Assurance · PayPal Holds</span>
          </span>
        </div>

        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900" data-testid="title">
              {v.project_title}
            </h1>
            <p className="text-sm text-slate-600 max-w-2xl">
              Collective funding round backed by PayPal authorization holds—funds are only captured if the full goal is met.
            </p>
          </div>
          <Badge tone={st.tone}>Round {v.number}: {st.label}</Badge>
        </div>
      </div>

      {view.error && (
        <p role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Could not refresh just now ({view.error.message}). Showing the last news we have.
        </p>
      )}

      {/* Main Split Workspace */}
      <div className="grid gap-6 lg:grid-cols-12 items-start">
        <div className={lead ? "lg:col-span-7 space-y-6" : "lg:col-span-12 space-y-6"}>
          {/* Funding Progress & KPI Tiles */}
          <section aria-label="Progress" className="card-pad space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Wallet className="h-4 w-4 text-sea-600" aria-hidden="true" />
                <h2 className="section-title">Funding Pool &amp; Terms</h2>
              </div>
              {open && (
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span>Accepting Holds</span>
                </span>
              )}
            </div>

            <PledgeProgress pledgedCents={v.pledged_cents} goalCents={v.goal_cents} count={v.pledge_count} open={false} />

            <div className="rounded-xl border border-sea-200/80 bg-sea-50/70 p-3.5 text-sm text-sea-900 flex items-start gap-2.5">
              <ShieldCheck className="h-4 w-4 text-sea-700 mt-0.5 shrink-0" aria-hidden="true" />
              <p data-testid="money-note">
                <strong>{v.held_not_charged ? "Held, not charged. " : ""}</strong>
                {moneyNote(v.state)}
              </p>
            </div>

            {v.fail_reason && (
              <p className="rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-700" data-testid="fail-reason">
                Why: {v.fail_reason}
              </p>
            )}

            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
              <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3">
                <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Goal</dt>
                <dd className="mt-1 text-base font-bold text-slate-900 tabular-nums">{formatMoney(v.goal_cents, v.currency)}</dd>
              </div>
              {isLive(v.state) && (
                <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3">
                  <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Still needed</dt>
                  <dd className="mt-1 text-base font-bold text-sea-800 tabular-nums" data-testid="need">{formatMoney(v.remaining_need_cents, v.currency)}</dd>
                </div>
              )}
              <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3">
                <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Smallest pledge</dt>
                <dd className="mt-1 text-base font-semibold text-slate-800 tabular-nums">{formatMoney(v.min_pledge_cents, v.currency)}</dd>
              </div>
              {v.suggested_share_cents !== null && (
                <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3">
                  <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Suggested share</dt>
                  <dd className="mt-1 text-base font-semibold text-slate-800 tabular-nums">{formatMoney(v.suggested_share_cents, v.currency)}</dd>
                </div>
              )}
              <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3">
                <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Deadline</dt>
                <dd className="mt-1 text-sm font-semibold text-slate-800">{formatDateTime(v.deadline_at)}</dd>
              </div>
              {open && (
                <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3">
                  <dt className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Time left</dt>
                  <dd className="mt-1 text-sm font-bold text-sea-800" data-testid="countdown">{countdownText(v.deadline_at, now, parseApiDate)}</dd>
                </div>
              )}
              {v.goal_reached_at && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3">
                  <dt className="text-[11px] font-bold uppercase tracking-wider text-emerald-700">Goal reached</dt>
                  <dd className="mt-1 text-sm font-semibold text-emerald-900">{formatDateTime(v.goal_reached_at)}</dd>
                </div>
              )}
            </dl>

            <p className="rounded-xl bg-slate-50 px-3.5 py-2.5 text-xs text-slate-600 border border-slate-100">
              {policy}
            </p>
          </section>

          {/* Supporter Backing Card */}
          {pledgeReady && (
            <section aria-label="Pledge" className="card-pad space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <h2 className="section-title">Back This Project</h2>
                <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-600">
                  Zero charge until goal met
                </span>
              </div>
              <p className="rounded-xl border border-dashed border-slate-300 bg-slate-50/70 p-3.5 text-sm text-slate-700 leading-relaxed" data-testid="pledge-unavailable">
                {v.state === "OPEN"
                  ? "Pledging is not switched on yet. When it is, you will be able to hold an amount with PayPal here; nothing is charged unless the goal is reached."
                  : "This campaign has not opened yet."}
              </p>
              <div>
                <button
                  onClick={async () => {
                    try { await navigator.clipboard.writeText(window.location.href); setCopied(true); } catch { setCopied(false); }
                  }}
                  className="inline-flex items-center gap-2 rounded-xl border border-sea-200 bg-sea-50/80 px-4 py-2 text-xs sm:text-sm font-semibold text-sea-800 hover:bg-sea-100 transition"
                >
                  {copied ? <Check className="h-4 w-4 text-emerald-600" aria-hidden="true" /> : <Share2 className="h-4 w-4 text-sea-600" aria-hidden="true" />}
                  <span>{copied ? "Link copied" : "Copy the link to share"}</span>
                </button>
              </div>
            </section>
          )}

          {/* Pledge Board */}
          <section aria-label="Pledge board" className="card-pad space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4 text-sea-600" aria-hidden="true" />
                <div>
                  <h2 className="section-title">Supporter Backing &amp; Ledger</h2>
                  <p className="text-xs text-slate-500">Verified holds and captures from the public ledger</p>
                </div>
              </div>
            </div>
            {v.opens_at === null ? (
              <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-4 text-sm text-slate-600">
                Pledges will appear here once the campaign opens.
              </p>
            ) : ledger.loading && !ledger.data ? (
              <Loading what="Loading the pledges" />
            ) : (
              <>
                {ledger.error && (
                  <p role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                    Could not load the pledges just now ({ledger.error.message}).
                  </p>
                )}
                <PledgeBoard rows={board} currency={v.currency} />
                <p className="text-xs text-slate-500">
                  Built from the public ledger. A hold shows no amount until the money is collected.
                </p>
              </>
            )}
          </section>
        </div>

        {lead && (
          <div className="lg:col-span-5 space-y-6">
            <LeadPanel projectId={v.project_id} campaign={v} onChanged={changed} />
            {isLive(v.state) && (
              <StrategistCard campaignId={v.id} currency={v.currency} report={report.data} missing={report.error?.code === "NO_REPORT"} reload={report.reload} onApplied={changed} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function FromQuery() {
  const q = useSearchParams();
  return <Campaign idParam={num(q.get("id"))} projectParam={num(q.get("project"))} />;
}

export default function CampaignPage() {
  return <Suspense fallback={<Loading what="Loading" />}><FromQuery /></Suspense>;
}
