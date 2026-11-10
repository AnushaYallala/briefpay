import { Badge } from "@/components/ui";
import type { Member } from "@/lib/types";

const ROLE_WORDS: Record<Member["role"], string> = { LEAD: "Organiser", SPONSOR: "Sponsor", SUPPORTER: "Supporter", FREELANCER: "Builder" };

/** Who is involved. Names and businesses only: contact details and PayPal addresses are never shown on this screen. */
export function MembersPanel({ members, viewerId }: { members: Member[]; viewerId: number | null }) {
  return (
    <section aria-label="People" className="rounded-xl border border-gray-200 bg-white p-4">
      <h2 className="mb-3 font-semibold">People</h2>
      <ul className="space-y-2 text-sm">
        {members.map((m) => (
          <li key={m.id} className="flex items-start justify-between gap-2">
            <div>
              <p className="font-medium">{m.display_name}{m.id === viewerId && <span className="ml-1 text-xs text-gray-500">(you)</span>}</p>
              {m.business_name && <p className="text-xs text-gray-500">{m.business_name}</p>}
            </div>
            <Badge tone={m.role === "LEAD" ? "teal" : m.role === "FREELANCER" ? "blue" : "grey"}>{ROLE_WORDS[m.role]}</Badge>
          </li>
        ))}
      </ul>
    </section>
  );
}
