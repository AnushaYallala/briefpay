import Link from "next/link";
import { Badge, PledgeProgress } from "@/components/ui";
import { formatMoney } from "@/lib/money";
import { campaignState, projectState } from "@/lib/states";
import type { ProjectCard } from "@/lib/types";
import { MapPin, ArrowRight, ShieldCheck } from "lucide-react";

export function ProjectCardView({ p }: { p: ProjectCard }) {
  const s = projectState(p.state);
  const c = p.campaign;

  // Color accent based on tone
  const accentBorder: Record<string, string> = {
    green: "border-t-emerald-500",
    teal: "border-t-sea-500",
    blue: "border-t-blue-500",
    amber: "border-t-amber-500",
    red: "border-t-coral-500",
    grey: "border-t-sand-300",
  };

  return (
    <li
      className={`card card-hover flex flex-col justify-between rounded-2xl border border-sand-200 bg-white p-5 sm:p-6 shadow-card transition-all duration-200 border-t-4 ${
        accentBorder[s.tone] ?? "border-t-sea-500"
      }`}
    >
      <div>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-bold tracking-tight text-ink-900 group">
              <Link
                href={`/project?id=${p.id}`}
                className="hover:text-sea-600 transition-colors"
              >
                {p.title}
              </Link>
            </h2>
            {p.location_label && (
              <p className="mt-1 flex items-center gap-1.5 text-xs font-medium text-ink-500">
                <MapPin className="w-3.5 h-3.5 text-sea-500 flex-shrink-0" />
                <span>{p.location_label}</span>
              </p>
            )}
          </div>
          <Badge tone={s.tone}>{s.label}</Badge>
        </div>

        {p.summary && (
          <p className="mt-3 text-sm text-ink-600 line-clamp-2 leading-relaxed">
            {p.summary}
          </p>
        )}
      </div>

      <div className="mt-5 pt-4 border-t border-sand-100">
        <p className="flex items-center justify-between text-xs text-ink-600 mb-3">
          <span className="font-semibold text-ink-700">
            Budget {formatMoney(p.budget_cents, p.currency)}
          </span>
          <span className="text-2xs text-ink-400 font-medium">Assurance Pool</span>
        </p>

        {c && (
          <div className="space-y-2 rounded-xl bg-sand-50/70 border border-sand-100/80 p-3.5 mb-3">
            <div className="flex items-center justify-between text-2xs font-bold uppercase tracking-wider text-ink-500">
              <span>Campaign Round {c.number}</span>
              <span className="text-sea-700 font-semibold">{campaignState(c.state).label}</span>
            </div>
            <PledgeProgress
              pledgedCents={c.pledged_cents}
              goalCents={c.goal_cents}
              count={c.pledge_count}
              open={c.state === "OPEN"}
            />
          </div>
        )}

        <div className="pt-1 flex items-center justify-between">
          <span className="inline-flex items-center gap-1 text-2xs font-medium text-ink-400">
            <ShieldCheck className="w-3.5 h-3.5 text-sea-600" />
            <span>Pledge-If Protected</span>
          </span>
          <Link
            href={`/project?id=${p.id}`}
            className="inline-flex items-center gap-1 text-xs font-semibold text-sea-600 hover:text-sea-700 transition group"
          >
            <span>Open Workspace</span>
            <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>
      </div>
    </li>
  );
}
