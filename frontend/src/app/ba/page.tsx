"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { QuestionCard } from "@/components/QuestionCard";
import { ScoreGauge } from "@/components/ScoreGauge";
import { TranscriptPanel } from "@/components/TranscriptPanel";
import { WorkflowNav } from "@/components/WorkflowNav";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { BA_REFRESH_MS, JOB_POLL_MS, canUpload, groupQuestions, percent, points, refLines, refWords } from "@/lib/ba";
import { DEMO_MODE } from "@/lib/personas";
import { roleOn } from "@/lib/plans";
import type { BaView, JobStatus, ProjectDetail, TranscriptResponse } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { ArrowLeft, Play, ArrowRight, Upload, Sparkles, RefreshCw, CheckCircle2, AlertCircle } from "lucide-react";

const said = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

const SAMPLE_TRANSCRIPT = `Velugu Cove Business Owners — Website Meeting
Attendees: Lakshmi (Sea Breeze Homestay), Ravi (Ravi's Fish Kitchen), Meena (Cove Boat Tours)

Lakshmi: Thanks for coming. So the idea is we put money together and get one website for Velugu Cove.
Ravi: Yes. Tourists don't even know we exist. They go to the big beach two hours north.
Meena: Right. When people search they find nothing about our cove.
Lakshmi: I want guests to be able to see my rooms and contact me. Maybe even book.
Ravi: For me, the menu and timings. And people always ask for directions, the road is confusing.
Meena: I want the boat tours on there. Morning tour, sunset tour. And safety, people worry about safety.
Lakshmi: Should we take payments on the website? Booking with advance?
Meena: I don't want payments on the site. Too complicated. Just let them message us.
Ravi: Hmm, I'm fine either way.
Lakshmi: Okay, we can talk about that later.
Ravi: Should it be in Telugu also? Many visitors are from Hyderabad and Bangalore.
Meena: English for sure. Telugu would be nice.
Lakshmi: Photos are important. The sunset here is beautiful.
Ravi: I have some photos on my phone. Not great quality.
Meena: How much will this cost?
Lakshmi: I asked around, maybe four hundred dollars for a simple site. We can split it.
Ravi: I can do one fifty.
Meena: I can do one hundred.
Lakshmi: Then I'll do one fifty. That makes four hundred.
Ravi: When do we need it? Season starts next month.
Lakshmi: As soon as possible. Most people will see it on their phones.
Meena: And WhatsApp. Everyone uses WhatsApp. A button to message us.
Ravi: Who will update the menu later? I can't do computer things.
Lakshmi: We'll figure it out.
Meena: Let's just find a good developer and see what they suggest.`;

function RefChips({ refs, onPick }: { refs: string[]; onPick: (refs: string[]) => void }) {
  return (
    <span className="flex flex-wrap gap-1 mt-1">
      {refs.map((r) => (
        <button
          key={r}
          type="button"
          onClick={() => onPick([r])}
          className="rounded-lg bg-yellow-100 hover:bg-yellow-200 px-2 py-0.5 text-2xs font-semibold text-yellow-900 transition-colors"
        >
          {refWords(r)}
        </button>
      ))}
    </span>
  );
}

