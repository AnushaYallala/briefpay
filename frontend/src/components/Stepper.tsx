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
      case "Contract": return `/contract?id=${projectId}`;
      case "Campaign": return `/campaign?project=${projectId}`;
      case "Build": return `/submit?id=${projectId}`;
      case "Verify": return `/verify?id=${projectId}`;
      case "Payout": return `/plans?id=${projectId}`;
      case "Ledger": return `/ledger?id=${projectId}`;
      default: return `/project?id=${projectId}`;
    }
  };

  return (
    <nav aria-label="Project progress" className="w-full overflow-x-auto py-1">
      <ol className="flex flex-wrap items-center gap-1.5 sm:gap-2">
        {STEPS.map((name, i) => {
          const status = statuses[i];
          const tone =
            status === "current"
              ? "border-sea-600 bg-sea-600 text-white shadow-xs font-semibold ring-2 ring-sea-500/20"
              : status === "done"
              ? "border-emerald-200 bg-emerald-50 text-emerald-800 hover:border-emerald-300 font-medium"
              : off
              ? "border-gray-200 bg-gray-100 text-gray-400"
              : "border-sand-200 bg-white text-ink-500 hover:border-sand-300 font-medium";
          const href = hrefFor(name);
          const inner = (
            <>
              <span
                aria-hidden
                className={`inline-flex items-center justify-center w-4 h-4 rounded-full text-2xs ${
                  status === "current"
                    ? "bg-white/20 text-white"
                    : status === "done"
                    ? "bg-emerald-600 text-white"
                    : "text-current"
                }`}
              >
                {status === "done" ? "✓" : i + 1}
              </span>
              <span>{name}</span>
            </>
          );
          return (
            <li
              key={name}
              aria-current={status === "current" ? "step" : undefined}
              data-status={status}
              className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs sm:text-sm transition-all ${tone}`}
            >
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
