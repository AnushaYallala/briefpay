"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { LeadPanel } from "@/components/LeadPanel";
import { PledgeBoard } from "@/components/PledgeBoard";
import { StrategistCard } from "@/components/StrategistCard";
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
      <div className="space-y-4">
        <Link href={`/project?id=${projectParam}`} className="text-sm text-sea-700 hover:underline">Back to the project</Link>
        <h1 className="text-2xl font-bold">Campaign</h1>
        {isLead ? <LeadPanel projectId={projectParam!} campaign={null} onChanged={changed} /> : <Empty title="No campaign yet">The campaign starts after the brief is approved and the builder has signed.</Empty>}
      </div>
    );
  }
  if (!v) return null;

  const st = campaignState(v.state);
  const policy = CLOSE_POLICY_WORDS[v.close_policy] ?? v.close_policy;
  return (
    <div className="space-y-5">
      <div>
        <Link href={`/project?id=${v.project_id}`} className="text-sm text-sea-700 hover:underline">Back to the project</Link>
        <div className="mt-1 flex flex-wrap items-start justify-between gap-2">
          <h1 className="text-2xl font-bold" data-testid="title">{v.project_title}</h1>
          <Badge tone={st.tone}>Round {v.number}: {st.label}</Badge>
        </div>
      </div>
      {view.error && <p role="alert" className="rounded bg-amber-50 p-2 text-sm text-amber-800">Could not refresh just now ({view.error.message}). Showing the last news we have.</p>}

      <section aria-label="Progress" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
        <PledgeProgress pledgedCents={v.pledged_cents} goalCents={v.goal_cents} count={v.pledge_count} open={false} />
        <p className="rounded bg-sea-50 p-2 text-sm text-sea-700" data-testid="money-note"><strong>{v.held_not_charged ? "Held, not charged. " : ""}</strong>{moneyNote(v.state)}</p>
        {v.fail_reason && <p className="text-sm text-gray-600" data-testid="fail-reason">Why: {v.fail_reason}</p>}
        <dl className="grid grid-cols-2 gap-y-1 text-sm">
          <dt className="text-gray-500">Goal</dt><dd>{formatMoney(v.goal_cents, v.currency)}</dd>
          {isLive(v.state) && <><dt className="text-gray-500">Still needed</dt><dd data-testid="need">{formatMoney(v.remaining_need_cents, v.currency)}</dd></>}
          <dt className="text-gray-500">Smallest pledge</dt><dd>{formatMoney(v.min_pledge_cents, v.currency)}</dd>
          {v.suggested_share_cents !== null && <><dt className="text-gray-500">Suggested share</dt><dd>{formatMoney(v.suggested_share_cents, v.currency)}</dd></>}
          <dt className="text-gray-500">Deadline</dt><dd>{formatDateTime(v.deadline_at)}</dd>
          {open && <><dt className="text-gray-500">Time left</dt><dd data-testid="countdown">{countdownText(v.deadline_at, now, parseApiDate)}</dd></>}
          {v.goal_reached_at && <><dt className="text-gray-500">Goal reached</dt><dd>{formatDateTime(v.goal_reached_at)}</dd></>}
        </dl>
        <p className="text-xs text-gray-500">{policy}</p>
      </section>

      {(v.state === "OPEN" || v.state === "SETUP") && (
        <section aria-label="Pledge" className="space-y-2 rounded-2xl border border-dashed border-gray-300 p-5">
          <h2 className="font-bold text-slate-900">Make a pledge</h2>
          <p className="text-sm text-gray-700" data-testid="pledge-unavailable">{v.state === "OPEN" ? "Pledging is not switched on yet. When it is, you will be able to hold an amount with PayPal here; nothing is charged unless the goal is reached." : "This campaign has not opened yet."}</p>
          <button onClick={async () => { try { await navigator.clipboard.writeText(window.location.href); setCopied(true); } catch { setCopied(false); } }} className="text-sm text-sea-700 underline">{copied ? "Link copied" : "Copy the link to share"}</button>
        </section>
      )}

      <section aria-label="Pledge board" className="space-y-2 rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="font-bold text-slate-900">Who has pledged</h2>
        {v.opens_at === null ? <p className="text-sm text-gray-600">Pledges will appear here once the campaign opens.</p> : ledger.loading && !ledger.data ? <Loading what="Loading the pledges" /> : (
          <>
            {ledger.error && <p role="alert" className="rounded bg-amber-50 p-2 text-sm text-amber-800">Could not load the pledges just now ({ledger.error.message}).</p>}
            <PledgeBoard rows={board} currency={v.currency} />
            <p className="text-xs text-gray-500">Built from the public ledger. A hold shows no amount until the money is collected.</p>
          </>
        )}
      </section>

      {lead && <LeadPanel projectId={v.project_id} campaign={v} onChanged={changed} />}
      {lead && isLive(v.state) && (
        <StrategistCard campaignId={v.id} currency={v.currency} report={report.data} missing={report.error?.code === "NO_REPORT"} reload={report.reload} onApplied={changed} />
      )}
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
