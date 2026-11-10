"use client";
import Link from "next/link";
import { ProjectCardView } from "@/components/ProjectCard";
import { Empty, ErrorBox, Loading } from "@/components/ui";
import type { ProjectCard } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function Home() {
  const { data, error, loading, slow, reload } = useApi<{ projects: ProjectCard[] }>("/projects");
  return (
    <div className="space-y-8">
      {/* High-impact Fintech Hero */}
      <section className="relative rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-xs">
        <div className="max-w-3xl space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            <span>Pledge-If: Assurance Contracts on PayPal Authorization Rails</span>
          </div>

          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
            Pledge together. Pay only if we reach the goal.
          </h1>

          <p className="text-base sm:text-lg text-slate-600 leading-relaxed">
            Local businesses pool resources for shared projects with an all-or-nothing guarantee. Pledges are <strong>authorization holds</strong>, not charges: if the campaign falls short, every hold is released and nobody is charged. Delivered work is autonomously verified before payment.
          </p>

          <div className="grid grid-cols-2 gap-3 pt-2 sm:grid-cols-4">
            <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
              <div className="text-xs font-medium text-slate-500">Hold Guarantee</div>
              <div className="mt-0.5 text-sm font-bold text-slate-900">0% Charged on Miss</div>
            </div>
            <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
              <div className="text-xs font-medium text-slate-500">Requirements</div>
              <div className="mt-0.5 text-sm font-bold text-slate-900">AI BA Scored ≥90</div>
            </div>
            <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
              <div className="text-xs font-medium text-slate-500">Deliverables</div>
              <div className="mt-0.5 text-sm font-bold text-slate-900">Vision Verified</div>
            </div>
            <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
              <div className="text-xs font-medium text-slate-500">Safety Check</div>
              <div className="mt-0.5 text-sm font-bold text-slate-900">13 Guardian Rules</div>
            </div>
          </div>
        </div>
      </section>

      {/* Projects List */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-slate-900">Community Projects</h2>
            <p className="text-xs text-slate-500">Browse shared initiatives and monitor live funding progress</p>
          </div>
        </div>

        {loading && <Loading what="Loading projects" slow={slow} />}
        {error && <ErrorBox error={error} onRetry={reload} />}
        {!loading && !error && data && data.projects.length === 0 && (
          <Empty title="No projects yet">No active projects found. Check back shortly or start a new community initiative.</Empty>
        )}
        {!loading && !error && data && data.projects.length > 0 && (
          <ul className="grid gap-5 sm:grid-cols-2">
            {data.projects.map((p) => (
              <ProjectCardView key={p.id} p={p} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
