"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { Stepper } from "@/components/Stepper";
import { WorkflowNav } from "@/components/WorkflowNav";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { apiGet, apiPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  ProjectDetail,
  SubmissionDetail,
  SubmissionListItem,
} from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { checkTarget, problemText } from "@/lib/verifyview";

ModuleRegistry.registerModules([AllCommunityModule]);

type CriterionRow = {
  requirement_code: string;
  criterion_id: string;
  priority: string;
  verdict: "PASS" | "FAIL" | "INSUFFICIENT_EVIDENCE" | string;
  source: string;
  confidence: number;
  reason: string;
};

type FailureOptions = {
  submission_id: number;
  state: string;
  open: boolean;
  attempts_used: number;
  attempts_allowed: number;
  extra_attempts_left: number;
  extend: { max_now: number };
  override: {
    needed: number;
    approved: number;
    sponsors: { member_id: number; name: string; vote: string; note: string | null }[];
  };
};

function VerificationStudio({ projectId, initialSubId }: { projectId: number; initialSubId: number | null }) {
  const auth = useAuth();
  const { data: project, error: pErr, loading: pLoading, slow: pSlow, reload: reloadProject } =
    useApi<ProjectDetail>(auth.status === "loading" ? null : `/projects/${projectId}`, auth.user?.id ?? null);

  const [submissions, setSubmissions] = useState<SubmissionListItem[]>([]);
  const [selectedSubId, setSelectedSubId] = useState<number | null>(initialSubId);
  const [sub, setSub] = useState<SubmissionDetail | null>(null);
  const [subLoading, setSubLoading] = useState<boolean>(false);
  const [loadProblem, setLoadProblem] = useState<string | null>(null);
  const [failureOptions, setFailureOptions] = useState<FailureOptions | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<boolean>(false);

  // Extend / Override state
  const [overrideVote, setOverrideVote] = useState<"APPROVE" | "REJECT">("APPROVE");
  const [overrideNote, setOverrideNote] = useState<string>("");

  const loadSubmissions = async () => {
    setLoadProblem(null);
    try {
      const res = await apiGet<{ submissions: SubmissionListItem[] }>(`/projects/${projectId}/submissions`);
      setSubmissions(res.submissions || []);
      if (!selectedSubId && res.submissions && res.submissions.length > 0) {
        setSelectedSubId(res.submissions[res.submissions.length - 1].id);
      }
    } catch (err) {
      setLoadProblem(problemText(err, "Could not load the submissions."));
    }
  };

  useEffect(() => {
    if (projectId) {
      loadSubmissions();
    }
  }, [projectId]);

  const loadDetail = async (id: number) => {
    setSubLoading(true);
    try {
      const data = await apiGet<SubmissionDetail>(`/submissions/${id}`);
      setSub(data);
      if (data.state === "FAILED") {
        try {
          const opts = await apiGet<FailureOptions>(`/submissions/${id}/failure-options`);
          setFailureOptions(opts);
        } catch {
          setFailureOptions(null);
        }
      } else {
        setFailureOptions(null);
      }
    } catch (err) {
      setLoadProblem(problemText(err, "Could not load this submission."));
    } finally {
      setSubLoading(false);
    }
  };

  useEffect(() => {
    if (selectedSubId) {
      loadDetail(selectedSubId);
    }
  }, [selectedSubId]);

  const isLead = project?.viewer?.role === "LEAD";
  const isSponsor = project?.viewer?.role === "SPONSOR" || isLead;

  // AG Grid Rows
  const criteriaRows = useMemo<CriterionRow[]>(() => {
    if (!sub?.report?.details) return [];
    const details = sub.report.details as { criteria?: CriterionRow[] };
    if (!Array.isArray(details.criteria)) return [];
    return details.criteria;
  }, [sub]);

  // AG Grid Column Definitions
  const columns = useMemo<ColDef<CriterionRow>[]>(() => [
    {
      field: "requirement_code",
      headerName: "Req Code",
      width: 110,
      pinned: "left",
      sort: "asc",
      cellClass: "font-mono font-bold text-slate-800",
    },
    {
      field: "criterion_id",
      headerName: "Criterion",
      width: 120,
      cellClass: "font-mono text-slate-700",
    },
    {
      field: "priority",
      headerName: "Priority",
      width: 100,
      cellClass: (p) =>
        p.value === "MUST" ? "font-bold text-red-700" : "font-semibold text-sea-700",
    },
    {
      field: "verdict",
      headerName: "Verdict",
      width: 130,
      cellRenderer: (p: { value: string }) => {
        const val = p.value || "PENDING";
        const isPass = val === "PASS" || val === "VERIFIED";
        return (
          <span
            className={`inline-block rounded-full px-2 py-0.5 text-xs font-bold ${
              isPass
                ? "bg-emerald-100 text-emerald-800"
                : "bg-red-100 text-red-800"
            }`}
          >
            {isPass ? "✓ " : "✗ "}
            {val}
          </span>
        );
      },
    },
    {
      field: "source",
      headerName: "Verification Source",
      width: 150,
      cellClass: "text-2xs font-semibold text-slate-600",
    },
    {
      field: "confidence",
      headerName: "Confidence",
      width: 110,
      valueFormatter: (p) => (p.value != null ? `${Math.round(p.value * 100)}%` : "100%"),
      cellClass: "font-mono text-xs text-slate-700",
    },
    {
      field: "reason",
      headerName: "Evidence & Reasoning",
      flex: 1,
      minWidth: 280,
      cellClass: "text-xs text-slate-700",
    },
  ], []);

  const handleExtend = async () => {
    if (!selectedSubId) return;
    setActionBusy(true);
    setActionMsg(null);
    try {
      await apiPost(`/submissions/${selectedSubId}/extend`, { extra_attempts: 1 });
      setActionMsg("Granted 1 additional attempt to the freelancer.");
      await loadDetail(selectedSubId);
      reloadProject();
    } catch (err: unknown) {
      setActionMsg(err instanceof Error ? err.message : "Failed to extend attempts");
    } finally {
      setActionBusy(false);
    }
  };

  const handleOverride = async () => {
    if (!selectedSubId) return;
    setActionBusy(true);
    setActionMsg(null);
    try {
      await apiPost(`/submissions/${selectedSubId}/override`, {
        decision: overrideVote,
        note: overrideNote.trim() || null,
      });
      setActionMsg("Sponsor override vote recorded.");
      await loadDetail(selectedSubId);
      reloadProject();
    } catch (err: unknown) {
      setActionMsg(err instanceof Error ? err.message : "Failed to record override vote");
    } finally {
      setActionBusy(false);
    }
  };

  const handleCancelRefund = async () => {
    if (!selectedSubId) return;
    if (!confirm("Are you sure you want to cancel the project and initiate refunds? All pledge holds will be released.")) {
      return;
    }
    setActionBusy(true);
    setActionMsg(null);
    try {
      const res = await apiPost<{ plan_id: number }>(`/submissions/${selectedSubId}/cancel-refund`, {});
      setActionMsg(`Refund money plan #${res.plan_id} created. Guardian review queued.`);
      await loadDetail(selectedSubId);
      reloadProject();
    } catch (err: unknown) {
      setActionMsg(err instanceof Error ? err.message : "Failed to cancel project");
    } finally {
      setActionBusy(false);
    }
  };

  if (auth.status === "loading" || pLoading) {
    return <Loading what="Loading verification report" slow={pSlow} />;
  }
  if (pErr) return <ErrorBox error={pErr} onRetry={reloadProject} />;
  if (!project) return null;

  const report = sub?.report;
  const isVerified = sub?.state === "VERIFIED" || report?.overall === "VERIFIED";

  return (
    <div className="space-y-6">
      {loadProblem && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{loadProblem}</p>}
      <WorkflowNav
        projectId={projectId}
        projectTitle={project.title}
        projectState={project.state}
        currentStep="Verify"
        nextAction={isVerified ? {
          label: "Proceed to Guardian Settlement",
          href: `/plans?id=${projectId}`,
          badge: "Verification Passed",
          description: "All acceptance criteria verified! Review and approve payout plan.",
        } : null}
      />

      {/* Prominent Forward Navigation Banner when Verified */}
      {isVerified && (
        <section aria-label="Verification passed" className="rounded-2xl border-2 border-emerald-500/80 bg-gradient-to-r from-emerald-50 via-teal-50 to-white p-5 sm:p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-600 text-xs font-bold text-white shadow-xs">✓</span>
                <h2 className="text-base sm:text-lg font-bold text-slate-900">
                  Deliverable Verified: 100% Passing Criteria!
                </h2>
              </div>
              <p className="text-xs sm:text-sm text-slate-600 max-w-2xl">
                The autonomous verification engine and Gemini Vision AI judged the live deliverable against the locked BRD specification. The project has satisfied all must-have criteria and is ready for Payment Guardian review and payout disbursement.
              </p>
            </div>
            <Link
              href={`/plans?id=${projectId}`}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-700 px-5 py-3 text-sm font-bold text-white shadow-md hover:from-emerald-700 hover:to-teal-800 transition hover:scale-[1.02] hover:shadow-lg"
            >
              <span>Proceed to Guardian Settlement</span>
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
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
              Autonomous Verification Matrix
            </h1>
            <p className="mt-1 text-xs text-slate-500 font-medium">
              Step 6 of 8 &bull; Deterministic Auto-Checks & AI Vision Inspection
            </p>
          </div>
          <div className="flex items-center gap-2">
            {isVerified ? (
              <Badge tone="green">VERIFIED: Ready for Payout</Badge>
            ) : sub ? (
              <Badge tone={sub.state === "NEEDS_CHANGES" ? "amber" : sub.state === "FAILED" ? "red" : "teal"}>
                {sub.state}
              </Badge>
            ) : (
              <Badge tone="grey">Awaiting Submission</Badge>
            )}
          </div>
        </div>

        <div className="mt-6 border-t border-slate-100 pt-5">
          <Stepper state={project.state} projectId={projectId} />
        </div>
      </div>

      {/* Attempt Switcher */}
      {submissions.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-xs">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-slate-600">Verification Attempts:</span>
            {submissions.map((s) => (
              <button
                key={s.id}
                onClick={() => setSelectedSubId(s.id)}
                className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
                  selectedSubId === s.id
                    ? "bg-sea-600 text-white shadow-xs"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                Attempt #{s.attempt_no} &bull; {s.state}
              </button>
            ))}
          </div>

          <div className="text-xs text-slate-500">
            <Link href={`/submit?id=${projectId}`} className="text-sea-700 font-semibold hover:underline">
              Freelancer Evidence Portal &rarr;
            </Link>
          </div>
        </div>
      )}

      {subLoading ? (
        <Loading what="Loading verification matrix" />
      ) : !sub ? (
        <Empty title="No Submissions to Verify">
          <p>Deliverables have not yet been submitted for this project.</p>
          <div className="mt-4">
            <Link
              href={`/submit?id=${projectId}`}
              className="rounded-lg bg-sea-600 px-4 py-2 text-xs font-semibold text-white hover:bg-sea-700"
            >
              Go to Freelancer Submit Portal
            </Link>
          </div>
        </Empty>
      ) : (
        <>
          {/* Top Verdict & Metrics Card */}
          <div className="grid gap-4 sm:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
              <span className="text-2xs font-bold uppercase tracking-wider text-slate-500">Overall Verdict</span>
              <p className={`mt-1 text-xl font-black ${
                isVerified ? "text-emerald-700" : "text-slate-900"
              }`}>
                {report?.overall || sub.state}
              </p>
              <p className="text-2xs text-slate-500 mt-0.5">Attempt #{sub.attempt_no}</p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
              <span className="text-2xs font-bold uppercase tracking-wider text-slate-500">MUST-Pass Compliance</span>
              <p className="mt-1 text-xl font-black text-slate-900">
                {report ? `${report.must_pass_pct}%` : "100%"}
              </p>
              <p className="text-2xs text-slate-500 mt-0.5">Threshold: 100% required</p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
              <span className="text-2xs font-bold uppercase tracking-wider text-slate-500">SHOULD-Pass Compliance</span>
              <p className="mt-1 text-xl font-black text-slate-900">
                {report ? `${report.should_pass_pct}%` : "100%"}
              </p>
              <p className="text-2xs text-slate-500 mt-0.5">Quality recommendations</p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
              <span className="text-2xs font-bold uppercase tracking-wider text-slate-500">Auto-Checks Passed</span>
              <p className="mt-1 text-xl font-black text-emerald-700">
                {sub.auto_check_summary?.PASS ?? 0} / {sub.auto_checks?.length ?? 0}
              </p>
              <p className="text-2xs text-slate-500 mt-0.5">Deterministic SSRF-safe checks</p>
            </div>
          </div>

          {/* Verification Banner */}
          {isVerified ? (
            <div className="rounded-2xl border border-emerald-300 bg-emerald-50/70 p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-emerald-700 text-lg">🎉</span>
                  <h3 className="text-base font-bold text-emerald-900">Verification Passed with Complete Proof</h3>
                </div>
                <p className="text-xs text-emerald-800 max-w-2xl leading-relaxed">
                  All requirements and acceptance criteria have been verified through autonomous checks and AI inspection. The Payment Guardian can now review the money plan to release funds to the builder.
                </p>
              </div>
              <div>
                <Link
                  href={`/plans?id=${projectId}`}
                  className="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-5 py-2.5 text-xs sm:text-sm font-bold text-white shadow-xs hover:bg-emerald-800 transition"
                >
                  <span>🛡️</span> Proceed to Payment Guardian &rarr;
                </Link>
              </div>
            </div>
          ) : sub.state === "NEEDS_CHANGES" ? (
            <div className="rounded-xl border border-amber-300 bg-amber-50/80 p-4 shadow-xs text-xs text-amber-900 space-y-1">
              <p className="font-bold">⚠️ Changes Requested on Attempt #{sub.attempt_no}</p>
              <p className="leading-relaxed">
                Some acceptance criteria did not meet required conditions. The freelancer can commit updates and submit a new attempt.
              </p>
            </div>
          ) : null}

          {/* SHA-256 Report Fingerprint Pill */}
          {report?.sha256 && (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs text-slate-600 shadow-xs flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-700">Verification Report Hash:</span>
                <code className="font-mono text-2xs bg-slate-100 px-2 py-0.5 rounded text-slate-900 select-all">
                  {report.sha256}
                </code>
              </div>
              <span className="text-2xs text-slate-500">Hash-bound to Payment Guardian Rules (G-07)</span>
            </div>
          )}

          {/* Action Message alert */}
          {actionMsg && (
            <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-xs text-blue-900">
              {actionMsg}
            </div>
          )}

          {/* Sponsor Failure Resolution Card (shown if FAILED and user is sponsor) */}
          {failureOptions && failureOptions.open && isSponsor && (
            <div className="rounded-2xl border border-red-200 bg-red-50/60 p-5 shadow-xs space-y-4">
              <div>
                <h3 className="font-bold text-red-900 text-sm">Sponsor Failure Resolution</h3>
                <p className="text-xs text-red-800 mt-0.5">
                  This submission failed automated verification. The project lead and sponsors may choose an action below.
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-3 pt-1">
                {isLead && failureOptions.extra_attempts_left > 0 && (
                  <button
                    type="button"
                    onClick={handleExtend}
                    disabled={actionBusy}
                    className="rounded-lg border border-slate-300 bg-white p-3 text-left hover:bg-slate-50 transition shadow-xs"
                  >
                    <span className="block text-xs font-bold text-slate-900">Grant Extra Attempt</span>
                    <span className="block text-2xs text-slate-500 mt-1">
                      Give the freelancer 1 more chance ({failureOptions.extra_attempts_left} left).
                    </span>
                  </button>
                )}

                <div className="rounded-lg border border-slate-300 bg-white p-3 shadow-xs space-y-2">
                  <span className="block text-xs font-bold text-slate-900">Vote Override</span>
                  <div className="flex items-center gap-2">
                    <select
                      value={overrideVote}
                      onChange={(e) => setOverrideVote(e.target.value as "APPROVE" | "REJECT")}
                      className="rounded border border-slate-300 text-2xs p-1"
                    >
                      <option value="APPROVE">Approve Deliverables</option>
                      <option value="REJECT">Reject Override</option>
                    </select>
                    <button
                      type="button"
                      onClick={handleOverride}
                      disabled={actionBusy}
                      className="rounded bg-sea-600 px-2.5 py-1 text-2xs font-bold text-white hover:bg-sea-700 disabled:opacity-50"
                    >
                      Vote
                    </button>
                  </div>
                  <span className="block text-2xs text-slate-500">
                    Approved by {failureOptions.override.approved} of {failureOptions.override.needed} sponsors.
                  </span>
                </div>

                {isLead && (
                  <button
                    type="button"
                    onClick={handleCancelRefund}
                    disabled={actionBusy}
                    className="rounded-lg border border-red-300 bg-red-100/70 p-3 text-left hover:bg-red-200/70 transition shadow-xs"
                  >
                    <span className="block text-xs font-bold text-red-900">Cancel & Refund</span>
                    <span className="block text-2xs text-red-700 mt-1">
                      Build refund money plan and release all pledge holds.
                    </span>
                  </button>
                )}
              </div>
            </div>
          )}

          {/* AG Grid Verification Matrix */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div>
                <h2 className="text-base font-bold text-slate-900">Requirement Criteria Verification Matrix</h2>
                <p className="text-xs text-slate-500">Every requirement mapped to automated checks and vision inspection</p>
              </div>
              <span className="text-xs font-semibold text-slate-600">
                {criteriaRows.length} Criteria Tested
              </span>
            </div>

            {criteriaRows.length > 0 ? (
              <div className="w-full rounded-2xl overflow-hidden border border-slate-200" style={{ height: "380px" }}>
                <AgGridReact
                  theme={themeQuartz}
                  rowData={criteriaRows}
                  columnDefs={columns}
                  defaultColDef={{ resizable: true, sortable: true, filter: true }}
                />
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-slate-600 italic">
                  Criteria level breakdowns will populate once the Verifier AI Agent finishes evaluating evidence.
                </p>
                {/* Fallback table if criteria not yet loaded */}
                {sub.auto_checks && sub.auto_checks.length > 0 && (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <h3 className="text-xs font-bold text-slate-700 uppercase mb-2">Automated Checks Executed</h3>
                    <div className="space-y-2 text-xs">
                      {sub.auto_checks.map((chk) => (
                        <div key={chk.id} className="flex items-center justify-between bg-white p-2 rounded border border-slate-200">
                          <div>
                            <span className="font-bold text-slate-800">{chk.check_type}</span>
                            <span className="text-slate-500 font-mono text-2xs ml-2">{checkTarget(chk.input)}</span>
                          </div>
                          <span className={`font-bold px-2 py-0.5 rounded text-2xs ${
                            chk.result === "PASS" ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"
                          }`}>
                            {chk.result}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function FromQuery() {
  const params = useSearchParams();
  const rawId = params.get("id");
  const rawSub = params.get("sub");
  const id = rawId !== null && /^\d{1,9}$/.test(rawId) ? Number(rawId) : null;
  const subId = rawSub !== null && /^\d{1,9}$/.test(rawSub) ? Number(rawSub) : null;
  if (id === null) {
    return <Empty title="No project selected">Select a project to view verification report.</Empty>;
  }
  return <VerificationStudio projectId={id} initialSubId={subId} />;
}

export default function VerifyPage() {
  return (
    <Suspense fallback={<Loading what="Loading verification report" />}>
      <FromQuery />
    </Suspense>
  );
}
