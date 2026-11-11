"use client";
import Link from "next/link";
import { STEPS, stepStatuses, WHAT_NEXT } from "@/lib/steps";
import { Badge } from "./ui";

export type StepName = "Requirements" | "Brief" | "Contract" | "Campaign" | "Build" | "Verify" | "Payout" | "Ledger";

export interface WorkflowNavProps {
  projectId: number;
  projectTitle?: string;
  projectState?: string;
  currentStep: StepName;
  nextAction?: {
    label: string;
    href: string;
    badge?: string;
    description?: string;
  } | null;
}

const STEP_LINKS: Record<StepName, (id: number) => string> = {
  Requirements: (id) => `/ba?id=${id}`,
  Brief: (id) => `/brd?id=${id}`,
  Contract: (id) => `/contract?id=${id}`,
  Campaign: (id) => `/project?id=${id}`,
  Build: (id) => `/submit?id=${id}`,
  Verify: (id) => `/verify?id=${id}`,
  Payout: (id) => `/plans?id=${id}`,
  Ledger: (id) => `/ledger?id=${id}`,
};

const STEP_SUBTITLES: Record<StepName, string> = {
  Requirements: "BA Studio",
  Brief: "BRD Spec",
  Contract: "Contract",
  Campaign: "Pledge-If",
  Build: "Delivery",
  Verify: "AI Verifier",
  Payout: "Guardian",
  Ledger: "Audit Ledger",
};

export function WorkflowNav({
  projectId,
  projectTitle,
  projectState,
  currentStep,
  nextAction,
}: WorkflowNavProps) {
  const state = projectState || "REQUIREMENTS";
  const statuses = stepStatuses(state);

  return (
    <div className="mb-6 rounded-2xl border border-slate-200/90 bg-white/95 p-4 sm:p-5 shadow-xs backdrop-blur-sm space-y-4">
      {/* Top Header Row */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <Link
            href={`/project?id=${projectId}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100 hover:text-slate-900 transition"
          >
            <span aria-hidden="true">&larr;</span>
            <span>Project Command Hub</span>
          </Link>
          <span className="text-slate-300">/</span>
          <span className="text-sm font-bold text-slate-900 truncate max-w-xs sm:max-w-md">
            {projectTitle || `Project #${projectId}`}
          </span>
          {projectState && (
            <Badge tone="teal">
              {projectState.replace(/_/g, " ")}
            </Badge>
          )}
        </div>

        {/* Optional Contextual Next-Action CTA */}
        {nextAction && (
          <Link
            href={nextAction.href}
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-sea-600 via-sea-700 to-teal-700 px-3.5 py-1.5 text-xs font-bold text-white shadow-sm hover:from-sea-700 hover:to-teal-800 transition hover:shadow hover:scale-[1.01]"
          >
            {nextAction.badge && (
              <span className="rounded bg-white/20 px-1.5 py-0.5 text-[10px] uppercase tracking-wider font-extrabold">
                {nextAction.badge}
              </span>
            )}
            <span>{nextAction.label}</span>
            <span aria-hidden="true">&rarr;</span>
          </Link>
        )}
      </div>

      {/* Progress Stepper Row */}
      <nav aria-label="Project lifecycle progress">
        <ol className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {STEPS.map((name, i) => {
            const stepName = name as StepName;
            const isCurrentPage = currentStep === stepName;
            const status = statuses[i];
            const isMilestoneDone = status === "done";
            const href = STEP_LINKS[stepName](projectId);

            let styleTone = "border-slate-200 bg-slate-50/70 text-slate-500 hover:border-slate-300 hover:bg-slate-100/80";
            if (isCurrentPage) {
              styleTone = "border-sea-600 bg-gradient-to-r from-sea-600 to-sea-700 text-white font-bold shadow-xs ring-2 ring-sea-500/25";
            } else if (isMilestoneDone) {
              styleTone = "border-emerald-200 bg-emerald-50/80 text-emerald-800 hover:bg-emerald-100 font-semibold";
            }

            return (
              <li key={name}>
                <Link
                  href={href}
                  className={`flex flex-col items-start justify-center rounded-xl border p-2 sm:p-2.5 transition text-left w-full h-full ${styleTone}`}
                >
                  <div className="flex items-center gap-1.5 text-xs">
                    <span className={`inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold ${
                      isCurrentPage
                        ? "bg-white/25 text-white"
                        : isMilestoneDone
                        ? "bg-emerald-600 text-white"
                        : "bg-slate-200 text-slate-600"
                    }`}>
                      {isMilestoneDone ? "✓" : i + 1}
                    </span>
                    <span className="truncate font-semibold">{name}</span>
                  </div>
                  <span className={`text-[10px] mt-0.5 truncate block w-full ${
                    isCurrentPage ? "text-sea-100" : isMilestoneDone ? "text-emerald-700" : "text-slate-400"
                  }`}>
                    {STEP_SUBTITLES[stepName]}
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      </nav>

      {/* Guidance footnote if nextAction description provided */}
      {nextAction?.description && (
        <div className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600 border border-slate-100">
          <p className="flex items-center gap-1.5">
            <span className="text-sea-600 font-bold">ℹ️ Next Action:</span>
            <span>{nextAction.description}</span>
          </p>
          <Link
            href={nextAction.href}
            className="font-bold text-sea-700 hover:text-sea-800 hover:underline shrink-0 ml-2"
          >
            {nextAction.label} &rarr;
          </Link>
        </div>
      )}
    </div>
  );
}
