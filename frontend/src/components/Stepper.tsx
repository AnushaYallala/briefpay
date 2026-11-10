import Link from "next/link";
import { STEPS, stepStatuses } from "@/lib/steps";

/** Requirements > Brief > Contract > Campaign > Build > Verify > Payout > Ledger, with the current step highlighted. */
export function Stepper({ state, projectId }: { state: string; projectId?: number }) {
  const statuses = stepStatuses(state);
  const off = statuses.every((s) => s === "upcoming");

  const hrefFor = (name: string): string | null => {
    if (!projectId) return null;
    switch (name) {
      case "Requirements": return `/ba?id=${projectId}`;
      case "Brief": return `/brd?id=${projectId}`;
      case "Payout": return `/plans?id=${projectId}`;
      case "Ledger": return `/ledger?id=${projectId}`;
      default: return `/project?id=${projectId}`;
    }
  };

  return (
    <nav aria-label="Project progress">
      <ol className="flex flex-wrap gap-2">
        {STEPS.map((name, i) => {
          const status = statuses[i];
          const tone =
            status === "current" ? "border-sea-600 bg-sea-600 text-white shadow-xs"
            : status === "done" ? "border-emerald-200 bg-emerald-50 text-emerald-800 hover:border-emerald-300"
            : off ? "border-gray-200 bg-gray-100 text-gray-400" : "border-slate-200 bg-white text-slate-500 hover:border-slate-300";
          const href = hrefFor(name);
          const inner = (
            <>
              <span aria-hidden>{status === "done" ? "✓" : i + 1}</span>
              <span>{name}</span>
            </>
          );
          return (
            <li key={name} aria-current={status === "current" ? "step" : undefined} data-status={status}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs sm:text-sm font-medium transition ${tone}`}>
              {href && status !== "upcoming" ? (
                <Link href={href} className="inline-flex items-center gap-1.5 hover:underline">
                  {inner}
                </Link>
              ) : (
                inner
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
