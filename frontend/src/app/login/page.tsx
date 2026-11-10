"use client";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { DEMO_MODE, PERSONAS } from "@/lib/personas";

export default function LoginPage() {
  const { login, problem } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function go(e: string, n: string) {
    setBusy(true);
    setError(null);
    try {
      await login(e, n);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in");
      setBusy(false);
    }
  }

  function submit(ev: FormEvent) {
    ev.preventDefault();
    void go(email.trim(), name.trim());
  }

  return (
    <div className="mx-auto max-w-md pt-4">
      <div className="mb-6 text-center">
        <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-tr from-sea-700 via-sea-600 to-cyan-500 text-white font-extrabold text-2xl shadow-sm mb-3">
          B
        </div>
        <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">Sign in</h1>
        <p className="mt-1.5 text-sm text-slate-500">Access BriefPay community workspace & campaigns</p>
      </div>

      {problem && (
        <div role="alert" className="mb-4 rounded-xl border border-amber-200 bg-amber-50/80 p-3 text-xs font-medium text-amber-900 shadow-xs">
          {problem}
        </div>
      )}

      <form onSubmit={submit} className="space-y-4 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs">
        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
          <span>Email</span>
          <input
            type="email"
            required
            placeholder="you@community.org"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1.5 block w-full rounded-xl border border-slate-300 px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sea-500 focus:outline-none focus:ring-2 focus:ring-sea-500/20"
          />
        </label>
        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
          <span>Your name</span>
          <input
            type="text"
            required
            placeholder="Your full name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1.5 block w-full rounded-xl border border-slate-300 px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sea-500 focus:outline-none focus:ring-2 focus:ring-sea-500/20"
          />
        </label>
        {error && <p role="alert" className="text-xs font-medium text-red-600">{error}</p>}
        <button
          disabled={busy}
          className="w-full rounded-xl bg-gradient-to-r from-sea-600 to-sea-700 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:from-sea-700 hover:to-sea-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? "Signing in..." : "Sign in"}
        </button>
      </form>

      {DEMO_MODE && (
        <section className="mt-8">
          <div className="relative mb-4 flex items-center justify-center">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200" />
            </div>
            <span className="relative bg-slate-50 px-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Or select a member profile
            </span>
          </div>

          <ul className="space-y-2">
            {PERSONAS.map((p) => (
              <li key={p.key}>
                <button
                  disabled={busy}
                  onClick={() => void go(p.email, p.name)}
                  className="card-hover flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white p-3.5 text-left shadow-xs transition hover:border-slate-300 hover:bg-slate-50/50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-xs font-bold text-slate-700">
                      {p.name.charAt(0)}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-slate-900">{p.name}</div>
                      <div className="text-xs text-slate-500">{p.email}</div>
                    </div>
                  </div>
                  <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">
                    {p.role}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
