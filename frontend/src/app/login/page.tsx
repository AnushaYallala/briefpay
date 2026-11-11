"use client";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { DEMO_MODE, PERSONAS } from "@/lib/personas";
import { ShieldCheck, ArrowRight, User } from "lucide-react";

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
    <div className="mx-auto max-w-xl py-6 sm:py-10 animate-fade-up">
      {/* Brand Header */}
      <div className="mb-8 text-center space-y-2">
        <div className="inline-flex items-center justify-center mb-2">
          <img
            src="/illustrations/logo-mark.svg"
            alt="BriefPay"
            width={48}
            height={48}
            className="rounded-2xl shadow-card"
          />
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-ink-900">
          Sign in
        </h1>
        <p className="text-sm text-ink-500 max-w-md mx-auto">
          Access BriefPay community workspace &amp; autonomous assurance campaigns
        </p>
      </div>

      {problem && (
        <div
          role="alert"
          className="mb-6 rounded-2xl border border-amber-200 bg-amber-50/90 p-4 text-xs sm:text-sm font-medium text-amber-900 shadow-xs"
        >
          {problem}
        </div>
      )}

      {/* Main Sign-In Card */}
      <div className="card card-pad bg-white rounded-2xl shadow-lift border border-sand-200">
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-ink-600 mb-1.5">
              <span>Email</span>
            </label>
            <input
              type="email"
              required
              aria-label="Email"
              placeholder="you@community.org"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input w-full"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-ink-600 mb-1.5">
              <span>Your name</span>
            </label>
            <input
              type="text"
              required
              aria-label="Your name"
              placeholder="Your full name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input w-full"
            />
          </div>

          {error && (
            <p role="alert" className="text-xs font-medium text-coral-600 bg-coral-50 border border-coral-200 rounded-xl p-2.5">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="btn btn-primary w-full py-2.5 text-sm font-semibold shadow-xs disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>

        {DEMO_MODE && (
          <div className="mt-8 pt-6 border-t border-sand-200">
            <div className="relative mb-4 flex items-center justify-center">
              <span className="bg-white px-3 text-2xs font-bold uppercase tracking-wider text-ink-400">
                Or select a demo persona (one-click)
              </span>
            </div>

            <div className="grid gap-2.5 sm:grid-cols-2">
              {PERSONAS.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  disabled={busy}
                  onClick={() => void go(p.email, p.name)}
                  className="card-hover flex items-center justify-between rounded-xl border border-sand-200 bg-sand-50/60 p-3 text-left transition hover:border-sand-300 hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-sand-200 text-ink-800 text-xs font-bold ring-1 ring-white">
                      {p.name.charAt(0)}
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-ink-900 truncate">{p.name}</div>
                      <div className="text-2xs text-ink-500 truncate">{p.role}</div>
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-ink-400 flex-shrink-0 ml-1" />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-6 text-center text-2xs text-ink-400">
        <span>No real credentials needed • Sandbox environment • Zero real money</span>
      </div>
    </div>
  );
}
