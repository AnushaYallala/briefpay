"use client";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { CLOSE_POLICY_WORDS, centsToDollars, deadlineProblem, deadlineToIso, dollarsToCents, isoToLocalInput, mayLaunch } from "@/lib/campaign";
import { formatMoney } from "@/lib/money";
import { formatDateTime, parseApiDate } from "@/lib/time";
import type { CampaignView } from "@/lib/types";

const said = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

/** What the lead can do: set the goal date and terms, open the campaign, and (not built yet) close, cancel or restart it. The server decides; this explains. */
export function LeadPanel({ projectId, campaign, onChanged }: { projectId: number; campaign: CampaignView | null; onChanged: () => void }) {
  const setup = campaign === null || campaign.state === "SETUP";
  const [deadline, setDeadline] = useState(campaign ? isoToLocalInput(campaign.deadline_at, parseApiDate) : "");
  const [policy, setPolicy] = useState(campaign?.close_policy ?? "EARLY_ON_GOAL");
  const [minPledge, setMinPledge] = useState(campaign ? centsToDollars(campaign.min_pledge_cents) : "");
  const [share, setShare] = useState(campaign ? centsToDollars(campaign.suggested_share_cents) : "");
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const lead = campaign?.lead;

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
    <section aria-label="Organiser" className="space-y-4 rounded-2xl border border-sea-200 bg-sea-50/50 p-5">
      <h2 className="font-bold text-slate-900">For the organiser</h2>
      {problem && <p role="alert" className="rounded bg-red-50 p-2 text-sm text-red-800">{problem}</p>}
      {message && <p role="status" className="rounded bg-white p-2 text-sm text-sea-700">{message}</p>}

      {setup && (
        <form onSubmit={(e) => { e.preventDefault(); void save(); }} className="space-y-3 text-sm" aria-label="Campaign terms">
          <p className="text-gray-700">
            The goal is the price in the signed contract{campaign ? `: ${formatMoney(campaign.goal_cents, campaign.currency)}` : ""}. It cannot be changed here.
          </p>
          <label className="block">
            <span className="font-medium">Deadline (UTC)</span>
            <input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} className="mt-1 block rounded border border-gray-300 p-2" />
          </label>
          {lead && <p className="text-xs text-gray-600" data-testid="window">It must be between {formatDateTime(lead.deadline_earliest)} and {formatDateTime(lead.deadline_latest)}: PayPal only guarantees a hold for three days, so a pledge must still be safe when the campaign closes.</p>}
          <fieldset>
            <legend className="font-medium">When it closes</legend>
            {Object.entries(CLOSE_POLICY_WORDS).map(([key, words]) => (
              <label key={key} className="mt-1 flex items-start gap-2"><input type="radio" name="policy" checked={policy === key} onChange={() => setPolicy(key)} /><span>{words}</span></label>
            ))}
          </fieldset>
          <label className="block"><span className="font-medium">Smallest pledge (dollars, optional)</span>
            <input inputMode="decimal" value={minPledge} onChange={(e) => setMinPledge(e.target.value)} className="mt-1 block w-32 rounded border border-gray-300 p-2" /></label>
          <label className="block"><span className="font-medium">Suggested share (dollars, optional)</span>
            <input inputMode="decimal" value={share} onChange={(e) => setShare(e.target.value)} className="mt-1 block w-32 rounded border border-gray-300 p-2" /></label>
          <button type="submit" disabled={busy !== null} className="rounded bg-sea-600 px-3 py-1.5 text-white hover:bg-sea-700 disabled:opacity-60">{busy === "save" ? "Saving..." : "Save the terms"}</button>
        </form>
      )}

      {campaign?.state === "SETUP" && lead && (
        <div className="space-y-2 text-sm" aria-label="Opening">
          {lead.launch_blockers.length > 0 && (
            <div data-testid="blockers"><p className="font-medium">Before it can open:</p><ul className="list-disc pl-5 text-amber-800">{lead.launch_blockers.map((b, i) => <li key={i}>{b}</li>)}</ul></div>
          )}
          <button disabled={busy !== null || !mayLaunch(campaign)} onClick={() => void launch()} className="rounded bg-green-700 px-3 py-1.5 text-white hover:bg-green-800 disabled:opacity-50">{busy === "launch" ? "Opening..." : "Open for pledges"}</button>
        </div>
      )}

      {campaign && lead?.earliest_honor_until && <p className="text-sm text-amber-800" data-testid="honor">The earliest hold runs out {formatDateTime(lead.earliest_honor_until)}.</p>}

      {campaign && campaign.state !== "SETUP" && (
        <div className="space-y-2 text-sm" aria-label="Controls">
          <p className="text-gray-700" data-testid="not-built">Closing and collecting, cancelling, starting another round and trying the deadline early are not built yet. They will appear here.</p>
          <div className="flex flex-wrap gap-2">
            {["Close and collect now", "Cancel the campaign", "Start another round", "Try the deadline early"].map((label) => (
              <button key={label} disabled className="rounded border border-gray-300 bg-white px-3 py-1.5 text-gray-500 opacity-60">{label}</button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
