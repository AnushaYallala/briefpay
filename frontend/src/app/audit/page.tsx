"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { AuditGrid } from "@/components/AuditGrid";
import { RunDialog } from "@/components/RunDialog";
import { WorkflowNav } from "@/components/WorkflowNav";
import { Empty, ErrorBox, Loading } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { AUDIT_REFRESH_MS, agentLabel, agentsPresent, filterRuns, latencyText, summarize } from "@/lib/audit";
import type { AgentRun, AgentRunsResponse } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function Audit({ id }: { id: number }) {
  const auth = useAuth();
  const { data, error, loading, slow, reload } = useApi<AgentRunsResponse>(auth.status === "authed" ? `/projects/${id}/agent-runs` : null, auth.user?.id ?? null);
  const [agent, setAgent] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<AgentRun | null>(null);
  const close = useCallback(() => setOpen(null), []);

  useEffect(() => {                                   // live refresh while the page is visible
    const t = setInterval(() => document.visibilityState === "visible" && reload(), AUDIT_REFRESH_MS);
    return () => clearInterval(t);
  }, [reload]);

  const runs = useMemo(() => (data ? filterRuns(data.rows, agent) : []), [data, agent]);

  if (auth.status === "loading") return <Loading what="Checking who you are" />;
  if (auth.status !== "authed") return <Empty title="Sign in to see the AI audit trail">Only the people on a project can see it. <Link href="/login" className="text-sea-700 underline">Sign in</Link>.</Empty>;
  if (loading && !data) return <Loading what="Loading the AI audit trail" slow={slow} />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const sum = summarize(runs);
  return (
    <div className="space-y-5 animate-fade-up">
      <WorkflowNav projectId={id} />

      <div className="card-pad hero-mesh space-y-2">
        <Link href={`/project?id=${id}`} className="inline-flex items-center gap-1 text-xs font-semibold text-sea-700 hover:text-sea-800 hover:underline">
          <span aria-hidden="true">&larr;</span> Back to the project
        </Link>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">AI audit trail</h1>
        <p className="text-sm text-slate-600 max-w-3xl leading-relaxed">
          Every call to an AI helper on this project: which agent ran, which model and prompt version answered, how long it took, and what came back. The AI only suggests; fixed deterministic rules decide.
        </p>
      </div>
      {error && <p role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">Could not refresh just now ({error.message}). Showing the last calls we have.</p>}
      {data.rows.length === 0 ? <Empty title="No AI calls yet">Calls appear as the helpers work on the project.</Empty> : (
        <section className="card-pad space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {agentsPresent(data.rows).map((a) => (
                <button key={a} aria-pressed={agent === a} onClick={() => setAgent(agent === a ? null : a)}
                        className={`rounded-full border px-3 py-1 text-xs sm:text-sm font-medium transition ${agent === a ? "border-sea-600 bg-sea-600 text-white shadow-xs" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}>{agentLabel(a)}</button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input aria-label="Search the audit trail" placeholder="Search runs..." value={search} onChange={(e) => setSearch(e.target.value)} className="input w-48 sm:w-56 py-1.5" />
              <button onClick={reload} className="btn-secondary py-1.5 px-3 text-xs sm:text-sm">Refresh</button>
            </div>
          </div>
          <p className="text-sm font-medium text-slate-700" data-testid="audit-summary">
            {sum.runs} call{sum.runs === 1 ? "" : "s"} · {sum.failed} failed · average {latencyText(sum.avgLatencyMs)} · {sum.tokens} tokens
          </p>
          <AuditGrid runs={runs} quickFilter={search} onOpen={setOpen} />
        </section>
      )}
      {open && <RunDialog run={open} onClose={close} />}
    </div>
  );
}

function FromQuery() {
  const raw = useSearchParams().get("id");
  const id = raw !== null && /^\d{1,9}$/.test(raw) ? Number(raw) : null;
  if (id === null) return <Empty title="No project selected">Open the audit trail from a <Link href="/" className="text-sea-700 underline">project</Link>.</Empty>;
  return <Audit id={id} />;
}

export default function AuditPage() {
  return <Suspense fallback={<Loading what="Loading" />}><FromQuery /></Suspense>;
}
