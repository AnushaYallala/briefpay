import { STEPS, stepStatuses } from "@/lib/steps";

/** Requirements > Brief > Contract > Campaign > Build > Verify > Payout > Ledger, with the current step highlighted. */
export function Stepper({ state }: { state: string }) {
  const statuses = stepStatuses(state);
  const off = statuses.every((s) => s === "upcoming");
  return (
    <nav aria-label="Project progress">
      <ol className="flex flex-wrap gap-2">
        {STEPS.map((name, i) => {
          const status = statuses[i];
          const tone =
            status === "current" ? "border-sea-600 bg-sea-600 text-white"
            : status === "done" ? "border-green-300 bg-green-50 text-green-800"
            : off ? "border-gray-200 bg-gray-100 text-gray-400" : "border-gray-200 bg-white text-gray-500";
          return (
            <li key={name} aria-current={status === "current" ? "step" : undefined} data-status={status}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm ${tone}`}>
              <span aria-hidden>{status === "done" ? "✓" : i + 1}</span>
              <span>{name}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
