"use client";
/** Small shared pieces: badges, pledge progress bar, headers, tiles, and loading/error/empty states. */
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { formatMoney, percentOf } from "@/lib/money";
import type { Tone } from "@/lib/states";

export const TONES: Record<Tone, string> = {
  grey: "bg-gray-100 text-gray-700",
  blue: "bg-blue-100 text-blue-800",
  teal: "bg-sea-100 text-sea-700",
  amber: "bg-amber-100 text-amber-800",
  green: "bg-green-100 text-green-800",
  red: "bg-red-100 text-red-800",
};

export function Badge({ tone, children, className = "" }: { tone: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONES[tone]} ${className}`}>
      {children}
    </span>
  );
}

/** Decorative illustration loader */
export function Illustration({
  name,
  size = 96,
  className = "",
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  return (
    <img
      src={`/illustrations/${name}.svg`}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      className={`inline-block select-none ${className}`}
    />
  );
}

/** PageHeader: breadcrumb + title + chip + actions slot */
export function PageHeader({
  back,
  title,
  subtitle,
  chip,
  actions,
}: {
  back?: { href: string; label: string };
  title: string;
  subtitle?: string;
  chip?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200/80 pb-4">
      <div className="space-y-1">
        {back && (
          <Link
            href={back.href}
            className="inline-flex items-center gap-1 text-xs font-semibold text-sea-700 hover:text-sea-800 transition"
          >
            <span aria-hidden="true">&larr;</span> {back.label}
          </Link>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">{title}</h1>
          {chip}
        </div>
        {subtitle && <p className="text-sm text-slate-600 leading-relaxed max-w-3xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5 shrink-0 pt-1 sm:pt-0">{actions}</div>}
    </div>
  );
}

/** StatTile: big number + label + hint */
export function StatTile({
  label,
  value,
  hint,
  tone = "slate",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "slate" | "green" | "amber" | "red" | "sea";
}) {
  const toneClasses = {
    slate: "border-slate-200/90 text-slate-900",
    green: "border-emerald-200 bg-emerald-50/50 text-emerald-950",
    amber: "border-amber-200 bg-amber-50/50 text-amber-950",
    red: "border-red-200 bg-red-50/50 text-red-950",
    sea: "border-sea-200 bg-sea-50/40 text-sea-950",
  }[tone];

  return (
    <div className={`card p-4 sm:p-5 transition hover:border-slate-300 ${toneClasses}`}>
      <span className="eyebrow block text-slate-500 font-bold">{label}</span>
      <div className="mt-1 text-2xl sm:text-3xl font-black tracking-tight tabular-nums">{value}</div>
      {hint && <p className="mt-1 text-xs text-slate-500 leading-snug">{hint}</p>}
    </div>
  );
}

/** SectionCard: card with titled header row and optional right-side action */
export function SectionCard({
  title,
  subtitle,
  action,
  children,
  className = "",
  ...aria
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <section className={`card-pad ${className}`} {...aria}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-3 mb-4">
        <div>
          <h2 className="section-title">{title}</h2>
          {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
        {action && <div>{action}</div>}
      </div>
      {children}
    </section>
  );
}

/** CopyHash: cryptographic hash pill with click-to-copy */
export function CopyHash({ hash, label }: { hash: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(hash);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
    }
  };

  return (
    <div className="inline-flex items-center gap-1.5 text-xs text-slate-600">
      {label && <span className="font-semibold text-slate-700">{label}:</span>}
      <code className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px] text-slate-800">
        {hash.length > 20 ? `${hash.slice(0, 10)}...${hash.slice(-8)}` : hash}
      </code>
      <button
        type="button"
        onClick={copy}
        title="Copy full hash to clipboard"
        className="rounded px-1.5 py-0.5 text-[11px] font-semibold text-sea-700 hover:bg-sea-50 hover:text-sea-800 transition"
      >
        {copied ? "Copied!" : "Copy"}
      </button>
    </div>
  );
}

/** "Pledged $X of $Y" with the honest line that a pledge is only a hold (SPEC 8.2). */
export function PledgeProgress({
  pledgedCents,
  goalCents,
  count,
  open,
}: {
  pledgedCents: number;
  goalCents: number;
  count: number;
  open: boolean;
}) {
  const pct = percentOf(pledgedCents, goalCents);
  return (
    <div className="space-y-1.5">
      <div
        className="h-3 w-full overflow-hidden rounded-full bg-slate-100 p-0.5 ring-1 ring-inset ring-slate-200/80"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div
          className="h-full rounded-full bg-sea-500 transition-all duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1 text-sm text-gray-700 font-medium">
        Pledged {formatMoney(pledgedCents)} of {formatMoney(goalCents)} by {count}{" "}
        {count === 1 ? "person" : "people"}
      </p>
      {open && (
        <p className="text-xs text-gray-500 flex items-center gap-1.5">
          <Illustration name="pledge-hold" size={16} className="inline-block" />
          <span>Nothing is charged unless the goal is reached: a pledge is only a hold.</span>
        </p>
      )}
    </div>
  );
}

export function Loading({ what = "Loading", slow = false }: { what?: string; slow?: boolean }) {
  return (
    <div
      role="status"
      className="card p-8 text-center text-gray-600 flex flex-col items-center justify-center space-y-3"
    >
      <div className="h-8 w-8 animate-spin rounded-full border-3 border-sea-600 border-t-transparent" />
      <p className="font-semibold text-slate-800 text-sm">{what}...</p>
      {slow && (
        <p className="mt-2 text-sm text-amber-700 max-w-md bg-amber-50 p-2.5 rounded-xl border border-amber-200">
          Waking up the server. The free host sleeps when nobody is using it and needs about a minute to wake up. Please wait.
        </p>
      )}
      <div className="w-48 h-1.5 rounded-full bg-slate-100 overflow-hidden">
        <div className="h-full bg-sea-400 animate-pulse w-3/4 rounded-full" />
      </div>
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div role="alert" className="card rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800 shadow-sm">
      <div className="flex items-start gap-3">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-red-200 text-red-800 text-xs font-black">
          !
        </span>
        <div className="space-y-1">
          <p className="font-bold text-red-900">
            {error.isNetwork ? "Could not reach the server" : "Something went wrong"}
          </p>
          <p className="text-xs text-red-700 leading-relaxed">{error.message}</p>
        </div>
      </div>
      {onRetry && (
        <div className="mt-3.5 pl-9">
          <button
            onClick={onRetry}
            className="rounded-xl bg-red-700 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-red-800 transition shadow-xs"
          >
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

export function Empty({
  title,
  children,
  illustration = "empty-generic",
}: {
  title: string;
  children?: ReactNode;
  illustration?: string;
}) {
  return (
    <div className="card p-8 sm:p-10 text-center flex flex-col items-center justify-center space-y-3">
      <Illustration name={illustration} size={80} className="mb-1 opacity-90" />
      <p className="font-bold text-slate-800 text-base">{title}</p>
      {children && <div className="text-sm text-gray-600 max-w-md leading-relaxed">{children}</div>}
    </div>
  );
}
