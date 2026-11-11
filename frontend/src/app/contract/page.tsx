"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Stepper } from "@/components/Stepper";
import { WorkflowNav } from "@/components/WorkflowNav";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { apiPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatMoney } from "@/lib/money";
import type { BRDResponse, ContractResponse, ProjectDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { memberName } from "@/lib/verifyview";

function ContractStudio({ projectId }: { projectId: number }) {
  const auth = useAuth();
  const { data: project, error: pErr, loading: pLoading, slow: pSlow, reload: reloadProject } =
    useApi<ProjectDetail>(auth.status === "loading" ? null : `/projects/${projectId}`, auth.user?.id ?? null);

  const { data: contract, error: cErr, loading: cLoading, reload: reloadContract } =
    useApi<ContractResponse>(auth.status === "loading" ? null : `/projects/${projectId}/contract`, auth.user?.id ?? null);

  const { data: brd } = useApi<BRDResponse>(`/projects/${projectId}/brd`);

  // Lead offer state
  const [amountDollars, setAmountDollars] = useState<string | null>(null);      // null = not typed yet: the form starts at the project's own budget
  const [deliveryDays, setDeliveryDays] = useState<number>(5);
  const [offering, setOffering] = useState<boolean>(false);
  const [offerError, setOfferError] = useState<string | null>(null);

  // Freelancer accept state - start empty or with authed user email (no fake default)
  const [paypalEmail, setPaypalEmail] = useState<string>(auth.user?.email || "");
  const [accepting, setAccepting] = useState<boolean>(false);
  const [acceptError, setAcceptError] = useState<string | null>(null);
  const [signedSuccess, setSignedSuccess] = useState<boolean>(false);

  if (auth.status === "loading" || pLoading || (cLoading && !contract)) {
    return <Loading what="Loading contract details" slow={pSlow} />;
  }
  if (pErr) return <ErrorBox error={pErr} onRetry={reloadProject} />;
  if (!project) return null;

  const isLead = project.viewer?.role === "LEAD";
  const isFreelancer = project.viewer?.role === "FREELANCER";
  const isSigned = contract?.status === "SIGNED" || Boolean(contract?.signed_at);
  const budgetDollars = String(project.budget_cents / 100);

  const handleOffer = async (e: React.FormEvent) => {
    e.preventDefault();
    setOffering(true);
    setOfferError(null);
    try {
      const cents = Math.round(parseFloat(amountDollars ?? budgetDollars) * 100);
      if (isNaN(cents) || cents <= 0) {
        throw new Error("Please enter a valid positive dollar amount.");
      }
      await apiPost(`/projects/${projectId}/contract/offer`, {
        amount_cents: cents,
        delivery_days: deliveryDays,
      });
      reloadContract();
      reloadProject();
    } catch (err: unknown) {
      setOfferError(err instanceof Error ? err.message : "Failed to offer contract");
    } finally {
      setOffering(false);
    }
  };

  const handleAccept = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!contract) return;
    setAccepting(true);
    setAcceptError(null);
    try {
      if (!paypalEmail || !paypalEmail.includes("@")) {
        throw new Error("Please enter a valid PayPal account email.");
      }
      await apiPost(`/projects/${projectId}/contract/accept`, {
        paypal_email: paypalEmail.trim(),
        brd_sha256: contract.brd_sha256,
        terms_sha256: contract.terms_sha256,
      });
      setSignedSuccess(true);
      reloadContract();
      reloadProject();
    } catch (err: unknown) {
      setAcceptError(err instanceof Error ? err.message : "Failed to sign contract");
    } finally {
      setAccepting(false);
    }
  };

  return (
    <div className="space-y-6">
      <WorkflowNav
        projectId={projectId}
        projectTitle={project.title}
        projectState={project.state}
        currentStep="Contract"
        nextAction={isSigned ? {
          label: "Proceed to Pledge Campaign",
          href: `/campaign?project=${projectId}`,
          badge: "Contract Signed",
          description: "Builder signed and PayPal locked! Open pledges from sponsors.",
        } : null}
      />

      {/* Prominent Forward Navigation Banner when Contract is Signed */}
      {isSigned && (
        <section aria-label="Contract signed" className="rounded-2xl border-2 border-emerald-500/80 bg-gradient-to-r from-emerald-50 via-teal-50 to-white p-5 sm:p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-600 text-xs font-bold text-white shadow-xs">✓</span>
                <h2 className="text-base sm:text-lg font-bold text-slate-900">
                  Conditional Agreement Signed by Freelancer!
                </h2>
              </div>
              <p className="text-xs sm:text-sm text-slate-600 max-w-2xl">
                {memberName(project.members, contract?.freelancer_member_id, "The builder")} accepted the delivery terms ({contract?.delivery_days} days, {formatMoney(contract?.amount_cents ?? 0, contract?.currency ?? "USD")}) and locked their PayPal payout address ({contract?.freelancer_paypal_email}). You can now proceed to the Pledge Campaign to collect pledge holds from sponsors.
              </p>
            </div>
            <Link
              href={`/campaign?project=${projectId}`}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-700 px-5 py-3 text-sm font-bold text-white shadow-md hover:from-emerald-700 hover:to-teal-800 transition hover:scale-[1.02] hover:shadow-lg"
            >
              <span>Proceed to Pledge Campaign</span>
              <span aria-hidden="true">&rarr;</span>
            </Link>
          </div>
        </section>
      )}

      {/* Header card with Stepper */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs">
        <div className="mb-2">
          <Link href={`/project?id=${projectId}`} className="inline-flex items-center gap-1 text-xs font-semibold text-sea-700 hover:text-sea-800 transition">
            <span aria-hidden="true">&larr;</span> Back to Project
          </Link>
        </div>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">Contract Agreement</h1>
            <p className="mt-1 text-xs text-slate-500 font-medium">
              Step 3 of 8 &bull; Conditional Freelancer Agreement bound by BRD Hash
            </p>
          </div>
          <div className="flex items-center gap-2">
            {isSigned ? (
              <Badge tone="green">Signed & Locked</Badge>
            ) : contract ? (
              <Badge tone="amber">Pending Signature</Badge>
            ) : (
              <Badge tone="grey">Drafting</Badge>
            )}
          </div>
        </div>

        <div className="mt-6 border-t border-slate-100 pt-5">
          <Stepper state={project.state} projectId={projectId} />
        </div>
      </div>

      {/* Notice Banner */}
      <div className="rounded-xl border border-blue-200 bg-blue-50/70 p-4 text-xs sm:text-sm text-blue-900 shadow-xs">
        <p className="font-semibold flex items-center gap-2">
          <span>⚖️</span>
          <span>Pledge-If Conditional Terms</span>
        </p>
        <p className="mt-1 text-blue-800 leading-relaxed">
          This contract is <strong>strictly conditional</strong>. It becomes effective only if the crowdfunding campaign reaches 100% of its goal within the 72-hour PayPal honor period. No funds are stored in traditional escrow: pledgers hold their authorizations until the goal is achieved.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Main Contract Terms column */}
        <div className="space-y-6 md:col-span-2">
          {contract ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-6">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">Terms of Engagement</h2>
                  <p className="text-xs text-slate-500">Contract ID #{contract.id} &bull; Version linked to BRD v{contract.brd_version}</p>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-black text-slate-900">{formatMoney(contract.amount_cents, contract.currency)}</div>
                  <div className="text-xs font-semibold text-slate-500">{contract.delivery_days} days delivery timeline</div>
                </div>
              </div>

              {/* Hashes and Verification Section */}
              <div className="rounded-xl bg-slate-50 p-4 border border-slate-200 text-xs space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <span className="font-semibold text-slate-700">BRD SHA-256 Hash:</span>
                  <span className="font-mono text-slate-900 bg-white px-2 py-0.5 rounded border border-slate-200 select-all">
                    {contract.brd_sha256}
                  </span>
                </div>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <span className="font-semibold text-slate-700">Terms SHA-256 Hash:</span>
                  <span className="font-mono text-slate-900 bg-white px-2 py-0.5 rounded border border-slate-200 select-all">
                    {contract.terms_sha256}
                  </span>
                </div>
              </div>

              {/* Rendered Terms Markdown */}
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Scope & Specifications</h3>
                <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 font-mono text-xs text-slate-800 whitespace-pre-wrap max-h-72 overflow-y-auto leading-relaxed">
                  {contract.terms_md}
                </div>
              </div>

              {/* Signed Status or Accept Form */}
              {isSigned ? (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-5 text-emerald-900 space-y-2">
                  <div className="flex items-center gap-2 font-bold text-base">
                    <span>✅</span> Contract Signed & Effective
                  </div>
                  <p className="text-xs sm:text-sm text-emerald-800">
                    Signed on {new Date(contract.signed_at!).toLocaleString()} by builder.
                  </p>
                  {contract.freelancer_paypal_email && (
                    <div className="pt-2 text-xs">
                      <span className="font-semibold">Locked PayPal Payout Address:</span>{" "}
                      <span className="font-mono font-bold bg-white/70 px-2 py-0.5 rounded">{contract.freelancer_paypal_email}</span>
                    </div>
                  )}
                  <div className="pt-3">
                    <Link
                      href={`/project?id=${projectId}`}
                      className="inline-flex items-center justify-center rounded-lg bg-emerald-700 px-4 py-2 text-xs sm:text-sm font-semibold text-white hover:bg-emerald-800 transition"
                    >
                      Proceed to Campaign &rarr;
                    </Link>
                  </div>
                </div>
              ) : isFreelancer ? (
                <form onSubmit={handleAccept} className="rounded-xl border border-sea-200 bg-sea-50/60 p-5 space-y-4">
                  <div>
                    <h3 className="text-sm font-bold text-sea-900">Builder Acceptance & PayPal Lock-in</h3>
                    <p className="text-xs text-sea-800 mt-1">
                      By signing, you agree to deliver the project in accordance with the specification within {contract.delivery_days} days once the campaign is funded.
                    </p>
                  </div>

                  {acceptError && (
                    <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700">
                      {acceptError}
                    </div>
                  )}

                  <div>
                    <label htmlFor="paypal-email" className="block text-xs font-semibold text-slate-700 mb-1">
                      Your PayPal Account Email (payout destination)
                    </label>
                    <input
                      id="paypal-email"
                      type="email"
                      required
                      value={paypalEmail}
                      onChange={(e) => setPaypalEmail(e.target.value)}
                      placeholder="arjun@velugudev.com"
                      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-sea-500 focus:ring-1 focus:ring-sea-500"
                    />
                    <p className="mt-1 text-2xs text-slate-500">
                      This email will be immutably verified by Payment Guardian before any payout is executed.
                    </p>
                  </div>

                  <div className="flex items-center gap-3 pt-2">
                    <button
                      type="submit"
                      disabled={accepting}
                      className="rounded-lg bg-sea-600 px-5 py-2.5 text-xs sm:text-sm font-semibold text-white shadow-xs hover:bg-sea-700 disabled:opacity-50 transition"
                    >
                      {accepting ? "Signing Contract..." : "Sign & Accept Contract"}
                    </button>
                    <Link
                      href={`/brd?id=${projectId}`}
                      className="text-xs font-semibold text-slate-600 hover:text-slate-800 underline"
                    >
                      Review BRD Requirements
                    </Link>
                  </div>
                </form>
              ) : (
                <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 text-xs text-slate-600">
                  <p className="font-semibold text-slate-700">Awaiting Freelancer Signature</p>
                  <p className="mt-1">
                    The contract has been offered to the freelancer. Once signed with their verified PayPal email, the campaign can be launched.
                  </p>
                </div>
              )}
            </div>
          ) : isLead ? (
            /* Lead Offer Form */
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">Offer Conditional Contract</h2>
                <p className="text-xs text-slate-500 mt-1">
                  Propose compensation and delivery terms based on the approved Business Requirements Document.
                </p>
              </div>

              {offerError && (
                <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700">
                  {offerError}
                </div>
              )}

              <form onSubmit={handleOffer} className="space-y-4">
                <div>
                  <label htmlFor="amount" className="block text-xs font-semibold text-slate-700 mb-1">
                    Contract Budget (USD)
                  </label>
                  <div className="relative rounded-lg shadow-xs">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                      <span className="text-slate-500 text-sm">$</span>
                    </div>
                    <input
                      id="amount"
                      type="number"
                      step="1"
                      min="1"
                      max="10000"
                      value={amountDollars ?? budgetDollars}
                      onChange={(e) => setAmountDollars(e.target.value)}
                      className="w-full rounded-lg border border-slate-300 bg-white pl-7 pr-3 py-2 text-sm text-slate-900 focus:border-sea-500 focus:ring-1 focus:ring-sea-500 font-semibold"
                    />
                  </div>
                  <p className="mt-1 text-2xs text-slate-500">Must match or be within approved project budget.</p>
                </div>

                <div>
                  <label htmlFor="delivery-days" className="block text-xs font-semibold text-slate-700 mb-1">
                    Delivery Timeframe (Days)
                  </label>
                  <input
                    id="delivery-days"
                    type="number"
                    min="1"
                    max="90"
                    value={deliveryDays}
                    onChange={(e) => setDeliveryDays(parseInt(e.target.value, 10))}
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-sea-500 focus:ring-1 focus:ring-sea-500"
                  />
                  <p className="mt-1 text-2xs text-slate-500">Days from campaign funding completion until deliverables must be submitted.</p>
                </div>

                {brd && (
                  <div className="rounded-lg bg-slate-50 p-3 border border-slate-200 text-xs text-slate-600 space-y-1">
                    <p className="font-semibold text-slate-700">BRD Hash Lock:</p>
                    <p className="font-mono text-2xs text-slate-800 break-all">{brd.sha256}</p>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={offering}
                  className="w-full rounded-lg bg-sea-600 px-4 py-2.5 text-xs sm:text-sm font-semibold text-white shadow-xs hover:bg-sea-700 disabled:opacity-50 transition"
                >
                  {offering ? "Offering Contract..." : "Send Contract Offer to Freelancer"}
                </button>
              </form>
            </div>
          ) : (
            <Empty title="No Contract Offered Yet">
              <p>The project lead has not yet issued a contract offer for this project.</p>
            </Empty>
          )}
        </div>

        {/* Sidebar Summary */}
        <div className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs text-xs space-y-4">
            <h3 className="font-bold text-slate-900 text-sm border-b border-slate-100 pb-2">Contract Safeguards</h3>
            
            <div className="space-y-3 text-slate-600">
              <div className="flex items-start gap-2">
                <span className="text-sea-600 font-bold">1.</span>
                <p><strong>Hash Invariance:</strong> Changing any requirement in the BRD invalidates the contract hash.</p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-sea-600 font-bold">2.</span>
                <p><strong>Strict Honor Window:</strong> Authorization holds expire in 72h. Campaign will automatically release holds if target is missed.</p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-sea-600 font-bold">3.</span>
                <p><strong>Verification Gate:</strong> Money cannot be paid out until the autonomous Verifier Agent confirms deliverable proof.</p>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100">
              <Link
                href={`/ledger?id=${projectId}`}
                className="text-sea-700 font-semibold hover:underline block"
              >
                View Public Audit Ledger &rarr;
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function FromQuery() {
  const raw = useSearchParams().get("id");
  const id = raw !== null && /^\d{1,9}$/.test(raw) ? Number(raw) : null;
  if (id === null) {
    return <Empty title="No project selected">Select a project to view contract.</Empty>;
  }
  return <ContractStudio projectId={id} />;
}

export default function ContractPage() {
  return (
    <Suspense fallback={<Loading what="Loading contract" />}>
      <FromQuery />
    </Suspense>
  );
}
