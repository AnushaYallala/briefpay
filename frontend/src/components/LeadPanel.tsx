"use client";
import Link from "next/link";
import { useState } from "react";
import { CalendarClock, CheckCircle2, Lock, Rocket, ShieldAlert, SlidersHorizontal } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { CLOSE_POLICY_WORDS, centsToDollars, deadlineProblem, deadlineToIso, dollarsToCents, isoToLocalInput, mayLaunch } from "@/lib/campaign";
import { formatMoney } from "@/lib/money";
import { DEMO_MODE } from "@/lib/personas";
import { formatDateTime, parseApiDate } from "@/lib/time";
import type { CampaignActionResult, CampaignView } from "@/lib/types";

const said = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

type ClockAction = { action: string; reason?: string; why?: string };

/** What the clock did on a demo tick, in plain words. */
function clockWords(actions: ClockAction[]): string {
  const a = actions.find((x) => x.action === "CAPTURE" || x.action === "RELEASE" || x.action === "SKIPPED" || x.action === "ERROR");
  if (!a) return "The clock looked at the campaign and had nothing to do yet.";
  if (a.action === "CAPTURE") return "The clock saw the goal was held and started collecting the money.";
  if (a.action === "RELEASE") return "The deadline had passed without the goal, so the clock started releasing every hold. Nobody is charged.";
  if (a.action === "SKIPPED") return "The clock found a money plan already waiting; a person decides from here.";
  return "The clock could not finish; look at the money plans.";
}

/** The lead's buttons for a campaign that has opened, and which of them make sense in each state. The server still decides. */
function controls(state: string) {
  const all = [
    { name: "close", label: "Close and collect now", enabled: state === "OPEN", hint: "Only when the holds already cover the goal." },
    { name: "cancel", label: "Cancel the campaign", enabled: state === "OPEN", hint: "Releases every hold. Nobody is charged." },
    { name: "round", label: "Start another round", enabled: state === "FAILED", hint: "After a round that missed its goal." },
    { name: "early", label: "Try the deadline early", enabled: state === "OPEN", hint: "Demo only: pretend the deadline is now." },
  ];
  return DEMO_MODE ? all : all.filter((c) => c.name !== "early");
}

