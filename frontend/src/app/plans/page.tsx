"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useState } from "react";
import { PlanDetailView } from "@/components/PlanDetailView";
import { WorkflowNav } from "@/components/WorkflowNav";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { decisionInfo, planState, planWord, roleOn } from "@/lib/plans";
import { formatDateTime } from "@/lib/time";
import type { PlanDetail, PlanListItem, PlansResponse, ProjectDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function Detail({ id, role, onChanged }: { id: number; role: string | null; onChanged: () => void }) {
  const { data, error, loading, slow, reload } = useApi<PlanDetail>(`/plans/${id}`);
  const again = useCallback(() => { reload(); onChanged(); }, [reload, onChanged]);
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading what="Loading the plan" slow={slow} />;
  return <>{error && <p role="alert" className="mb-2 rounded bg-amber-50 p-2 text-sm text-amber-800">Could not refresh just now ({error.message}). Showing the last news we have.</p>}<PlanDetailView plan={data} role={role} reload={again} />{loading && <span className="sr-only">Refreshing</span>}</>;
}

function Plans({ id, firstSelected }: { id: number; firstSelected: number | null }) {
  const auth = useAuth();
  const pr = useApi<ProjectDetail>(auth.status === "authed" ? `/projects/${id}` : null, auth.user?.id ?? null);
  const { data, error, loading, slow, reload } = useApi<PlansResponse>(auth.status === "authed" ? `/projects/${id}/plans` : null, auth.user?.id ?? null);
  const [selected, setSelected] = useState<number | null>(firstSelected);
  const [problem, setProblem] = useState<string | null>(null);
  const [building, setBuilding] = useState<string | null>(null);
  const role = roleOn(auth.memberships, id);

  if (auth.status === "loading") return <Loading what="Checking who you are" />;
  if (auth.status !== "authed") return <Empty title="Sign in to see the money plans">Only the people on a project can see them. <Link href="/login" className="text-sea-700 underline">Sign in</Link>.</Empty>;
  if (loading && !data) return <Loading what="Loading the money plans" slow={slow} />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;

  async function build(kind: string) {
    setBuilding(kind);
    setProblem(null);
    try {
      const made = await api<PlanDetail>(`/projects/${id}/plans`, { method: "POST", body: { kind } });
      reload();
      setSelected(made.id);
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setBuilding(null);
    }
  }

  const hasExecutedPlan = data.plans.some((p: PlanListItem) => p.state === "EXECUTED");

  return (
    <div className="space-y-4">
      <WorkflowNav
        projectId={id}
        projectTitle={pr.data?.title}
        projectState={pr.data?.state}
        currentStep="Payout"
        nextAction={hasExecutedPlan ? {
          label: "View Public Audit Ledger",
          href: `/ledger?id=${id}`,
          badge: "Payout Executed",
          description: "Payout executed! Inspect the immutable double-entry ledger.",
        } : null}
      />
      <div>
        <Link href={`/project?id=${id}`} className="text-sm text-sea-700 hover:underline">Back to the project</Link>
        <h1 className="mt-1 text-2xl font-bold">Money plans</h1>
        <p className="text-sm text-gray-600">Money never moves on its own. Every move is written down as a plan, checked by the Payment Guardian, and approved before anything runs.</p>
      </div>
      {error && <p role="alert" className="rounded bg-amber-50 p-2 text-sm text-amber-800">Could not refresh just now ({error.message}). Showing the last plans we have.</p>}
      {problem && <p role="alert" className="rounded bg-red-50 p-2 text-sm text-red-800">{problem}</p>}
      <div className="flex flex-wrap items-center gap-2">
        {(role === "LEAD" || role === "SPONSOR") && <button disabled={building !== null} onClick={() => void build("FREELANCER_PAYOUT")} className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-60">{building === "FREELANCER_PAYOUT" ? "Building..." : "Build a payout plan"}</button>}
        {role === "LEAD" && <button disabled={building !== null} onClick={() => void build("REFUND_CAPTURED")} className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-60">{building === "REFUND_CAPTURED" ? "Building..." : "Build a refund plan"}</button>}
        <button onClick={reload} className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50">Refresh</button>
      </div>
      {data.plans.length === 0 ? <Empty title="No money plans yet">Plans appear when a campaign closes or when a payout or refund is requested.</Empty> : (
        <div className="grid gap-5 md:grid-cols-3">
          <ul className="space-y-2 md:col-span-1" aria-label="Plans">
            {data.plans.map((p: PlanListItem) => {
              const s = planState(p.state);
              const d = decisionInfo(p.decision);
              return (
                <li key={p.id}>
                  <button aria-pressed={selected === p.id} onClick={() => setSelected(p.id)} className={`w-full rounded-lg border p-3 text-left text-sm ${selected === p.id ? "border-sea-600 bg-sea-50" : "border-gray-200 bg-white hover:bg-gray-50"}`}>
                    <span className="block font-medium">{planWord(p.kind)}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-1"><Badge tone={s.tone}>{s.label}</Badge><Badge tone={d.tone}>{d.label}</Badge></span>
                    <span className="mt-1 block text-xs text-gray-500">Plan {p.id} · {formatDateTime(p.created_at)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="md:col-span-2">
            {selected === null ? <Empty title="Pick a plan">Choose one on the left to see its steps and the Guardian's verdict.</Empty> : <Detail key={selected} id={selected} role={role} onChanged={reload} />}
          </div>
        </div>
      )}
    </div>
  );
}

function FromQuery() {
  const q = useSearchParams();
  const raw = q.get("id");
  const id = raw !== null && /^\d{1,9}$/.test(raw) ? Number(raw) : null;
  const planRaw = q.get("plan");
  const plan = planRaw !== null && /^\d{1,9}$/.test(planRaw) ? Number(planRaw) : null;
  if (id === null) return <Empty title="No project selected">Open the money plans from a <Link href="/" className="text-sea-700 underline">project</Link>.</Empty>;
  return <Plans id={id} firstSelected={plan} />;
}

export default function PlansPage() {
  return <Suspense fallback={<Loading what="Loading" />}><FromQuery /></Suspense>;
}
