"use client";
import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { DEMO_MODE, PERSONAS } from "@/lib/personas";
import { UserCheck } from "lucide-react";

/** Switch between stakeholders and participants (sign in with one click). */
export function PersonaSwitcher() {
  const { user, login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const current = PERSONAS.find((p) => p.email === user?.email)?.key ?? "";

  return (
    <label className="flex items-center gap-2 text-xs font-medium text-ink-600">
      <span className="sr-only">Switch demo person</span>
      <span aria-hidden="true" className="hidden md:inline text-ink-500 font-medium">
        Stakeholder:
      </span>
      <div className="relative inline-flex items-center">
        <select
          className="rounded-xl border border-sand-200 bg-sand-50/70 hover:bg-white px-3 py-1.5 text-xs font-semibold text-ink-800 shadow-2xs transition-colors hover:border-sand-300 focus:border-sea-500 focus:outline-none focus:ring-2 focus:ring-sea-500/20 cursor-pointer"
          value={current}
          aria-label="Switch demo person"
          onChange={async (e) => {
            const p = PERSONAS.find((x) => x.key === e.target.value);
            if (!p) return;
            setError(null);
            try {
              await login(p.email, p.name);
            } catch (err) {
              setError(err instanceof Error ? err.message : "Could not switch");
            }
          }}
        >
          <option value="" disabled>Select Persona...</option>
          {PERSONAS.map((p) => (
            <option key={p.key} value={p.key}>
              {p.name} ({p.role})
            </option>
          ))}
        </select>
      </div>
      {error && <span role="alert" className="text-xs text-coral-600 font-normal">{error}</span>}
    </label>
  );
}

export function Header() {
  const { status, user, logout } = useAuth();

  return (
    <header className="sticky top-0 z-30 border-b border-sand-200/90 bg-white/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 sm:px-6 lg:px-8 py-3">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5 group">
            <img
              src="/illustrations/logo-mark.svg"
              alt="BriefPay"
              width={34}
              height={34}
              className="rounded-xl shadow-xs transition-transform duration-200 group-hover:scale-105"
            />
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold tracking-tight text-ink-900">
                Brief<span className="text-sea-600">Pay</span>
              </span>
              <span className="hidden sm:inline-flex items-center rounded-full bg-sea-50 border border-sea-200/60 px-2 py-0.5 text-2xs font-semibold text-sea-700">
                Pledge-If
              </span>
            </div>
          </Link>
        </div>

        <div className="flex flex-wrap items-center gap-3 sm:gap-4">
          {DEMO_MODE && status !== "loading" && <PersonaSwitcher />}

          {status === "authed" && user ? (
            <div className="flex items-center gap-3 pl-2 sm:border-l sm:border-sand-200">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-ink-800 text-xs font-bold text-white shadow-2xs ring-1 ring-white">
                  {user.display_name ? user.display_name.charAt(0).toUpperCase() : "U"}
                </div>
                <span className="text-sm font-semibold text-gray-700">{user.display_name}</span>
              </div>
              <button
                onClick={logout}
                className="rounded-lg border border-sand-200 bg-sand-50/80 px-2.5 py-1 text-xs font-medium text-ink-600 transition hover:bg-sand-100 hover:text-ink-900"
              >
                Sign out
              </button>
            </div>
          ) : (
            status === "anonymous" && (
              <Link
                href="/login"
                className="rounded-xl bg-sea-600 hover:bg-sea-700 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs transition-colors"
              >
                Sign in
              </Link>
            )
          )}
        </div>
      </div>
    </header>
  );
}
