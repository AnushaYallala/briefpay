import { Badge } from "@/components/ui";
import type { Member } from "@/lib/types";

const ROLE_WORDS: Record<Member["role"], string> = { LEAD: "Organiser", SPONSOR: "Sponsor", SUPPORTER: "Supporter", FREELANCER: "Builder" };

/** Who is involved. Names and businesses only: contact details and PayPal addresses are never shown on this screen. */
export function MembersPanel({ members, viewerId }: { members: Member[]; viewerId: number | null }) {
  return (
    <section aria-label="People" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
      <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
        <h2 className="font-bold text-slate-900">People</h2>
        <span className="text-xs font-medium text-slate-500">{members.length} Stakeholders</span>
      </div>
      <ul className="space-y-3 text-sm">
        {members.map((m) => (
          <li key={m.id} className="flex items-start justify-between gap-2">
            <div className="flex items-start gap-2.5">
              <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-xs font-bold text-slate-700">
                {m.display_name.charAt(0)}
              </div>
              <div>
                <p className="font-semibold text-slate-900">
                  {m.display_name}
                  {m.id === viewerId && <span className="ml-1 text-xs font-normal text-slate-500">(you)</span>}
                </p>
                {m.business_name && <p className="text-xs text-slate-500">{m.business_name}</p>}
              </div>
            </div>
            <Badge tone={m.role === "LEAD" ? "teal" : m.role === "FREELANCER" ? "blue" : "grey"}>{ROLE_WORDS[m.role]}</Badge>
          </li>
        ))}
      </ul>
    </section>
  );
}
