"use client";
import Link from "next/link";
import { WHAT_NEXT } from "@/lib/steps";
import { ArrowRight } from "lucide-react";

interface PhaseBannerProps {
  state: string;
  cta?: { label: string; href: string } | null;
  className?: string;
}

const STEP_ILLUSTRATION_MAP: Record<string, string> = {
  REQUIREMENTS: "step-requirements",
  BRD_REVIEW: "step-brief",
  CONTRACTING: "step-contract",
  CAMPAIGN_OPEN: "step-campaign",
  CAMPAIGN_EXPIRING: "step-campaign",
  GOAL_REACHED: "step-campaign",
  CAMPAIGN_FAILED: "step-campaign",
  BUILDING: "step-build",
  VERIFYING: "step-verify",
  NEEDS_CHANGES: "step-verify",
  PAYOUT_PENDING: "step-payout",
  PAYOUT_FAILED: "step-payout",
  PAID: "step-payout",
  CANCELLED: "step-ledger",
  COMPLETED: "step-ledger",
};

export function PhaseBanner({ state, cta, className = "" }: PhaseBannerProps) {
  const illustration = STEP_ILLUSTRATION_MAP[state] || "step-requirements";
  const whatNextText = WHAT_NEXT[state] ?? "";

  return (
    <div
      className={`relative overflow-hidden rounded-2xl border border-sea-200/80 bg-gradient-to-r from-sea-50/90 via-white to-sand-50/60 p-5 sm:p-6 shadow-card transition-all ${className}`}
    >
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-start sm:items-center gap-4">
          <img
            src={`/illustrations/${illustration}.svg`}
            alt=""
            aria-hidden="true"
            className="w-12 h-12 flex-shrink-0 drop-shadow-xs"
          />
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="flex h-2 w-2 rounded-full bg-sea-600 animate-pulse" />
              <span className="text-xs font-bold uppercase tracking-wider text-sea-900">
                Current Phase &amp; Next Action
              </span>
            </div>
            <p
              className="text-sm font-medium text-sea-950 leading-relaxed"
              data-testid="what-next"
            >
              {whatNextText}
            </p>
          </div>
        </div>

        {cta && (
          <Link
            href={cta.href}
            className="inline-flex items-center gap-2 rounded-xl bg-sea-600 px-4 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-sea-700 active:bg-sea-800 transition-colors whitespace-nowrap self-stretch sm:self-auto justify-center"
          >
            <span>{cta.label}</span>
            <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
          </Link>
        )}
      </div>
    </div>
  );
}
