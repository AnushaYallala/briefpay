import { Badge, PledgeProgress } from "@/components/ui";
import { formatMoney } from "@/lib/money";
import { campaignState, projectState } from "@/lib/states";
import type { ProjectCard } from "@/lib/types";

export function ProjectCardView({ p }: { p: ProjectCard }) {
  const s = projectState(p.state);
  const c = p.campaign;
  return (
    <li className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{p.title}</h2>
          {p.location_label && <p className="text-sm text-gray-500">{p.location_label}</p>}
        </div>
        <Badge tone={s.tone}>{s.label}</Badge>
      </div>
      {p.summary && <p className="mt-2 text-sm text-gray-700">{p.summary}</p>}
      <p className="mt-2 text-sm text-gray-600">Budget {formatMoney(p.budget_cents, p.currency)}</p>
      {c && (
        <div className="mt-3">
          <p className="mb-1 text-xs uppercase tracking-wide text-gray-500">Round {c.number}: {campaignState(c.state).label}</p>
          <PledgeProgress pledgedCents={c.pledged_cents} goalCents={c.goal_cents} count={c.pledge_count} open={c.state === "OPEN"} />
        </div>
      )}
    </li>
  );
}
