"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { AuditGrid } from "@/components/AuditGrid";
import { RunDialog } from "@/components/RunDialog";
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
    <div className="space-y-4">
      <div>
        <Link href={`/project?id=${id}`} className="text-sm text-sea-700 hover:underline">Back to the project</Link>
        <h1 className="mt-1 text-2xl font-bold">AI audit trail</h1>
        <p className="text-sm text-gray-600">Every call to an AI helper on this project: which one, which model and prompt version, how long it took and what came back. The AI only suggests; fixed rules decide.</p>
      </div>
      {error && <p role="alert" className="rounded bg-amber-50 p-2 text-sm text-amber-800">Could not refresh just now ({error.message}). Showing the last calls we have.</p>}
      {data.rows.length === 0 ? <Empty title="No AI calls yet">Calls appear as the helpers work on the project.</Empty> : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {agentsPresent(data.rows).map((a) => (
              <button key={a} aria-pressed={agent === a} onClick={() => setAgent(agent === a ? null : a)}
                      className={`rounded-full border px-3 py-1 text-sm ${agent === a ? "border-sea-600 bg-sea-600 text-white" : "border-gray-300 bg-white text-gray-700"}`}>{agentLabel(a)}</button>
            ))}
            <input aria-label="Search the audit trail" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} className="rounded border border-gray-300 px-3 py-1.5 text-sm" />
            <button onClick={reload} className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50">Refresh</button>
          </div>
          <p className="text-sm text-gray-700" data-testid="audit-summary">
            {sum.runs} call{sum.runs === 1 ? "" : "s"} · {sum.failed} failed · average {latencyText(sum.avgLatencyMs)} · {sum.tokens} tokens
          </p>
          <AuditGrid runs={runs} quickFilter={search} onOpen={setOpen} />
        </>
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
