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
    } finally {
      setBusy(false);
    }
  }

  function submit(ev: FormEvent) {
    ev.preventDefault();
    void go(email.trim(), name.trim());
  }

  return (
    <div className="mx-auto max-w-md">
      <h1 className="mb-1 text-2xl font-bold">Sign in</h1>
      <p className="mb-4 text-sm text-gray-600">Demo sign-in: an email and a name, no password. This is for the hackathon sandbox only.</p>
      {problem && <p role="alert" className="mb-3 rounded border border-amber-200 bg-amber-50 p-2 text-sm text-amber-800">{problem}</p>}
      <form onSubmit={submit} className="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
        <label className="block text-sm">
          <span className="text-gray-700">Email</span>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 w-full rounded border border-gray-300 px-3 py-2" />
        </label>
        <label className="block text-sm">
          <span className="text-gray-700">Your name</span>
          <input type="text" required value={name} onChange={(e) => setName(e.target.value)} className="mt-1 w-full rounded border border-gray-300 px-3 py-2" />
        </label>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <button disabled={busy} className="w-full rounded bg-sea-600 py-2 text-white hover:bg-sea-700 disabled:opacity-60">{busy ? "Signing in..." : "Sign in"}</button>
      </form>
      {DEMO_MODE && (
        <section className="mt-6">
          <h2 className="mb-2 text-sm font-semibold text-gray-700">Or continue as a demo person</h2>
          <ul className="space-y-2">
            {PERSONAS.map((p) => (
              <li key={p.key}>
                <button disabled={busy} onClick={() => void go(p.email, p.name)} className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-left hover:bg-sea-50 disabled:opacity-60">
                  <span className="font-medium">{p.name}</span> <span className="text-sm text-gray-600">{p.role}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
