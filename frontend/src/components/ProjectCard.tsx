import Link from "next/link";
import { Badge, PledgeProgress } from "@/components/ui";
import { formatMoney } from "@/lib/money";
import { campaignState, projectState } from "@/lib/states";
import type { ProjectCard } from "@/lib/types";

export function ProjectCardView({ p }: { p: ProjectCard }) {
  const s = projectState(p.state);
  const c = p.campaign;
  return (
    <li className="card-hover flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-5 shadow-xs">
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold tracking-tight text-slate-900">
              <Link href={`/project?id=${p.id}`} className="hover:text-sea-600 transition">
                {p.title}
              </Link>
            </h2>
            {p.location_label && (
              <p className="mt-0.5 flex items-center gap-1 text-xs font-medium text-slate-500">
                <span>📍</span>
                <span>{p.location_label}</span>
              </p>
            )}
          </div>
          <Badge tone={s.tone}>{s.label}</Badge>
        </div>

        {p.summary && <p className="mt-3 text-sm text-slate-600 line-clamp-2 leading-relaxed">{p.summary}</p>}
      </div>

      <div className="mt-4 pt-4 border-t border-slate-100">
        <p className="flex items-center justify-between text-xs text-slate-600 mb-2">
          <span className="font-semibold text-slate-700">Budget {formatMoney(p.budget_cents, p.currency)}</span>
        </p>

        {c && (
          <div className="space-y-1.5 rounded-xl bg-slate-50/80 p-3">
            <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              <span>Campaign Round {c.number}</span>
              <span className="text-sea-700">{campaignState(c.state).label}</span>
            </div>
            <PledgeProgress pledgedCents={c.pledged_cents} goalCents={c.goal_cents} count={c.pledge_count} open={c.state === "OPEN"} />
          </div>
        )}

        <div className="mt-3 text-right">
          <Link
            href={`/project?id=${p.id}`}
            className="inline-flex items-center gap-1 text-xs font-semibold text-sea-700 hover:text-sea-800 transition"
          >
            <span>Open Workspace</span>
            <span aria-hidden="true">&rarr;</span>
          </Link>
        </div>
      </div>
    </li>
  );
}
