"use client";
import { useEffect, useState } from "react";
import { GuardianPanel } from "@/components/GuardianPanel";
import { StepsGrid } from "@/components/StepsGrid";
import { Badge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { DEMO_MODE } from "@/lib/personas";
import { PLAN_REFRESH_MS, approval, decisionInfo, isLive, mayReview, planState, planWord, realReview, tampersFor } from "@/lib/plans";
import { formatDateTime } from "@/lib/time";
import type { PlanDetail, TamperResponse } from "@/lib/types";

const sentence = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

/** One money plan: its steps, the Guardian's verdict, and what the signed-in person may do about it. The server decides; this only explains. */
export function PlanDetailView({ plan, role, reload }: { plan: PlanDetail; role: string | null; reload: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [sim, setSim] = useState<TamperResponse | null>(null);

  useEffect(() => {                                 // an approved or running plan keeps asking for news while the tab is visible
    if (!isLive(plan.state)) return;
    const t = setInterval(() => document.visibilityState === "visible" && reload(), PLAN_REFRESH_MS);
    return () => clearInterval(t);
  }, [plan.state, reload]);

  async function act(name: string, path: string, body?: unknown, done?: (r: never) => void) {
    setBusy(name);
    setProblem(null);
    setMessage(null);
    try {
      const r = await api(path, { method: "POST", body });
      done?.(r as never);
      return true;
    } catch (e) {
      setProblem(sentence(e));
      return false;
    } finally {
      setBusy(null);
    }
  }

  const review = realReview(plan);
  const state = planState(plan.state);
  const d = decisionInfo(plan.decision);
  const can = approval(plan, review, role, note);
  const total = plan.steps.reduce((s, x) => s + x.amount_cents, 0);
  const tampers = DEMO_MODE && (role === "LEAD" || role === "SPONSOR") ? tampersFor(plan.kind) : [];

  return (
    <div className="space-y-4" data-testid="plan-detail">
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xl font-bold">{planWord(plan.kind)}</h2>
          <span className="flex items-center gap-2"><Badge tone={state.tone}>{state.label}</Badge><Badge tone={d.tone}>{d.label}</Badge></span>
        </div>
        <p className="text-sm text-gray-600">
          Plan {plan.id}{plan.reason ? ` · ${plan.reason.toLowerCase().replace(/_/g, " ")}` : ""} · {plan.steps.length} step{plan.steps.length === 1 ? "" : "s"} moving {formatMoney(total)} · proposed {formatDateTime(plan.created_at)}
        </p>
        <p className="mt-1 text-xs text-gray-500">Fingerprint <span className="font-mono" title={plan.plan_hash}>{plan.plan_hash.slice(0, 12)}</span>: approval is tied to exactly this plan, so it cannot be swapped afterwards.</p>
      </div>

      {problem && <p role="alert" className="rounded bg-red-50 p-2 text-sm text-red-800">{problem}</p>}
      {message && <p role="status" className="rounded bg-sea-50 p-2 text-sm text-sea-700">{message}</p>}

      <section aria-label="Steps" className="space-y-2">
        <h3 className="font-semibold">Steps</h3>
        <StepsGrid steps={plan.steps} />
      </section>

      {review ? <GuardianPanel review={review} title="Payment Guardian" /> : <p className="rounded-lg border border-dashed border-gray-300 p-4 text-sm text-gray-600">The Guardian has not checked this plan yet.</p>}

      <div className="flex flex-wrap items-center gap-3">
        {mayReview(role, plan.state) && (
          <button disabled={busy !== null} onClick={async () => { if (await act("review", `/plans/${plan.id}/review`)) reload(); }} className="rounded bg-sea-600 px-3 py-1.5 text-sm text-white hover:bg-sea-700 disabled:opacity-60">
            {busy === "review" ? "Checking..." : plan.state === "REVIEWED" ? "Check again" : "Run the Guardian check"}
          </button>
        )}
        {plan.state === "EXECUTING" && (
          <button disabled={busy !== null} onClick={async () => { if (await act("ask", `/projects/${plan.project_id}/money/refresh`, undefined, () => setMessage("Asked PayPal. The steps update as it answers."))) reload(); }} className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-60">
            {busy === "ask" ? "Asking..." : "Ask PayPal now"}
          </button>
        )}
      </div>

      {plan.state === "REVIEWED" && (
        <section aria-label="Approval" className="space-y-2 rounded-xl border border-gray-200 bg-white p-4">
          <h3 className="font-semibold">Approval</h3>
          {can.needsNote && (
            <>
              <p className="text-sm text-amber-800">The Guardian says HOLD: a person must look first. Write why it is safe to go ahead; it is kept with the approval.</p>
              {plan.earliest_honor_until && <p className="text-sm text-amber-800" data-testid="honor">Earliest hold runs out: {formatDateTime(plan.earliest_honor_until)}.</p>}
              <textarea aria-label="Why it is safe to go ahead" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} rows={3} className="w-full rounded border border-gray-300 p-2 text-sm" />
            </>
          )}
          <button disabled={!can.ok || busy !== null} onClick={async () => {
            if (review && await act("approve", `/plans/${plan.id}/approve`, { plan_hash: plan.plan_hash, guardian_review_id: review.id, ack_note: note.trim() || undefined })) reload();
          }} className="rounded bg-green-700 px-3 py-1.5 text-sm text-white hover:bg-green-800 disabled:opacity-50">{busy === "approve" ? "Approving..." : "Approve and run"}</button>
          {!can.ok && <p className="text-sm text-gray-600" data-testid="why-not">{can.reason}</p>}
        </section>
      )}

      {plan.approvals.length > 0 && (
        <section aria-label="Approvals" className="text-sm">
          <h3 className="font-semibold">Approved by</h3>
          <ul className="list-disc pl-5 text-gray-700">
            {plan.approvals.map((a, i) => <li key={i}>{a.approver.startsWith("system:") ? "the system (the Guardian allowed it automatically)" : a.approver} · {formatDateTime(a.created_at)}{a.ack_note ? ` · "${a.ack_note}"` : ""}</li>)}
          </ul>
        </section>
      )}

      {tampers.length > 0 && (
        <section aria-label="Tamper test" className="space-y-2 rounded-xl border border-dashed border-blue-300 bg-blue-50 p-4">
          <h3 className="font-semibold text-blue-900">Try to cheat (demo only)</h3>
          <p className="text-sm text-blue-900">Make a tampered copy of this plan and see the Guardian refuse it. PayPal is never contacted.</p>
          <div className="flex flex-wrap gap-2">
            {tampers.map((t) => (
              <button key={t.key} disabled={busy !== null} onClick={() => void act("tamper", `/plans/${plan.id}/simulate-tamper`, { mutation: t.key }, (r: TamperResponse) => setSim(r))}
                      className="rounded border border-blue-300 bg-white px-3 py-1.5 text-sm text-blue-900 hover:bg-blue-100 disabled:opacity-60">{t.label}</button>
            ))}
          </div>
          {sim && <GuardianPanel review={sim.review} title={`Simulation: ${tampers.find((t) => t.key === sim.mutation)?.label ?? sim.mutation}`} />}
        </section>
      )}
    </div>
  );
}
