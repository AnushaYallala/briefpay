"use client";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { apiPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { BAResponse, BAQuestionItem, ProjectDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function BAStudioView({ id }: { id: number }) {
  const auth = useAuth();
  const router = useRouter();
  const [refreshKey, setRefreshKey] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedOptions, setSelectedOptions] = useState<Record<number, string>>({});
  const [customAnswers, setCustomAnswers] = useState<Record<number, string>>({});
  const [showTranscript, setShowTranscript] = useState(false);

  const { data: project } = useApi<ProjectDetail>(auth.status === "loading" ? null : `/projects/${id}`, auth.user?.id ?? null);
  const { data: ba, error, loading, slow, reload } = useApi<BAResponse>(
    auth.status === "loading" ? null : `/projects/${id}/ba`,
    `${auth.user?.id ?? "anon"}-${refreshKey}`
  );
  const { data: transcriptData } = useApi<{ transcript: { source_name: string; lines: { line_no: number; text: string }[] } }>(
    showTranscript ? `/projects/${id}/transcript` : null
  );

  async function runRound() {
    setBusy("run");
    setActionError(null);
    try {
      const res = await apiPost<{ job_id: number }>(`/projects/${id}/ba/run`, {});
      // Wait for job to process
      let done = false;
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const job = await fetch(`/api/jobs/${res.job_id}`).then((r) => r.json());
        if (job.state === "DONE") {
          done = true;
          break;
        }
        if (job.state === "FAILED") {
          throw new Error(job.error ?? "BA run failed");
        }
      }
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to run BA round");
    } finally {
      setBusy(null);
    }
  }

  async function generateBRD() {
    setBusy("generate");
    setActionError(null);
    try {
      await apiPost<{ job_id: number }>(`/projects/${id}/brd/generate`, {});
      router.push(`/brd?id=${id}`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to generate BRD");
      setBusy(null);
    }
  }

  async function submitAnswer(q: BAQuestionItem) {
    const text = customAnswers[q.id]?.trim() || selectedOptions[q.id];
    if (!text) return;
    setBusy(`answer-${q.id}`);
    setActionError(null);
    try {
      await apiPost(`/ba/questions/${q.id}/answers`, {
        answer_text: text,
        selected_option: selectedOptions[q.id] || null,
      });
      setCustomAnswers((prev) => ({ ...prev, [q.id]: "" }));
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not submit answer");
    } finally {
      setBusy(null);
    }
  }

  async function skipQuestion(qId: number) {
    setBusy(`skip-${qId}`);
    setActionError(null);
    try {
      await apiPost(`/ba/questions/${qId}/skip`, {});
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not skip question");
    } finally {
      setBusy(null);
    }
  }

  if (auth.status === "loading" || loading) return <Loading what="Loading BA Studio" slow={slow} />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!ba) return null;

  const session = ba.session;
  const score = ba.score;
  const currentScore = session?.current_score ?? score?.total ?? 0;
  const targetScore = session?.target_score ?? 90;
  const isReady = currentScore >= targetScore || session?.state === "READY";

  return (
    <div className="space-y-6">
      {/* Navigation Header */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs">
        <div className="mb-2">
          <Link href={`/project?id=${id}`} className="inline-flex items-center gap-1 text-xs font-semibold text-sea-700 hover:text-sea-800 transition">
            <span aria-hidden="true">&larr;</span> Back to Project Workspace
          </Link>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
              BA Requirements Studio
            </h1>
            <p className="mt-1 text-xs text-slate-500">
              Autonomous Business Analyst turning stakeholder meetings into verifiable specifications
            </p>
          </div>
          <div className="flex items-center gap-2">
            {session && (
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                Round {session.round + 1} of {session.max_rounds}
              </span>
            )}
            <Badge tone={isReady ? "green" : "blue"}>
              {isReady ? "Ready (≥90 Scored)" : "Clarification Needed"}
            </Badge>
          </div>
        </div>

        {actionError && (
          <div role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-900">
            {actionError}
          </div>
        )}

        {/* Primary Action Controls */}
        <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4">
          {isReady ? (
            <button
              disabled={busy !== null}
              onClick={() => void generateBRD()}
              className="rounded-xl bg-gradient-to-r from-emerald-600 to-teal-700 px-5 py-2.5 text-xs font-bold text-white shadow-sm transition hover:from-emerald-700 hover:to-teal-800 disabled:opacity-60"
            >
              {busy === "generate" ? "Generating BRD..." : "✓ Generate Business Requirements Document (BRD)"}
            </button>
          ) : ba.can_run ? (
            <button
              disabled={busy !== null}
              onClick={() => void runRound()}
              className="rounded-xl bg-gradient-to-r from-sea-600 to-sea-700 px-5 py-2.5 text-xs font-bold text-white shadow-sm transition hover:from-sea-700 hover:to-sea-800 disabled:opacity-60"
            >
              {busy === "run" ? "Analyzing Requirements..." : "Analyze & Run Next BA Round"}
            </button>
          ) : null}

          <button
            onClick={() => setShowTranscript((v) => !v)}
            className="rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
          >
            {showTranscript ? "Hide Meeting Transcript" : "View Source Transcript"}
          </button>
        </div>
      </div>

      {/* Transcript Viewer Accordion */}
      {showTranscript && (
        <section aria-label="Meeting Transcript" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
          <h2 className="text-sm font-bold text-slate-900 mb-3">
            Source Meeting Transcript: {transcriptData?.transcript.source_name ?? "transcript.txt"}
          </h2>
          <div className="max-h-72 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50/70 p-4 font-mono text-xs text-slate-700 space-y-1">
            {transcriptData?.transcript.lines ? (
              transcriptData.transcript.lines.map((l) => (
                <div key={l.line_no} className="flex gap-4">
                  <span className="w-8 text-right text-slate-400 select-none">{l.line_no}</span>
                  <span>{l.text}</span>
                </div>
              ))
            ) : (
              <p className="text-slate-500 font-sans">Loading transcript lines...</p>
            )}
          </div>
        </section>
      )}

      {/* Score Gauge & Gates Banner */}
      <div className="grid gap-6 md:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-xs font-semibold text-slate-500 uppercase tracking-wider">
              <span>BRD Quality Score</span>
              <span>Target: 90/100</span>
            </div>
            <div className="mt-4 flex items-baseline gap-2">
              <span className={`text-5xl font-black tracking-tight ${isReady ? "text-emerald-600" : "text-sea-600"}`}>
                {currentScore}
              </span>
              <span className="text-sm font-bold text-slate-400">/ 100</span>
            </div>
            <p className="mt-2 text-xs text-slate-500 leading-relaxed">
              {isReady
                ? "Quality threshold reached! All core gates passed. You can now generate the binding BRD."
                : `Score is ${currentScore}/100. Answer the clarification questions below to reach the ≥90 requirement.`}
            </p>
          </div>

          {/* History Sparkline */}
          {ba.history.length > 0 && (
            <div className="mt-4 border-t border-slate-100 pt-3">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Score History:</span>
              <div className="mt-1 flex items-center gap-2 text-xs font-semibold">
                {ba.history.map((h, i) => (
                  <span key={h.round} className="inline-flex items-center gap-1">
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-700">R{h.round}: {h.total}</span>
                    {i < ba.history.length - 1 && <span className="text-slate-300">&rarr;</span>}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Gate Checks */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs md:col-span-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
            Core Readiness Gates (Must All Pass)
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {score?.gates ? (
              score.gates.map((g) => (
                <div key={g.id} className={`rounded-xl border p-3 ${g.passed ? "border-emerald-200 bg-emerald-50/60" : "border-amber-200 bg-amber-50/60"}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[11px] font-bold text-slate-600">{g.id}</span>
                    <span className={`text-xs font-bold ${g.passed ? "text-emerald-700" : "text-amber-700"}`}>
                      {g.passed ? "✓ PASS" : "PENDING"}
                    </span>
                  </div>
                  <p className="mt-1 text-xs font-semibold text-slate-800 line-clamp-1">{g.name}</p>
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-500 col-span-4">No gate data available yet.</p>
            )}
          </div>

          {/* Conflicts Card if any */}
          {score?.conflicts && score.conflicts.length > 0 && (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/70 p-3.5 text-xs">
              <span className="font-bold text-amber-900 uppercase tracking-wide">Stakeholder Conflicts:</span>
              <ul className="mt-1 space-y-1 text-amber-800">
                {score.conflicts.map((c, i) => (
                  <li key={i}>
                    <strong>{c.topic}:</strong> {c.resolved ? `Resolved (${c.resolution})` : "Unresolved — clarification needed"}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* 10 Dimension Coverage Bars */}
      <section aria-label="Dimension Coverage" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs">
        <h2 className="text-sm font-bold text-slate-900 mb-4 border-b border-slate-100 pb-3">
          10-Dimension Evaluation Breakdown
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {score?.dimensions.map((d) => {
            const pct = Math.round(d.coverage * 100);
            return (
              <div key={d.dimension} className="rounded-xl border border-slate-100 bg-slate-50/70 p-3.5 space-y-2">
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className="text-slate-800">{d.dimension}: {d.name}</span>
                  <span className={`font-mono font-bold ${pct >= 75 ? "text-emerald-700" : pct >= 50 ? "text-sea-700" : "text-amber-700"}`}>
                    {pct}%
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
                  <div
                    className={`h-full transition-all ${pct >= 75 ? "bg-emerald-500" : pct >= 50 ? "bg-sea-500" : "bg-amber-500"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">{d.justification}</p>
                {d.source_refs.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {d.source_refs.map((ref, idx) => (
                      <span key={idx} className="rounded bg-slate-200/80 px-1.5 py-0.5 text-[10px] font-mono text-slate-700">
                        {ref}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Clarification Questions */}
      <section aria-label="Clarification Questions" className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs">
        <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
          <div>
            <h2 className="text-base font-bold text-slate-900">Clarification Questions</h2>
            <p className="text-xs text-slate-500">Addressed to specific project members to close requirements gaps</p>
          </div>
          <span className="text-xs font-semibold text-slate-600">
            {ba.questions.filter((q) => q.status === "OPEN").length} Open
          </span>
        </div>

        {ba.questions.length === 0 ? (
          <Empty title="No questions pending">All required details are clarified or ready for review.</Empty>
        ) : (
          <div className="space-y-4">
            {ba.questions.map((q) => (
              <div key={q.id} className={`rounded-xl border p-4 transition ${q.status === "OPEN" ? "border-slate-300 bg-white" : "border-slate-100 bg-slate-50/50"}`}>
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-sea-50 px-2 py-0.5 text-xs font-bold text-sea-700">
                      {q.dimension_name || q.dimension}
                    </span>
                    <span className="text-xs text-slate-500">Round {q.round + 1}</span>
                  </div>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${q.status === "OPEN" ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
                    {q.status}
                  </span>
                </div>

                <h3 className="text-sm font-bold text-slate-900">{q.question}</h3>
                <p className="mt-1 text-xs text-slate-500 leading-relaxed">Rationale: {q.rationale}</p>

                {/* Answers already provided */}
                {q.answers.length > 0 && (
                  <div className="mt-3 space-y-1.5 border-t border-slate-100 pt-2.5">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Answers:</span>
                    {q.answers.map((a) => (
                      <div key={a.id} className="rounded-lg bg-slate-50 p-2.5 text-xs">
                        <span className="font-bold text-slate-800">{a.member_name}: </span>
                        <span className="text-slate-700">{a.answer_text}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Answer form if authorized */}
                {q.can_answer && (
                  <div className="mt-4 border-t border-slate-100 pt-3 space-y-3">
                    <span className="text-xs font-bold text-slate-700">Your Response:</span>

                    {/* Suggested option chips */}
                    {q.suggested_options && q.suggested_options.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {q.suggested_options.map((opt) => (
                          <button
                            key={opt}
                            type="button"
                            onClick={() => setSelectedOptions((prev) => ({ ...prev, [q.id]: opt }))}
                            className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                              selectedOptions[q.id] === opt
                                ? "border-sea-600 bg-sea-50 text-sea-800"
                                : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"
                            }`}
                          >
                            {opt}
                          </button>
                        ))}
                      </div>
                    )}

                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="Type answer or select above..."
                        value={customAnswers[q.id] ?? selectedOptions[q.id] ?? ""}
                        onChange={(e) => setCustomAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                        className="flex-1 rounded-xl border border-slate-300 px-3 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:border-sea-500 focus:outline-none"
                      />
                      <button
                        disabled={busy !== null}
                        onClick={() => void submitAnswer(q)}
                        className="rounded-xl bg-sea-600 px-4 py-2 text-xs font-bold text-white hover:bg-sea-700 disabled:opacity-60 transition"
                      >
                        {busy === `answer-${q.id}` ? "Saving..." : "Submit Answer"}
                      </button>
                      <button
                        disabled={busy !== null}
                        onClick={() => void skipQuestion(q.id)}
                        className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-60 transition"
                      >
                        Skip
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function FromQuery() {
  const raw = useSearchParams().get("id");
  const id = raw !== null && /^\d{1,9}$/.test(raw) ? Number(raw) : null;
  if (id === null) {
    return (
      <Empty title="No project selected">
        Open a project from <Link href="/" className="text-sea-700 underline">the project list</Link>.
      </Empty>
    );
  }
  return <BAStudioView id={id} />;
}

export default function BAPage() {
  return (
    <Suspense fallback={<Loading what="Loading BA Studio" />}>
      <FromQuery />
    </Suspense>
  );
}