/** What the lead can do: set the goal date and terms, open the campaign, then close and collect, cancel, start another round, or (demo) try the deadline early. The server decides; this explains. */
export function LeadPanel({ projectId, campaign, onChanged, onRound }: { projectId: number; campaign: CampaignView | null; onChanged: () => void; onRound?: (campaignId: number) => void }) {
  const setup = campaign === null || campaign.state === "SETUP";
  const [deadline, setDeadline] = useState(campaign ? isoToLocalInput(campaign.deadline_at, parseApiDate) : "");
  const [policy, setPolicy] = useState(campaign?.close_policy ?? "EARLY_ON_GOAL");
  const [minPledge, setMinPledge] = useState(campaign ? centsToDollars(campaign.min_pledge_cents) : "");
  const [share, setShare] = useState(campaign ? centsToDollars(campaign.suggested_share_cents) : "");
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [plan, setPlan] = useState<CampaignActionResult["plan"] | null>(null);
  const lead = campaign?.lead;

  /** Close, cancel, another round and the demo shortcut all go through here: busy while it runs, the server's reason if it refuses. */
  async function act(name: string, run: () => Promise<string | null>) {
    setBusy(name);
    setProblem(null);
    setMessage(null);
    setPlan(null);
    setConfirming(false);
    try {
      const done = await run();
      if (done) setMessage(done);
      onChanged();
    } catch (e) { setProblem(said(e)); } finally { setBusy(null); }
  }
  const planned = (r: CampaignActionResult, words: string) => { setPlan(r.plan ?? null); return `${words}${r.plan ? ` The safety check said ${r.plan.decision}.` : ""}`; };
  const close = () => act("close", async () => planned(await api<CampaignActionResult>(`/campaigns/${campaign!.id}/close`, { method: "POST" }), "The goal is held, so the money is being collected."));
  const cancel = () => act("cancel", async () => planned(await api<CampaignActionResult>(`/campaigns/${campaign!.id}/cancel`, { method: "POST" }), "Every hold is being released. Nobody is charged."));
  const another = () => act("round", async () => {
    const next = await api<CampaignView>(`/campaigns/${campaign!.id}/relaunch`, { method: "POST" });
    onRound?.(next.id);
    return `Round ${next.number} is ready to set up.`;
  });
  const early = () => act("early", async () => {
    await api(`/demo/campaigns/${campaign!.id}/expire`, { method: "POST" });
    const t = await api<{ actions: ClockAction[] }>("/demo/clock/tick", { method: "POST" });
    return clockWords(t.actions);
  });

  async function save() {
    setProblem(null);
    setMessage(null);
    const iso = deadlineToIso(deadline);
    const win = lead ? deadlineProblem(deadline, lead.deadline_earliest, lead.deadline_latest, parseApiDate) : iso === null ? "Choose a date and time for the deadline." : null;
    if (win) { setProblem(win); return; }
    const mn = dollarsToCents(minPledge);
    const sh = dollarsToCents(share);
    if (mn === "bad" || sh === "bad") { setProblem("Amounts are in dollars, for example 5 or 12.50."); return; }
    setBusy("save");
    try {
      await api(`/projects/${projectId}/campaigns`, { method: "POST", body: { deadline_at: iso, close_policy: policy, min_pledge_cents: mn ?? undefined, suggested_share_cents: sh ?? undefined } });
      setMessage("Saved.");
      onChanged();
    } catch (e) { setProblem(said(e)); } finally { setBusy(null); }
  }
  async function launch() {
    if (campaign === null) return;
    setBusy("launch");
    setProblem(null);
    setMessage(null);
    try { await api(`/campaigns/${campaign.id}/launch`, { method: "POST" }); onChanged(); } catch (e) { setProblem(said(e)); } finally { setBusy(null); }
  }

  return (
    <section aria-label="Organiser" className="rounded-2xl border border-sea-200/90 bg-white shadow-card overflow-hidden">
      <div className="border-b border-sea-100 bg-gradient-to-r from-sea-50/90 via-emerald-50/40 to-white px-5 py-4 flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-sea-100 text-sea-700">
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-base font-bold text-slate-900">Campaign Terms &amp; Launch Controls</h2>
            <p className="text-xs text-slate-500 mt-0.5">Configure the funding deadline, minimum backing, and launch readiness</p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full border border-sea-200 bg-white px-2.5 py-0.5 text-[11px] font-semibold text-sea-700 shrink-0">
          Lead only
        </span>
      </div>

      <div className="p-5 sm:p-6 space-y-4">
        {problem && (
          <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm font-medium text-red-800">
            {problem}
          </p>
        )}
        {message && (
          <p role="status" className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-sm font-semibold text-emerald-800">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" aria-hidden="true" />
            <span>{message}</span>
          </p>
        )}

        {setup && (
          <form onSubmit={(e) => { e.preventDefault(); void save(); }} className="space-y-4 text-sm" aria-label="Campaign terms">
            <div className="flex items-start gap-2.5 rounded-xl border border-slate-200 bg-slate-50/80 p-3 text-xs sm:text-sm text-slate-700">
              <Lock className="h-4 w-4 text-slate-500 mt-0.5 shrink-0" aria-hidden="true" />
              <p>
                The goal is the price in the signed contract{campaign ? `: ${formatMoney(campaign.goal_cents, campaign.currency)}` : ""}. It cannot be changed here.
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="block">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                  <CalendarClock className="h-3.5 w-3.5 text-sea-600" aria-hidden="true" />
                  <span>Deadline (UTC)</span>
                </span>
                <input
                  type="datetime-local"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                  className="input mt-1.5"
                />
              </label>
              {lead && (
                <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600 border border-slate-100 leading-relaxed" data-testid="window">
                  It must be between <span className="font-semibold text-slate-800">{formatDateTime(lead.deadline_earliest)}</span> and{" "}
                  <span className="font-semibold text-slate-800">{formatDateTime(lead.deadline_latest)}</span>: PayPal only guarantees a hold for three days, so a pledge must still be safe when the campaign closes.
                </p>
              )}
            </div>

            <fieldset className="space-y-2">
              <legend className="text-xs font-bold uppercase tracking-wider text-slate-600">When it closes</legend>
              <div className="space-y-2 pt-1">
                {Object.entries(CLOSE_POLICY_WORDS).map(([key, words]) => {
                  const active = policy === key;
                  return (
                    <label
                      key={key}
                      className={`flex items-start gap-2.5 rounded-xl border p-3 cursor-pointer transition text-xs sm:text-sm ${
                        active
                          ? "border-sea-500 bg-sea-50/60 text-slate-900 ring-1 ring-sea-500/20"
                          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                      }`}
                    >
                      <input
                        type="radio"
                        name="policy"
                        checked={active}
                        onChange={() => setPolicy(key)}
                        className="mt-0.5 accent-sea-600"
                      />
                      <span className="leading-snug">{words}</span>
                    </label>
                  );
                })}
              </div>
            </fieldset>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <label className="block">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-600">Smallest pledge (dollars, optional)</span>
                <input
                  inputMode="decimal"
                  placeholder="e.g. 5.00"
                  value={minPledge}
                  onChange={(e) => setMinPledge(e.target.value)}
                  className="input mt-1.5 tabular-nums"
                />
              </label>
              <label className="block">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-600">Suggested share (dollars, optional)</span>
                <input
                  inputMode="decimal"
                  placeholder="e.g. 100.00"
                  value={share}
                  onChange={(e) => setShare(e.target.value)}
                  className="input mt-1.5 tabular-nums"
                />
              </label>
            </div>

            <div className="pt-1 flex flex-wrap items-center gap-3">
              <button type="submit" disabled={busy !== null} className="btn-primary">
                {busy === "save" ? "Saving..." : "Save the terms"}
              </button>
            </div>
          </form>
        )}

        {campaign?.state === "SETUP" && lead && (
          <div className="border-t border-slate-100 pt-4 space-y-3 text-sm" aria-label="Opening">
            {lead.launch_blockers.length > 0 && (
              <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-3.5" data-testid="blockers">
                <p className="font-semibold text-amber-900 flex items-center gap-1.5 text-xs uppercase tracking-wider">
                  <ShieldAlert className="h-4 w-4 text-amber-600 shrink-0" aria-hidden="true" />
                  <span>Before it can open:</span>
                </p>
                <ul className="mt-1.5 list-disc pl-5 text-amber-900 space-y-0.5 text-xs sm:text-sm">
                  {lead.launch_blockers.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-200/80 bg-emerald-50/50 p-3.5">
              <div className="text-xs text-slate-600">
                <p className="font-semibold text-slate-800">Ready to accept PayPal holds?</p>
                <p>Opening starts the 72-hour Pledge-If backing window.</p>
              </div>
              <button
                disabled={busy !== null || !mayLaunch(campaign)}
                onClick={() => void launch()}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-700 px-4 py-2.5 text-sm font-bold text-white shadow-sm hover:from-emerald-700 hover:to-teal-800 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Rocket className="h-4 w-4" aria-hidden="true" />
                <span>{busy === "launch" ? "Opening..." : "Open for pledges"}</span>
              </button>
            </div>
          </div>
        )}

        {campaign && lead?.earliest_honor_until && (
          <p className="rounded-xl border border-amber-200 bg-amber-50/80 px-3.5 py-2.5 text-xs sm:text-sm font-medium text-amber-900" data-testid="honor">
            The earliest hold runs out {formatDateTime(lead.earliest_honor_until)}.
          </p>
        )}

        {campaign && campaign.state !== "SETUP" && (
          <div className="border-t border-slate-100 pt-4 space-y-3 text-sm" aria-label="Controls">
            {plan && (
              <p className="rounded-xl border border-sea-200 bg-sea-50/70 px-3.5 py-2.5 text-xs text-sea-900" data-testid="plan-link">
                A money plan was prepared.{" "}
                <Link href={`/plans?id=${projectId}&plan=${plan.id}`} className="font-semibold underline">See the plan and the Guardian&apos;s checks</Link>
              </p>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {controls(campaign.state).map((c) => {
                const off = !c.enabled || busy !== null;
                return (
                  <button
                    key={c.label}
                    type="button"
                    disabled={off}
                    onClick={() => (c.name === "cancel" ? setConfirming(true) : void ({ close, round: another, early }[c.name as "close" | "round" | "early"]()))}
                    className={`rounded-xl border px-3 py-2 text-xs font-semibold text-left transition ${
                      off ? "border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed" : "border-sea-200 bg-white text-sea-800 hover:bg-sea-50"
                    }`}
                  >
                    {busy === c.name ? "Working..." : c.label}
                    <span className="block text-[11px] font-normal text-slate-500">{c.hint}</span>
                  </button>
                );
              })}
            </div>
            {confirming && (
              <div role="alertdialog" aria-label="Confirm cancel" className="rounded-xl border border-amber-200 bg-amber-50/80 p-3.5 space-y-2" data-testid="confirm-cancel">
                <p className="text-xs sm:text-sm text-amber-900">Cancel the campaign? Every hold is released and nobody is charged. This cannot be undone.</p>
                <div className="flex gap-2">
                  <button type="button" onClick={() => void cancel()} className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-700">Yes, cancel it</button>
                  <button type="button" onClick={() => setConfirming(false)} className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700">No, keep it open</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
