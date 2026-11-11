"use client";
/** The supporter's box: choose an amount, press PayPal's button, and a HOLD is placed on their PayPal account. Nothing is charged
 * unless the goal is reached. Every rule is decided by the server; this only explains and keeps the obvious mistakes from being sent. */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Lock } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { dollarsToCents } from "@/lib/campaign";
import { formatMoney } from "@/lib/money";
import { PAYPAL_CLIENT_ID, loadPayPal, type PayPalButtons } from "@/lib/paypal";
import type { CampaignView, PledgeResult } from "@/lib/types";

const said = (e: unknown) => (e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Something went wrong");

/** The amount typed, as cents, or the plain-words reason it cannot be pledged yet. */
export function amountProblem(text: string, minCents: number, needCents: number, currency: string): { cents: number | null; problem: string | null } {
  const c = dollarsToCents(text);
  if (c === null) return { cents: null, problem: null };                    // nothing typed yet: no complaint, no button
  if (c === "bad") return { cents: null, problem: "Amounts are in dollars, for example 25 or 12.50." };
  if (c < minCents) return { cents: null, problem: `The smallest pledge is ${formatMoney(minCents, currency)}.` };
  if (c > needCents) return { cents: null, problem: `Only ${formatMoney(needCents, currency)} is still needed.` };
  return { cents: c, problem: null };
}

type Props = {
  campaign: CampaignView;
  role: string | null;                // the viewer's role on this project, if any
  signedIn: boolean;
  userName: string | null;
  onPledged: () => void;
  clientId?: string;                  // PayPal sandbox client id; defaults to NEXT_PUBLIC_PAYPAL_CLIENT_ID
};

export function PledgeBox({ campaign, role, signedIn, userName, onPledged, clientId = PAYPAL_CLIENT_ID }: Props) {
  const [amount, setAmount] = useState(campaign.suggested_share_cents !== null ? (campaign.suggested_share_cents / 100).toFixed(2) : "");
  const [name, setName] = useState(userName ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [done, setDone] = useState<PledgeResult | null>(null);
  const [sdkError, setSdkError] = useState<string | null>(null);
  const target = useRef<HTMLDivElement>(null);
  const live = useRef({ cents: 0, name: "" });
  const check = amountProblem(amount, campaign.min_pledge_cents, campaign.remaining_need_cents, campaign.currency);
  live.current = { cents: check.cents ?? 0, name: name.trim() };
  const canPledge = check.cents !== null && done === null;
  const { id, currency } = campaign;

  useEffect(() => {                                     // PayPal's button appears only while the amount is acceptable
    if (!canPledge || !clientId || !target.current) return;
    let closed = false;
    let button: PayPalButtons | null = null;
    const el = target.current;
    loadPayPal(clientId, currency).then((paypal) => {
      if (closed) return;
      button = paypal.Buttons({
        style: { layout: "vertical", shape: "rect", label: "pay" },
        createOrder: async () => {
          setProblem(null);
          setNote(null);
          try {
            const o = await api<PledgeResult>(`/campaigns/${id}/pledges/order`, { method: "POST", body: { amount_cents: live.current.cents, display_name: live.current.name || undefined } });
            return o.order_id;
          } catch (e) { setProblem(said(e)); throw e; }
        },
        onApprove: async (data) => {
          try {
            const p = await api<PledgeResult>(`/campaigns/${id}/pledges/authorize`, { method: "POST", body: { order_id: data.orderID } });
            setDone(p);
            onPledged();
          } catch (e) { setProblem(said(e)); onPledged(); }
        },
        onCancel: () => setNote("You closed PayPal. Nothing was held and nothing was charged."),
        onError: () => setProblem((p) => p ?? "PayPal could not finish. Nothing was charged. Please try again."),
      });
      return button.render(el);
    }).catch((e: unknown) => { if (!closed) setSdkError(said(e)); });
    return () => { closed = true; void button?.close().catch(() => undefined); };
  }, [canPledge, clientId, currency, id, onPledged]);

  if (campaign.state === "SETUP") return <p className="rounded-xl border border-dashed border-slate-300 bg-slate-50/70 p-3.5 text-sm text-slate-700" data-testid="pledge-unavailable">This campaign has not opened yet.</p>;
  if (!signedIn) {
    return (
      <p className="rounded-xl border border-dashed border-slate-300 bg-slate-50/70 p-3.5 text-sm text-slate-700 leading-relaxed" data-testid="pledge-unavailable">
        <Link href="/login" className="font-semibold text-sea-700 underline">Sign in</Link> to hold an amount for this project. Nothing is charged unless the goal is reached.
      </p>
    );
  }
  if (role === "FREELANCER") return <p className="rounded-xl border border-dashed border-slate-300 bg-slate-50/70 p-3.5 text-sm text-slate-700" data-testid="pledge-unavailable">The builder cannot fund their own job.</p>;
  if (!clientId) {
    return (
      <p className="rounded-xl border border-dashed border-slate-300 bg-slate-50/70 p-3.5 text-sm text-slate-700 leading-relaxed" data-testid="pledge-unavailable">
        PayPal is not set up on this site yet (there is no sandbox client id), so a hold cannot be placed here. Nothing is charged.
      </p>
    );
  }
  if (done) {
    return (
      <div role="status" className="flex items-start gap-2.5 rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-sm text-emerald-900" data-testid="pledge-done">
        <CheckCircle2 className="h-4 w-4 text-emerald-600 mt-0.5 shrink-0" aria-hidden="true" />
        <p>
          <strong>Thank you, {done.display_name}.</strong> {formatMoney(done.amount_cents, campaign.currency)} is held on your PayPal account.
          It is only a hold: you are charged only if the goal is reached before the deadline.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3 text-sm" data-testid="pledge-form">
      {problem && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 font-medium text-red-800">{problem}</p>}
      {note && <p role="status" className="rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-slate-700">{note}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
        <label className="block">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-600">Amount to hold (dollars)</span>
          <input inputMode="decimal" placeholder="e.g. 25.00" value={amount} onChange={(e) => setAmount(e.target.value)} className="input mt-1.5 tabular-nums" />
        </label>
        <label className="block">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-600">Name on the board</span>
          <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} className="input mt-1.5" />
        </label>
      </div>
      <p className="text-xs text-slate-500">Between {formatMoney(campaign.min_pledge_cents, campaign.currency)} and {formatMoney(campaign.remaining_need_cents, campaign.currency)}.</p>
      {check.problem && <p role="alert" className="text-xs font-medium text-amber-800" data-testid="amount-problem">{check.problem}</p>}
      {sdkError && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 font-medium text-red-800">{sdkError}</p>}
      {canPledge ? (
        <div className="space-y-2">
          <p className="flex items-center gap-1.5 text-xs text-slate-600"><Lock className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />PayPal asks for your approval. This only holds {formatMoney(live.current.cents, campaign.currency)}; it is not a payment.</p>
          <div ref={target} data-testid="paypal-button" />
        </div>
      ) : (
        <p className="text-xs text-slate-500" data-testid="pledge-hint">Enter an amount and the PayPal button appears.</p>
      )}
    </div>
  );
}
