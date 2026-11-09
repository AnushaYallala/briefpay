/** Small shared pieces: badges, the pledge progress bar, and the loading / error / empty states every screen must have. */
import type { ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { formatMoney, percentOf } from "@/lib/money";
import type { Tone } from "@/lib/states";

const TONES: Record<Tone, string> = {
  grey: "bg-gray-100 text-gray-700",
  blue: "bg-blue-100 text-blue-800",
  teal: "bg-sea-100 text-sea-700",
  amber: "bg-amber-100 text-amber-800",
  green: "bg-green-100 text-green-800",
  red: "bg-red-100 text-red-800",
};

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>{children}</span>;
}

/** "Pledged $X of $Y" with the honest line that a pledge is only a hold (SPEC 8.2). */
export function PledgeProgress({ pledgedCents, goalCents, count, open }: { pledgedCents: number; goalCents: number; count: number; open: boolean }) {
  const pct = percentOf(pledgedCents, goalCents);
  return (
    <div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <div className="h-full bg-sea-500" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1 text-sm text-gray-700">
        Pledged {formatMoney(pledgedCents)} of {formatMoney(goalCents)} by {count} {count === 1 ? "person" : "people"}
      </p>
      {open && <p className="text-xs text-gray-500">Nothing is charged unless the goal is reached: a pledge is only a hold.</p>}
    </div>
  );
}

export function Loading({ what = "Loading", slow = false }: { what?: string; slow?: boolean }) {
  return (
    <div role="status" className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-gray-600">
      <p>{what}...</p>
      {slow && (
        <p className="mt-2 text-sm text-amber-700">
          Waking up the server. The free host sleeps when nobody is using it and needs about a minute to wake up. Please wait.
        </p>
      )}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
      <p className="font-medium">{error.isNetwork ? "Could not reach the server" : "Something went wrong"}</p>
      <p className="mt-1 text-sm">{error.message}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-3 rounded bg-red-700 px-3 py-1.5 text-sm text-white hover:bg-red-800">
          Try again
        </button>
      )}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center">
      <p className="font-medium text-gray-800">{title}</p>
      {children && <div className="mt-1 text-sm text-gray-600">{children}</div>}
    </div>
  );
}
