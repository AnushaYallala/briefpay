"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Stepper } from "@/components/Stepper";
import { WorkflowNav } from "@/components/WorkflowNav";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { apiGet, apiPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatMoney } from "@/lib/money";
import type {
  ContractResponse,
  ProjectDetail,
  SubmissionDetail,
  SubmissionListItem,
  VerificationQuestionItem,
} from "@/lib/types";
import { useApi } from "@/lib/useApi";

function SubmitStudio({ projectId }: { projectId: number }) {
  const auth = useAuth();
  const { data: project, error: pErr, loading: pLoading, slow: pSlow, reload: reloadProject } =
    useApi<ProjectDetail>(auth.status === "loading" ? null : `/projects/${projectId}`, auth.user?.id ?? null);

  const { data: contract } = useApi<ContractResponse>(`/projects/${projectId}/contract`);

  const [submissions, setSubmissions] = useState<SubmissionListItem[]>([]);
  const [selectedSubId, setSelectedSubId] = useState<number | null>(null);
  const [currentSub, setCurrentSub] = useState<SubmissionDetail | null>(null);
  const [subLoading, setSubLoading] = useState<boolean>(false);

  // New submission form - starts empty with quick paste helper (no fake defaults)
  const [repoUrl, setRepoUrl] = useState<string>("");
  const [commitSha, setCommitSha] = useState<string>("");
  const [deployedUrl, setDeployedUrl] = useState<string>("");
  const [notes, setNotes] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Question answering state
  const [answeringQId, setAnsweringQId] = useState<number | null>(null);
  const [evidenceSnippet, setEvidenceSnippet] = useState<string>("");
  const [evidenceRepoPath, setEvidenceRepoPath] = useState<string>("");
  const [evidenceUrl, setEvidenceUrl] = useState<string>("");
  const [evidenceText, setEvidenceText] = useState<string>("");
  const [savingEvidence, setSavingEvidence] = useState<boolean>(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  // Judging state
  const [judging, setJudging] = useState<boolean>(false);
  const [judgeMsg, setJudgeMsg] = useState<string | null>(null);

  const loadSubmissions = async () => {
    try {
      const res = await apiGet<{ submissions: SubmissionListItem[] }>(`/projects/${projectId}/submissions`);
      setSubmissions(res.submissions || []);
      if (res.submissions && res.submissions.length > 0) {
        // Default to latest
        const latest = res.submissions[res.submissions.length - 1];
        if (!selectedSubId) {
          setSelectedSubId(latest.id);
        }
      }
    } catch {
      // Submissions may be empty initially
    }
  };

  useEffect(() => {
    if (projectId) {
      loadSubmissions();
    }
  }, [projectId]);

  useEffect(() => {
    if (!selectedSubId) {
      setCurrentSub(null);
      return;
    }
    setSubLoading(true);
    apiGet<SubmissionDetail>(`/submissions/${selectedSubId}`)
      .then((data: SubmissionDetail) => {
        setCurrentSub(data);
      })
      .catch((err: unknown) => {
        console.error(err);
      })
      .finally(() => {
        setSubLoading(false);
      });
  }, [selectedSubId]);

  if (auth.status === "loading" || pLoading) {
    return <Loading what="Loading freelancer workspace" slow={pSlow} />;
  }
  if (pErr) return <ErrorBox error={pErr} onRetry={reloadProject} />;
  if (!project) return null;

  const isFreelancer = project.viewer?.role === "FREELANCER" || project.viewer?.role === "LEAD";

  const handleSubmitWork = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      if (!repoUrl.trim() || !commitSha.trim() || !deployedUrl.trim()) {
        throw new Error("Repository URL, commit SHA, and deployed URL are all required.");
      }
      const res = await apiPost<{ submission_id: number; attempt_no: number }>(`/projects/${projectId}/submissions`, {
        repo_url: repoUrl.trim(),
        commit_sha: commitSha.trim(),
        deployed_url: deployedUrl.trim(),
        notes: notes.trim() || null,
      });
      await loadSubmissions();
      setSelectedSubId(res.submission_id);
      reloadProject();
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Failed to submit work");
    } finally {
      setSubmitting(false);
    }
  };

  const handleAnswerQuestion = async (q: VerificationQuestionItem) => {
    setSavingEvidence(true);
    setEvidenceError(null);
    try {
      await apiPost(`/verification/questions/${q.id}/evidence`, {
        code_snippet: evidenceSnippet.trim() || null,
        repo_path: evidenceRepoPath.trim() || null,
        url: evidenceUrl.trim() || null,
        text: evidenceText.trim() || null,
        image_ids: [],
      });
      // Refresh current submission
      if (selectedSubId) {
        const refreshed = await apiGet<SubmissionDetail>(`/submissions/${selectedSubId}`);
        setCurrentSub(refreshed);
      }
      setAnsweringQId(null);
      setEvidenceSnippet("");
      setEvidenceRepoPath("");
      setEvidenceUrl("");
      setEvidenceText("");
    } catch (err: unknown) {
      setEvidenceError(err instanceof Error ? err.message : "Failed to record evidence");
    } finally {
      setSavingEvidence(false);
    }
  };

  const handleTriggerJudge = async () => {
    if (!selectedSubId) return;
    setJudging(true);
    setJudgeMsg(null);
    try {
      await apiPost(`/submissions/${selectedSubId}/judge`, {});
      setJudgeMsg("AI Verification Judge triggered. Assessing requirements against submitted evidence...");
      // Poll/refresh after a short delay
      setTimeout(async () => {
        try {
          const refreshed = await apiGet<SubmissionDetail>(`/submissions/${selectedSubId}`);
          setCurrentSub(refreshed);
          reloadProject();
        } catch {
          // ignore
        }
        setJudging(false);
      }, 2000);
    } catch (err: unknown) {
      setJudgeMsg(err instanceof Error ? err.message : "Failed to trigger judge");
      setJudging(false);
    }
  };

  return (
    <div className="space-y-6">
      <WorkflowNav
        projectId={projectId}
        projectTitle={project.title}
        projectState={project.state}
        currentStep="Build"
        nextAction={submissions.length > 0 ? {
          label: "Proceed to AI Verification",
          href: `/verify?id=${projectId}`,
          badge: "Submission Available",
          description: "Deliverables are submitted. Review autonomous checks and Vision AI verification.",
        } : null}
      />

      {/* Header card with Stepper */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs">
        <div className="mb-2">
          <Link href={`/project?id=${projectId}`} className="inline-flex items-center gap-1 text-xs font-semibold text-sea-700 hover:text-sea-800 transition">
            <span aria-hidden="true">&larr;</span> Back to Project
          </Link>
        </div>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">Freelancer Delivery Portal</h1>
            <p className="mt-1 text-xs text-slate-500 font-medium">
              Step 5 of 8 &bull; Submit deliverables, provide verification evidence, and trigger automated checks
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href={`/verify?id=${projectId}${selectedSubId ? `&sub=${selectedSubId}` : ""}`}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
            >
              <span>📊</span> Verification Report Matrix &rarr;
            </Link>
          </div>
        </div>

        <div className="mt-6 border-t border-slate-100 pt-5">
          <Stepper state={project.state} projectId={projectId} />
        </div>
      </div>

      {/* Contract & Submission Attempts Status Bar */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
          <span className="text-2xs font-bold uppercase tracking-wider text-slate-500">Contract Value</span>
          <p className="mt-1 text-xl font-black text-slate-900">
            {contract ? formatMoney(contract.amount_cents, contract.currency) : "$400.00"}
          </p>
          <p className="text-2xs text-slate-500 mt-0.5">Held in POOL, ready for payout on verification</p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
          <span className="text-2xs font-bold uppercase tracking-wider text-slate-500">Attempts Used</span>
          <p className="mt-1 text-xl font-black text-slate-900">
            {submissions.length} / 3 Attempts
          </p>
          <p className="text-2xs text-slate-500 mt-0.5">Max 3 attempts before lead review or refund</p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
          <span className="text-2xs font-bold uppercase tracking-wider text-slate-500">Active Submission State</span>
          <p className="mt-1 text-xl font-bold text-sea-700">
            {currentSub?.state || (submissions.length > 0 ? "REVIEWING" : "NOT_SUBMITTED")}
          </p>
          <p className="text-2xs text-slate-500 mt-0.5">Autonomous verification pipeline</p>
        </div>
      </div>

      {/* Attempts Tabs */}
      {submissions.length > 0 && (
        <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
          <span className="text-xs font-bold text-slate-600 mr-2">Attempts:</span>
          {submissions.map((s) => (
            <button
              key={s.id}
              onClick={() => setSelectedSubId(s.id)}
              className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
                selectedSubId === s.id
                  ? "bg-sea-600 text-white shadow-xs"
                  : "bg-white text-slate-700 border border-slate-200 hover:border-slate-300"
              }`}
            >
              Attempt #{s.attempt_no} &bull; {s.state}
            </button>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left Column: Submit New Deliverable */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-bold text-slate-900">
                {submissions.length === 0 ? "Submit Work Deliverables" : "Submit New Attempt"}
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Provide the GitHub repository, commit hash, and deployed URL. Automated checks run immediately upon submission.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                setRepoUrl("https://github.com/meghavardhan-git/velugu-cove-site");
                setCommitSha("1a75b03");
                setDeployedUrl("https://velugucove.demo");
                setNotes("Delivered v2 website featuring room booking, WhatsApp contact button, seafood restaurant menu, and boat tours schedule.");
              }}
              className="rounded-xl border border-sea-200 bg-sea-50 px-3 py-1.5 text-xs font-semibold text-sea-800 hover:bg-sea-100 transition shadow-2xs"
            >
              Paste Sample Deliverables (Velugu Cove v2)
            </button>
          </div>

          {submitError && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700">
              {submitError}
            </div>
          )}

          <form onSubmit={handleSubmitWork} className="space-y-4">
            <div>
              <label htmlFor="repo-url" className="block text-xs font-semibold text-slate-700 mb-1">
                Public GitHub Repository URL
              </label>
              <input
                id="repo-url"
                type="url"
                required
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/velugu-cove/tourism-site"
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-sea-500 focus:ring-1 focus:ring-sea-500"
              />
              <p className="mt-1 text-2xs text-slate-500">AutoChecker verifies public visibility and repository structure.</p>
            </div>

            <div>
              <label htmlFor="commit-sha" className="block text-xs font-semibold text-slate-700 mb-1">
                Git Commit SHA (40 chars)
              </label>
              <input
                id="commit-sha"
                type="text"
                required
                maxLength={64}
                value={commitSha}
                onChange={(e) => setCommitSha(e.target.value)}
                placeholder="4b825dc642cb6eb9a060e54bf8d69288fbee4904"
                className="w-full font-mono rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-sea-500 focus:ring-1 focus:ring-sea-500"
              />
            </div>

            <div>
              <label htmlFor="deployed-url" className="block text-xs font-semibold text-slate-700 mb-1">
                Deployed Website / Application URL
              </label>
              <input
                id="deployed-url"
                type="url"
                required
                value={deployedUrl}
                onChange={(e) => setDeployedUrl(e.target.value)}
                placeholder="https://velugucove.demo"
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-sea-500 focus:ring-1 focus:ring-sea-500"
              />
              <p className="mt-1 text-2xs text-slate-500">AutoChecker performs SSRF-safe HTTP checks and mobile viewport tests.</p>
            </div>

            <div>
              <label htmlFor="notes" className="block text-xs font-semibold text-slate-700 mb-1">
                Submission Notes & Implementation Highlights
              </label>
              <textarea
                id="notes"
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Detail key architectural decisions or specific instructions for verifiers..."
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 focus:border-sea-500 focus:ring-1 focus:ring-sea-500"
              />
            </div>

            <button
              type="submit"
              disabled={submitting || !isFreelancer}
              className="w-full rounded-lg bg-sea-600 px-4 py-2.5 text-xs sm:text-sm font-semibold text-white shadow-xs hover:bg-sea-700 disabled:opacity-50 transition"
            >
              {submitting ? "Submitting Deliverables..." : `Submit Deliverables (Attempt #${submissions.length + 1})`}
            </button>
          </form>
        </div>

        {/* Right Column: Active Submission Details, Questions & Auto-Checks */}
        <div className="space-y-6">
          {subLoading ? (
            <Loading what="Loading submission evidence & checks" />
          ) : currentSub ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs space-y-6">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div>
                  <h3 className="font-bold text-slate-900">Attempt #{currentSub.attempt_no} Status</h3>
                  <p className="text-2xs text-slate-500 font-mono">Commit: {currentSub.commit_sha.slice(0, 10)}...</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold bg-sea-100 text-sea-800">
                    {currentSub.state}
                  </span>
                </div>
              </div>

              {/* Auto-Checks Summary */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Automated Checks</h4>
                <div className="flex items-center gap-3 text-xs mb-3">
                  <span className="font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                    PASS: {currentSub.auto_check_summary?.PASS ?? 0}
                  </span>
                  <span className="font-semibold text-red-700 bg-red-50 border border-red-200 px-2 py-0.5 rounded">
                    FAIL: {currentSub.auto_check_summary?.FAIL ?? 0}
                  </span>
                  <span className="font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                    ERROR: {currentSub.auto_check_summary?.ERROR ?? 0}
                  </span>
                </div>

                {currentSub.auto_checks && currentSub.auto_checks.length > 0 && (
                  <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-2.5 space-y-1 max-h-40 overflow-y-auto text-2xs font-mono">
                    {currentSub.auto_checks.map((chk) => (
                      <div key={chk.id} className="flex items-center justify-between py-0.5 border-b border-slate-100 last:border-0">
                        <span className="text-slate-700">{chk.check_type}: {chk.target}</span>
                        <span className={`font-bold px-1.5 py-0.2 rounded ${
                          chk.result === "PASS" ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"
                        }`}>
                          {chk.result}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Verifier Evidence Questions */}
              <div className="border-t border-slate-100 pt-4">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Verification Questions ({currentSub.questions?.length ?? 0})
                  </h4>
                  {currentSub.questions && currentSub.questions.length > 0 && (
                    <button
                      type="button"
                      onClick={handleTriggerJudge}
                      disabled={judging}
                      className="rounded-lg bg-emerald-600 px-3 py-1 text-2xs font-bold text-white hover:bg-emerald-700 transition disabled:opacity-50"
                    >
                      {judging ? "Judging..." : "Run AI Judge"}
                    </button>
                  )}
                </div>

                {judgeMsg && (
                  <div className="rounded-lg bg-blue-50 border border-blue-200 p-2.5 text-xs text-blue-800 mb-3">
                    {judgeMsg}
                  </div>
                )}

                {currentSub.questions && currentSub.questions.length > 0 ? (
                  <div className="space-y-3">
                    {currentSub.questions.map((q) => {
                      const isAnswering = answeringQId === q.id;
                      const hasEvidence = currentSub.evidence?.some((e) => e.question_id === q.id);
                      return (
                        <div key={q.id} className="rounded-xl border border-slate-200 bg-slate-50/50 p-3 text-xs space-y-2">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <span className="font-bold text-slate-900">[{q.requirement_code}]</span>{" "}
                              <span className="text-slate-700">{q.question}</span>
                            </div>
                            <span className={`px-2 py-0.5 rounded text-2xs font-bold ${
                              hasEvidence ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
                            }`}>
                              {hasEvidence ? "Answered" : "Needs Evidence"}
                            </span>
                          </div>

                          {q.expected_evidence && q.expected_evidence.length > 0 && (
                            <div className="flex flex-wrap gap-1 text-2xs">
                              <span className="text-slate-500">Expected:</span>
                              {q.expected_evidence.map((ev, i) => (
                                <span key={i} className="bg-slate-200/80 text-slate-700 px-1.5 py-0.2 rounded font-mono">
                                  {ev}
                                </span>
                              ))}
                            </div>
                          )}

                          {isAnswering ? (
                            <div className="space-y-2 pt-2 border-t border-slate-200">
                              {evidenceError && (
                                <p className="text-2xs text-red-600 font-semibold">{evidenceError}</p>
                              )}
                              <div>
                                <label className="block text-2xs font-semibold text-slate-600 mb-0.5">Code Snippet</label>
                                <textarea
                                  rows={2}
                                  value={evidenceSnippet}
                                  onChange={(e) => setEvidenceSnippet(e.target.value)}
                                  placeholder="Paste relevant implementation code..."
                                  className="w-full rounded border border-slate-300 font-mono text-2xs p-1.5"
                                />
                              </div>
                              <div className="grid grid-cols-2 gap-2">
                                <div>
                                  <label className="block text-2xs font-semibold text-slate-600 mb-0.5">Repo Path</label>
                                  <input
                                    type="text"
                                    value={evidenceRepoPath}
                                    onChange={(e) => setEvidenceRepoPath(e.target.value)}
                                    placeholder="src/components/Form.tsx"
                                    className="w-full rounded border border-slate-300 text-2xs p-1.5"
                                  />
                                </div>
                                <div>
                                  <label className="block text-2xs font-semibold text-slate-600 mb-0.5">Specific URL</label>
                                  <input
                                    type="url"
                                    value={evidenceUrl}
                                    onChange={(e) => setEvidenceUrl(e.target.value)}
                                    placeholder="https://velugucove.demo#enquiry"
                                    className="w-full rounded border border-slate-300 text-2xs p-1.5"
                                  />
                                </div>
                              </div>
                              <div>
                                <label className="block text-2xs font-semibold text-slate-600 mb-0.5">Explanation</label>
                                <input
                                  type="text"
                                  value={evidenceText}
                                  onChange={(e) => setEvidenceText(e.target.value)}
                                  placeholder="How this criterion is satisfied..."
                                  className="w-full rounded border border-slate-300 text-2xs p-1.5"
                                />
                              </div>
                              <div className="flex items-center gap-2 pt-1">
                                <button
                                  type="button"
                                  onClick={() => handleAnswerQuestion(q)}
                                  disabled={savingEvidence}
                                  className="rounded bg-sea-600 px-3 py-1 text-2xs font-bold text-white hover:bg-sea-700 disabled:opacity-50"
                                >
                                  {savingEvidence ? "Submitting..." : "Save Evidence"}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setAnsweringQId(null)}
                                  className="text-2xs text-slate-500 hover:text-slate-700"
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="pt-1">
                              <button
                                type="button"
                                onClick={() => {
                                  setAnsweringQId(q.id);
                                  setEvidenceSnippet("");
                                  setEvidenceRepoPath("");
                                  setEvidenceUrl("");
                                  setEvidenceText("");
                                }}
                                className="text-2xs font-semibold text-sea-700 hover:text-sea-800 underline"
                              >
                                {hasEvidence ? "Add more evidence &rarr;" : "Provide evidence for this question &rarr;"}
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500 italic">No open verification questions for this attempt.</p>
                )}
              </div>

              {/* View Verification Matrix CTA */}
              <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                <Link
                  href={`/verify?id=${projectId}&sub=${currentSub.id}`}
                  className="text-xs font-bold text-sea-700 hover:text-sea-800 underline"
                >
                  Open Complete Verification Report & Matrix &rarr;
                </Link>
                {currentSub.report && (
                  <Badge tone={currentSub.report.overall === "VERIFIED" ? "green" : "red"}>
                    {currentSub.report.overall}
                  </Badge>
                )}
              </div>
            </div>
          ) : (
            <Empty title="No Submissions Yet">
              <p>Submit your initial deliverables using the form on the left to begin automated verification.</p>
            </Empty>
          )}
        </div>
      </div>
    </div>
  );
}

function FromQuery() {
  const raw = useSearchParams().get("id");
  const id = raw !== null && /^\d{1,9}$/.test(raw) ? Number(raw) : null;
  if (id === null) {
    return <Empty title="No project selected">Select a project to submit work.</Empty>;
  }
  return <SubmitStudio projectId={id} />;
}

export default function SubmitPage() {
  return (
    <Suspense fallback={<Loading what="Loading freelancer workspace" />}>
      <FromQuery />
    </Suspense>
  );
}