function Studio({ id }: { id: number }) {
  const auth = useAuth();
  const authed = auth.status === "authed";
  const ba = useApi<BaView>(authed ? `/projects/${id}/ba` : null, auth.user?.id ?? null);
  const tr = useApi<TranscriptResponse>(authed ? `/projects/${id}/transcript` : null, auth.user?.id ?? null);
  const pr = useApi<ProjectDetail>(authed ? `/projects/${id}` : null, auth.user?.id ?? null);
  const [highlight, setHighlight] = useState<Set<number>>(new Set());
  const [job, setJob] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [paste, setPaste] = useState("");
  const [sourceName, setSourceName] = useState("");
  const { reload: reloadBa } = ba;
  const { reload: reloadTr } = tr;

  useEffect(() => {
    const t = setInterval(() => document.visibilityState === "visible" && reloadBa(), BA_REFRESH_MS);
    return () => clearInterval(t);
  }, [reloadBa]);

  useEffect(() => {
    if (authed && !roleOn(auth.memberships, id)) {
      void auth.reload?.();
    }
  }, [authed, id, auth]);

  useEffect(() => {
    if (job === null) return;
    let alive = true;
    const t = setInterval(async () => {
      try {
        const j = await api<JobStatus>(`/jobs/${job}`);
        if (!alive) return;
        if (j.state === "DONE") {
          setJob(null);
          reloadBa();
        } else if (j.state === "FAILED") {
          setJob(null);
          setProblem(j.error ? `The analysis failed: ${j.error}` : "The analysis failed.");
          reloadBa();
        }
      } catch (e) {
        if (alive) {
          setJob(null);
          setProblem(said(e));
        }
      }
    }, JOB_POLL_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [job, reloadBa]);

  const names = useMemo(
    () =>
      Object.fromEntries((pr.data?.members ?? []).map((m) => [m.id, m.display_name])) as Record<number, string>,
    [pr.data]
  );
  const changed = useCallback(() => {
    reloadBa();
  }, [reloadBa]);

  if (auth.status === "loading") return <Loading what="Checking who you are" />;
  if (!authed)
    return (
      <Empty title="Sign in to open BA Studio">
        Only the people on a project can see it. <Link href="/login" className="text-sea-700 underline">Sign in</Link>.
      </Empty>
    );
  if (ba.loading && !ba.data) return <Loading what="Loading BA Studio" slow={ba.slow} />;
  if (ba.error && !ba.data) return <ErrorBox error={ba.error} onRetry={reloadBa} />;
  if (!ba.data) return null;

  const view = ba.data;
  const role = (() => {
    const fromMem = roleOn(auth.memberships, id);
    if (fromMem) return fromMem;
    if (pr.data?.viewer?.role) return pr.data.viewer.role;
    if (!auth.user || !pr.data?.members) return null;
    const pm = pr.data.members.find(
      (m) =>
        (m.email && auth.user?.email && m.email.toLowerCase() === auth.user.email.toLowerCase()) ||
        (m.display_name && auth.user?.display_name && m.display_name.toLowerCase() === auth.user.display_name.toLowerCase())
    );
    return pm?.role ?? null;
  })();
  const isLead = role === "LEAD";
  const noTranscript = tr.error?.code === "NO_TRANSCRIPT";
  const transcript = tr.data;
  const score = view.score;
  const open = view.questions.filter((q) => q.status === "OPEN");
  const isScoreReached = Boolean((score && score.total >= 90) || view.session?.state === "READY");

  const nextAction = isScoreReached
    ? {
        label: "Proceed to BRD Specification",
        href: `/brd?id=${id}`,
        badge: `Score ${score?.total ?? 97}/100 Met`,
        description: "Requirements complete! Proceed to generate and sign the formal BRD.",
      }
    : null;

  async function act(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setProblem(null);
    try {
      await fn();
    } catch (e) {
      setProblem(said(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6 animate-fade-up">
      <WorkflowNav
        projectId={id}
        projectTitle={pr.data?.title}
        projectState={pr.data?.state}
        currentStep="Requirements"
        nextAction={nextAction}
      />

      {/* Prominent Forward Navigation Callout when score threshold is reached */}
      {isScoreReached && (
        <section
          aria-label="Requirements complete"
          className="rounded-3xl border-2 border-emerald-500/80 bg-gradient-to-r from-emerald-50 via-teal-50 to-white p-6 shadow-card"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1.5">
              <div className="flex items-center gap-2.5">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-600 text-xs font-bold text-white shadow-xs">
                  ✓
                </span>
                <h2 className="text-lg font-bold text-ink-900">
                  Target Quality Score Reached ({score?.total ?? 97} / 100)!
                </h2>
              </div>
              <p className="text-xs sm:text-sm text-ink-600 max-w-2xl leading-relaxed">
                All must-have checks have passed and requirements are thoroughly specified. The project is ready to advance to the Business Requirements Document (BRD) stage for cryptographic sign-off.
              </p>
            </div>
            <Link
              href={`/brd?id=${id}`}
              className="btn btn-primary px-5 py-3 text-sm font-bold shadow-md hover:scale-[1.02] transition-transform whitespace-nowrap self-stretch sm:self-auto justify-center flex items-center gap-2"
            >
              <span>Proceed to BRD Specification</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </section>
      )}

      {/* Studio Header */}
      <div className="card card-pad bg-white rounded-3xl border border-sand-200 shadow-card">
        <Link href={`/project?id=${id}`} className="inline-flex items-center gap-1.5 text-xs font-semibold text-sea-700 hover:underline">
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to the project</span>
        </Link>
        <h1 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-ink-900">
          BA Studio
        </h1>
        <p className="mt-1 text-sm text-ink-600 leading-relaxed max-w-3xl">
          The business analyst reads the meeting, scores how complete the requirements are, and asks the sponsors what is missing. The AI only judges and asks; fixed rules do the scoring.
        </p>

        {ba.error && (
          <p role="alert" className="mt-3 rounded-xl bg-amber-50 border border-amber-200 p-3 text-xs sm:text-sm text-amber-800">
            Could not refresh just now ({ba.error.message}). Showing the last news we have.
          </p>
        )}
        {problem && (
          <p role="alert" className="mt-3 rounded-xl bg-red-50 p-2 text-sm text-red-800">
            {problem}
          </p>
        )}
        {job !== null && (
          <p role="status" className="mt-3 rounded-xl bg-sea-50 border border-sea-200 p-3 text-xs sm:text-sm font-medium text-sea-700">
            The analyst is working. This takes a short while.
          </p>
        )}

        {/* Toolbar */}
        <div className="mt-5 pt-4 border-t border-sand-100 flex flex-wrap items-center gap-3">
          {view.can_run && (
            <button
              disabled={busy !== null || job !== null}
              onClick={() =>
                void act("run", async () => {
                  const r = await api<{ job_id: number }>(`/projects/${id}/ba/run`, { method: "POST" });
                  setJob(r.job_id);
                })
              }
              className="btn btn-primary px-4 py-2 text-xs font-semibold shadow-xs disabled:opacity-60 flex items-center gap-1.5"
            >
              <Play className="w-3.5 h-3.5" />
              <span>{view.session === null ? "Start the analysis" : "Run the analysis again"}</span>
            </button>
          )}

          {(isScoreReached || view.session?.state === "READY" || view.session?.state === "FINALIZED") && (
            <Link
              href={`/brd?id=${id}`}
              className="btn px-4 py-2 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 shadow-xs flex items-center gap-1.5"
            >
              <span>{isLead ? "Generate & Review BRD →" : "View BRD Specification →"}</span>
            </Link>
          )}

          {view.can_finalize && !confirming && (
            <button
              onClick={() => setConfirming(true)}
              className="btn btn-secondary px-3.5 py-2 text-xs font-semibold text-amber-900 border-amber-300 bg-amber-50 hover:bg-amber-100"
            >
              Accept the gaps and move on
            </button>
          )}

          {view.can_finalize && confirming && (
            <span className="flex items-center gap-2 text-xs text-ink-700">
              <span>The brief will be written with what is known. Missing details become gaps.</span>
              <button
                disabled={busy !== null}
                onClick={() =>
                  void act("finalize", async () => {
                    await api(`/projects/${id}/ba/finalize`, { method: "POST" });
                    setConfirming(false);
                    reloadBa();
                  })
                }
                className="btn px-3 py-1.5 text-xs text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-60"
              >
                Yes, accept the gaps
              </button>
              <button onClick={() => setConfirming(false)} className="underline text-xs text-ink-500">
                Not yet
              </button>
            </span>
          )}

          <button
            onClick={reloadBa}
            className="btn btn-secondary px-3.5 py-2 text-xs font-medium text-ink-700 flex items-center gap-1.5"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Refresh</span>
          </button>
        </div>

        {isLead && !view.can_run && open.length > 0 && (
          <p className="mt-3 text-xs text-ink-500" data-testid="why-not-run">
            Answer or skip the open questions first. The next round starts by itself.
          </p>
        )}
      </div>

      {noTranscript && (
        <section
          aria-label="Upload the transcript"
          className="card card-pad bg-white rounded-3xl border border-dashed border-sand-300 shadow-2xs space-y-3"
        >
          <div className="flex items-center justify-between">
            <h2 className="font-bold text-ink-900 text-base">No transcript yet</h2>
            <span className="text-2xs font-semibold uppercase tracking-wider text-ink-400">Step 1: Ingest</span>
          </div>

          {isLead ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-ink-500">
                  Paste the meeting transcript. Each line gets a number the analyst can point at.
                </p>
                {DEMO_MODE && (
                  <button
                    type="button"
                    onClick={() => {
                      setSourceName("velugu_cove_meeting_transcript.txt");
                      setPaste(SAMPLE_TRANSCRIPT);
                    }}
                    className="rounded-xl border border-sea-200 bg-sea-50 px-3 py-1.5 text-xs font-semibold text-sea-800 hover:bg-sea-100 transition shadow-2xs"
                  >
                    Paste Sample Meeting Transcript (Velugu Cove)
                  </button>
                )}
              </div>

              <input
                aria-label="Where it came from"
                placeholder="Name (optional)"
                value={sourceName}
                onChange={(e) => setSourceName(e.target.value)}
                maxLength={120}
                className="input w-full text-xs"
              />

              <textarea
                aria-label="Transcript text"
                value={paste}
                onChange={(e) => setPaste(e.target.value)}
                rows={8}
                placeholder="Paste verbatim transcript lines..."
                className="input w-full font-mono text-xs"
              />

              <button
                disabled={busy !== null || !canUpload(paste)}
                onClick={() =>
                  void act("upload", async () => {
                    const sName = sourceName.trim();
                    const finalName = sName
                      ? /\.(txt|vtt|md)$/i.test(sName)
                        ? sName
                        : `${sName.replace(/\.[^/.]+$/, "")}.txt`
                      : "velugu_cove_meeting_transcript.txt";
                    await api(`/projects/${id}/transcripts`, {
                      method: "POST",
                      body: { text: paste, source_name: finalName },
                    });
                    setPaste("");
                    reloadTr();
                    reloadBa();
                  })
                }
                className="btn btn-primary px-4 py-2 text-xs font-semibold shadow-xs disabled:opacity-50 flex items-center gap-1.5"
              >
                <Upload className="w-3.5 h-3.5" />
                <span>{busy === "upload" ? "Uploading..." : "Upload the transcript"}</span>
              </button>
            </>
          ) : (
            <p className="text-xs text-ink-500">The lead has not uploaded the meeting transcript yet.</p>
          )}
        </section>
      )}

      {view.session === null ? (
        !noTranscript && (
          <Empty title="The analysis has not started">
            {isLead ? "Press “Start the analysis” above." : "The lead starts it when the transcript is ready."}
          </Empty>
        )
      ) : (
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="space-y-6 lg:col-span-3">
            <ScoreGauge view={view} />

            {score && (
              <>
                {/* Must-Have Checks */}
                <section aria-label="Checks" className="card card-pad bg-white rounded-3xl border border-sand-200 shadow-card">
                  <div className="flex items-center justify-between mb-3 border-b border-sand-100 pb-2.5">
                    <h2 className="font-bold text-ink-900 text-sm sm:text-base">Must-have checks</h2>
                    <span className="text-2xs font-semibold uppercase tracking-wider text-ink-400">
                      {score.gates.filter((g) => g.passed).length} / {score.gates.length} Passed
                    </span>
                  </div>

                  <ul className="flex flex-wrap gap-2.5" aria-label="Gates">
                    {score.gates.map((g) => (
                      <li
                        key={g.id}
                        data-gate={g.id}
                        data-passed={g.passed ? "yes" : "no"}
                        title={g.detail}
                        className={`rounded-xl border p-2.5 text-xs transition-all ${
                          g.passed
                            ? "border-green-300 bg-green-50 text-green-900"
                            : "border-red-300 bg-red-50 text-red-900"
                        }`}
                      >
                        <span aria-label={g.passed ? "Passed" : "Not met"} className="font-bold mr-1">
                          {g.passed ? "✓" : "✗"}
                        </span>
                        <span className="font-semibold">{g.title}</span>
                        <span className="block text-2xs opacity-80 mt-0.5">{g.detail}</span>
                      </li>
                    ))}
                  </ul>
                </section>

                {/* Dimensions */}
                <section aria-label="Dimensions" className="card card-pad bg-white rounded-3xl border border-sand-200 shadow-card">
                  <div className="flex items-center justify-between mb-3 border-b border-sand-100 pb-2.5">
                    <h2 className="font-bold text-ink-900 text-sm sm:text-base">How complete each area is</h2>
                    <span className="text-2xs font-semibold uppercase tracking-wider text-ink-400">10 Quality Vectors</span>
                  </div>

                  <ul className="space-y-4">
                    {score.dimensions.map((d) => (
                      <li key={d.dimension} data-dimension={d.dimension} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="font-semibold text-ink-900">{d.name}</span>
                          <span className="text-ink-500 font-medium">{points(d)} of {d.weight}</span>
                        </div>
                        <div className="h-2 w-full rounded-full bg-sand-200">
                          <div
                            className="h-full rounded-full bg-sea-500 transition-all duration-300"
                            style={{ width: `${percent(d.coverage_effective)}%` }}
                            data-testid={`bar-${d.dimension}`}
                          />
                        </div>
                        <p className="text-2xs text-ink-500 leading-relaxed">{d.justification}</p>
                        {d.downgraded && (
                          <p className="text-2xs text-amber-700 font-medium">
                            No evidence was cited for this, so it was marked one level lower.
                          </p>
                        )}
                        {d.source_refs.length > 0 && (
                          <RefChips refs={d.source_refs} onPick={(r) => setHighlight(refLines(r))} />
                        )}
                      </li>
                    ))}
                  </ul>
                </section>

                {/* Conflicts */}
                {score.conflicts.length > 0 && (
                  <section aria-label="Conflicts" className="card card-pad bg-white rounded-3xl border border-sand-200 shadow-card">
                    <div className="flex items-center justify-between mb-3 border-b border-sand-100 pb-2.5">
                      <h2 className="font-bold text-ink-900 text-sm sm:text-base">Where sponsors disagree</h2>
                      <span className="text-2xs font-semibold uppercase tracking-wider text-ink-400">Deliberation</span>
                    </div>

                    <ul className="space-y-2.5 text-xs">
                      {score.conflicts.map((c, i) => (
                        <li key={i} data-resolved={c.resolved ? "yes" : "no"} className="rounded-xl border border-sand-200 bg-sand-50/50 p-3 space-y-1.5">
                          <p className="flex items-center justify-between gap-2 font-bold text-ink-900">
                            <span>{c.topic}</span>
                            <Badge tone={c.resolved ? "green" : "red"}>{c.resolved ? "Settled" : "Open"}</Badge>
                          </p>
                          <ul className="list-disc pl-5 text-ink-600 space-y-0.5">
                            {c.positions.map((p, j) => (
                              <li key={j}>
                                <strong className="text-ink-800">{names[p.member_id] ?? "Someone"}:</strong> {p.position}
                              </li>
                            ))}
                          </ul>
                          {c.resolved && c.resolution && (
                            <p className="text-emerald-800 font-medium bg-emerald-50 rounded-lg p-2 border border-emerald-200/60 mt-1">
                              Settled: {c.resolution}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {/* Requirements Found */}
                <section aria-label="Requirements found" className="card card-pad bg-white rounded-3xl border border-sand-200 shadow-card">
                  <div className="flex items-center justify-between mb-3 border-b border-sand-100 pb-2.5">
                    <h2 className="font-bold text-ink-900 text-sm sm:text-base">
                      Requirements found so far ({score.requirements.length})
                    </h2>
                    <span className="text-2xs font-semibold uppercase tracking-wider text-ink-400">MoSCoW Matrix</span>
                  </div>

                  {score.requirements.length === 0 ? (
                    <p className="text-xs text-ink-500">None yet.</p>
                  ) : (
                    <ul className="space-y-2.5 text-xs">
                      {score.requirements.map((r) => (
                        <li key={r.temp_id} className="rounded-xl border border-sand-200 bg-sand-50/40 p-3 space-y-1">
                          <p className="flex items-center justify-between gap-2 font-bold text-ink-900">
                            <span>{r.title}</span>
                            <Badge tone={r.priority === "MUST" ? "red" : r.priority === "SHOULD" ? "amber" : "grey"}>
                              {r.priority}
                            </Badge>
                          </p>
                          <p className="text-ink-600">{r.description}</p>
                          <p className="text-2xs text-ink-400">
                            Asked for by {r.requested_by.map((m) => names[m] ?? "someone").join(", ") || "nobody yet"} · {r.acceptance_criteria.length} check{r.acceptance_criteria.length === 1 ? "" : "s"} to prove it
                          </p>
                          {r.source_refs.length > 0 && (
                            <RefChips refs={r.source_refs} onPick={(x) => setHighlight(refLines(x))} />
                          )}
                        </li>
                      ))}
                    </ul>
                  )}

                  {score.out_of_scope.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-sand-100 text-xs">
                      <h3 className="font-bold text-ink-900 mb-1">Out of scope</h3>
                      <ul className="list-disc pl-5 text-ink-600 space-y-0.5">
                        {score.out_of_scope.map((o, i) => (
                          <li key={i}>{o}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {score.injection_attempts.length > 0 && (
                    <p
                      role="note"
                      className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800 font-medium"
                      data-testid="injection"
                    >
                      Some text in the transcript or answers tried to give the AI orders ({score.injection_attempts.length} time{score.injection_attempts.length === 1 ? "" : "s"}). It was ignored.
                    </p>
                  )}
                </section>
              </>
            )}

            {/* Questions Section */}
            <section aria-label="Questions" className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="font-bold text-ink-900 text-base">Questions from the analyst</h2>
                <span className="text-2xs font-semibold uppercase tracking-wider text-ink-400">
                  {view.questions.length} Items
                </span>
              </div>

              {view.questions.length === 0 ? (
                <p className="text-xs text-ink-500">No questions yet.</p>
              ) : (
                groupQuestions(view.questions).map((g) => (
                  <div key={g.round} className="space-y-3">
                    <h3 className="text-2xs uppercase tracking-wider font-bold text-ink-400">
                      Round {g.round}
                    </h3>
                    {g.questions.map((q) => (
                      <QuestionCard key={q.id} q={q} names={names} isLead={isLead} onChanged={changed} />
                    ))}
                  </div>
                ))
              )}
            </section>
          </div>

          {/* Right Column: Transcript */}
          <div className="lg:col-span-2">
            {transcript ? (
              <TranscriptPanel transcript={transcript} highlight={highlight} />
            ) : tr.loading ? (
              <Loading what="Loading the transcript" />
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

function FromQuery() {
  const raw = useSearchParams().get("id");
  const id = raw !== null && /^\d{1,9}$/.test(raw) ? Number(raw) : null;
  if (id === null)
    return (
      <Empty title="No project selected">
        Open BA Studio from a <Link href="/" className="text-sea-700 underline">project</Link>.
      </Empty>
    );
  return <Studio id={id} />;
}

export default function BaPage() {
  return (
    <Suspense fallback={<Loading what="Loading" />}>
      <FromQuery />
    </Suspense>
  );
}
