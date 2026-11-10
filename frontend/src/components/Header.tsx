"use client";
import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { DEMO_MODE, PERSONAS } from "@/lib/personas";

/** Switch between stakeholders and participants (sign in with one click). */
export function PersonaSwitcher() {
  const { user, login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const current = PERSONAS.find((p) => p.email === user?.email)?.key ?? "";
  return (
    <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
      <span className="sr-only">Switch demo person</span>
      <span aria-hidden="true" className="hidden sm:inline text-slate-500 font-semibold">Stakeholder:</span>
      <div className="relative inline-block">
        <select
          className="rounded-lg border border-slate-300 bg-white/95 px-2.5 py-1.5 text-xs font-semibold text-slate-800 shadow-xs transition hover:border-slate-400 focus:border-sea-500 focus:outline-none focus:ring-2 focus:ring-sea-500/20"
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
            <option key={p.key} value={p.key}>{p.name} ({p.role})</option>
          ))}
        </select>
      </div>
      {error && <span role="alert" className="text-xs text-red-600 font-normal">{error}</span>}
    </label>
  );
}

export function Header() {
  const { status, user, logout } = useAuth();
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-sea-700 via-sea-600 to-cyan-500 text-white font-black text-lg shadow-sm transition group-hover:scale-105">
              B
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xl font-extrabold tracking-tight text-slate-900">
                Brief<span className="text-sea-600">Pay</span>
              </span>
              <span className="hidden sm:inline-flex items-center rounded-full bg-sea-50 px-2.5 py-0.5 text-[11px] font-semibold text-sea-700 ring-1 ring-inset ring-sea-600/20">
                Pledge-If
              </span>
            </div>
          </Link>
        </div>

        <div className="flex flex-wrap items-center gap-3 sm:gap-4">
          {DEMO_MODE && status !== "loading" && <PersonaSwitcher />}
          {status === "authed" && user ? (
            <div className="flex items-center gap-3 pl-2 sm:border-l sm:border-slate-200">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-slate-700 to-slate-900 text-xs font-bold text-white shadow-xs">
                  {user.display_name ? user.display_name.charAt(0).toUpperCase() : "U"}
                </div>
                <span className="text-sm font-semibold text-gray-700">{user.display_name}</span>
              </div>
              <button
                onClick={logout}
                className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
              >
                Sign out
              </button>
            </div>
          ) : (
            status === "anonymous" && (
              <Link
                href="/login"
                className="rounded-lg bg-gradient-to-r from-sea-600 to-sea-700 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:from-sea-700 hover:to-sea-800 hover:shadow"
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
