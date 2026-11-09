"use client";
import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { DEMO_MODE, PERSONAS } from "@/lib/personas";

/** Demo only: switch between the seeded Velugu Cove people with one click (sign in as them). */
export function PersonaSwitcher() {
  const { user, login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const current = PERSONAS.find((p) => p.email === user?.email)?.key ?? "";
  return (
    <label className="flex items-center gap-2 text-sm text-gray-700">
      <span>Demo person</span>
      <select
        className="rounded border border-gray-300 bg-white px-2 py-1"
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
        <option value="" disabled>Choose...</option>
        {PERSONAS.map((p) => (
          <option key={p.key} value={p.key}>{p.name}: {p.role}</option>
        ))}
      </select>
      {error && <span role="alert" className="text-red-700">{error}</span>}
    </label>
  );
}

export function Header() {
  const { status, user, logout } = useAuth();
  return (
    <header className="border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <Link href="/" className="text-xl font-semibold text-sea-700">BriefPay</Link>
        <div className="flex flex-wrap items-center gap-4">
          {DEMO_MODE && status !== "loading" && <PersonaSwitcher />}
          {status === "authed" && user ? (
            <span className="flex items-center gap-3 text-sm">
              <span className="text-gray-700">{user.display_name}</span>
              <button onClick={logout} className="rounded border border-gray-300 px-2 py-1 hover:bg-gray-50">Sign out</button>
            </span>
          ) : (
            status === "anonymous" && <Link href="/login" className="rounded bg-sea-600 px-3 py-1.5 text-sm text-white hover:bg-sea-700">Sign in</Link>
          )}
        </div>
      </div>
    </header>
  );
}
