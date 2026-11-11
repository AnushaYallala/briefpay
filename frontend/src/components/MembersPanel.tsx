import { Badge } from "@/components/ui";
import type { Member } from "@/lib/types";
import { Users } from "lucide-react";

const ROLE_WORDS: Record<Member["role"], string> = {
  LEAD: "Organiser",
  SPONSOR: "Sponsor",
  SUPPORTER: "Supporter",
  FREELANCER: "Builder",
};

/** Who is involved. Names and businesses only: contact details and PayPal addresses are never shown on this screen. */
export function MembersPanel({ members, viewerId }: { members: Member[]; viewerId: number | null }) {
  return (
    <section aria-label="People" className="card card-pad bg-white rounded-2xl border border-sand-200 shadow-card">
      <div className="flex items-center justify-between mb-4 border-b border-sand-100 pb-3">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-sea-600" />
          <h2 className="font-bold text-ink-900">People</h2>
        </div>
        <span className="text-2xs font-medium text-ink-400 uppercase tracking-wider">
          {members.length} Stakeholders
        </span>
      </div>

      <ul className="space-y-3.5 text-sm">
        {members.map((m) => (
          <li key={m.id} className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-3 min-w-0">
              <div className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-sand-100 text-xs font-bold text-ink-700 ring-1 ring-sand-200">
                {m.display_name.charAt(0)}
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-ink-900 truncate">
                  {m.display_name}
                  {m.id === viewerId && (
                    <span className="ml-1.5 text-xs font-normal text-sea-700 font-medium">(you)</span>
                  )}
                </p>
                {m.business_name && (
                  <p className="text-2xs text-ink-500 truncate">{m.business_name}</p>
                )}
              </div>
            </div>
            <Badge tone={m.role === "LEAD" ? "teal" : m.role === "FREELANCER" ? "blue" : "grey"}>
              {ROLE_WORDS[m.role]}
            </Badge>
          </li>
        ))}
      </ul>
    </section>
  );
}
