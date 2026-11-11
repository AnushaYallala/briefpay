"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, useMemo, useEffect } from "react";
import type { ColDef } from "ag-grid-community";
import { BrdDocumentBook } from "@/components/BrdDocumentBook";
import { WorkflowNav } from "@/components/WorkflowNav";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { api, apiPost, API_BASE } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { BRDResponse, BRDRequirementItem, JobStatus, ProjectDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { brdIsOpen, brdStatus, leadName } from "@/lib/verifyview";
import { FileText, Download, CheckCircle2, XCircle, ArrowRight, ShieldCheck, Sparkles } from "lucide-react";

function BRDView({ id }: { id: number }) {
  const auth = useAuth();
  const [refreshKey, setRefreshKey] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [selectedReq, setSelectedReq] = useState<BRDRequirementItem | null>(null);
  const [genJob, setGenJob] = useState<number | null>(null);
  const [genError, setGenError] = useState<string | null>(null);

  const { data: project } = useApi<ProjectDetail>(
    auth.status === "loading" ? null : `/projects/${id}`,
    auth.user?.id ?? null
  );
  const { data: brd, error, loading, slow, reload } = useApi<BRDResponse>(
    auth.status === "loading" ? null : `/projects/${id}/brd`,
    `${auth.user?.id ?? "anon"}-${refreshKey}`
  );

  useEffect(() => {
    if (genJob === null) return;
    let alive = true;
    const t = setInterval(async () => {
      try {
        const j = await api<JobStatus>(`/jobs/${genJob}`);
        if (!alive) return;
        if (j.state === "DONE") {
          setGenJob(null);
          setRefreshKey((k) => k + 1);
          reload();
        } else if (j.state === "FAILED") {
          setGenJob(null);
          const rawErr = j.error || "";
          let cleanErr = "Generation failed. Please try again.";
          if (rawErr.includes("getaddrinfo") || rawErr.includes("ConnectError")) {
            cleanErr = "Network connection error: Could not reach the AI provider API. Please check your internet connection.";
          } else if (rawErr.includes("503") || rawErr.includes("UNAVAILABLE") || rawErr.includes("high demand")) {
            cleanErr = "The AI provider is temporarily experiencing high traffic (503). Spikes are temporary—please wait 1-2 minutes and try again.";
          } else if (rawErr.includes("429") || rawErr.includes("quota")) {
            cleanErr = "AI provider rate limit reached. Please wait a moment and try again.";
          } else if (j.error) {
            cleanErr = `Generation failed: ${j.error.replace(/^BRDError:\s*/, "").replace(/^The BRD Generator could not produce a valid draft:\s*/, "")}`;
          }
          setGenError(cleanErr);
        }
      } catch (e) {
        if (alive) {
          setGenJob(null);
          setGenError(e instanceof Error ? e.message : "Failed checking job status");
        }
      }
    }, 2000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [genJob, reload]);

  async function generateBRD() {
    setGenError(null);
    setBusy("generate");
    try {
      const res = await api<{ job_id: number }>(`/projects/${id}/brd/generate`, { method: "POST" });
      setGenJob(res.job_id);
    } catch (e) {
      setGenError(e instanceof Error ? e.message : "Failed to start BRD generation");
    } finally {
      setBusy(null);
    }
  }

  async function submitDecision(decision: "APPROVE" | "REJECT") {
    if (!brd) return;
    setBusy(decision);
    setActionError(null);
    try {
      await apiPost(`/projects/${id}/brd/${brd.version}/decision`, {
        decision,
        brd_sha256: brd.sha256,
        comment: comment.trim() || null,
      });
      setComment("");
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not submit decision");
    } finally {
      setBusy(null);
    }
  }

  const columns = useMemo<ColDef<BRDRequirementItem>[]>(
    () => [
      { field: "code", headerName: "Code", width: 110, pinned: "left", sort: "asc" },
      { field: "title", headerName: "Requirement Title", flex: 1, minWidth: 200 },
      {
        field: "priority",
        headerName: "Priority",
        width: 110,
        cellClass: (p) =>
          p.value === "MUST"
            ? "font-bold text-red-700"
            : p.value === "SHOULD"
            ? "font-semibold text-sea-700"
            : "text-ink-500",
      },
      {
        headerName: "Criteria",
        width: 110,
        valueGetter: (p) => `${p.data?.acceptance_criteria?.length ?? 0} ACs`,
      },
      { field: "weight", headerName: "Weight", width: 90 },
    ],
    []
  );

  // who the signed-in person is on THIS project comes from their memberships, never from matching names
  const mine = auth.memberships.find((m) => m.project_id === id);
  const userMembership = mine ? { id: mine.member_id, role: mine.role } : undefined;
  const isLead = userMembership?.role === "LEAD";
  const isSponsor = isLead || userMembership?.role === "SPONSOR";

  if (auth.status === "loading" || loading) return <Loading what="Loading BRD" slow={slow} />;

  if (error && error.code === "NO_BRD") {
    return (
      <div className="space-y-6 animate-fade-up">
        <WorkflowNav
          projectId={id}
          projectTitle={project?.title}
          projectState={project?.state}
          currentStep="Brief"
          nextAction={{
            label: "Review in BA Studio",
            href: `/ba?id=${id}`,
            description: "Review meeting notes and scoring in BA Studio.",
          }}
        />

        <div className="card card-pad bg-white rounded-3xl border border-sand-200 shadow-card text-center max-w-2xl mx-auto space-y-4">
          <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-sea-50 text-sea-700 text-2xl font-bold shadow-xs">
            <FileText className="w-6 h-6 text-sea-600" />
          </div>
          <h1 className="text-2xl font-bold text-ink-900">
            Generate Business Requirements Document (BRD)
          </h1>
          <p className="text-sm text-ink-600 leading-relaxed">
            The business requirements have been analyzed and reached the target quality score. You can now generate the official, immutable specification with REQ codes and acceptance criteria.
          </p>

          {genError && (
            <div role="alert" className="rounded-xl border border-coral-200 bg-coral-50 p-3 text-xs font-semibold text-coral-900 text-left">
              {genError}
            </div>
          )}

          {genJob !== null ? (
            <div className="rounded-xl border border-sea-200 bg-sea-50/70 p-4 text-xs font-semibold text-sea-800 flex items-center justify-center gap-2">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-sea-600 border-t-transparent" />
              <span>Gemini AI is writing and hashing the BRD specification...</span>
            </div>
          ) : isLead ? (
            <div className="pt-2">
              <button
                disabled={busy !== null}
                onClick={() => void generateBRD()}
                className="btn btn-primary px-6 py-3 text-sm font-bold shadow-md hover:scale-[1.02] transition-transform disabled:opacity-60 flex items-center gap-2 mx-auto"
              >
                <Sparkles className="w-4 h-4" />
                <span>Generate BRD with Gemini AI</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="rounded-xl border border-sand-200 bg-sand-50 p-3 text-xs text-ink-600">
              Awaiting {leadName(project?.members)} to generate the official BRD.
            </div>
          )}
        </div>
      </div>
    );
  }

  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!brd) return null;

  const isApproved = brd.status === "APPROVED";
  const userDecision = brd.approvals.find((a) => a.member_id === userMembership?.id);
  const canDecide = isSponsor && brdIsOpen(brd.status) && !userDecision;

  return (
    <div className="space-y-6 animate-fade-up">
      <WorkflowNav
        projectId={id}
        projectTitle={project?.title}
        projectState={project?.state}
        currentStep="Brief"
        nextAction={
          isApproved
            ? {
                label: "Proceed to Freelancer Contract",
                href: `/contract?id=${id}`,
                badge: "BRD Approved",
                description: "All sponsors have signed! Set up freelancer agreement.",
              }
            : null
        }
      />

      {/* Prominent Forward Navigation Banner when BRD is Approved */}
      {isApproved && (
        <section
          aria-label="BRD approved"
          className="rounded-3xl border-2 border-emerald-500/80 bg-gradient-to-r from-emerald-50 via-teal-50 to-white p-6 shadow-card"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2.5">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-600 text-xs font-bold text-white shadow-xs">
                  ✓
                </span>
                <h2 className="text-lg font-bold text-ink-900">
                  BRD Specification Approved by All Sponsors!
                </h2>
              </div>
              <p className="text-xs sm:text-sm text-ink-600 max-w-2xl leading-relaxed">
                Version {brd.version} is cryptographically locked with SHA-256 fingerprint{" "}
                <code className="rounded bg-sand-200 px-1 py-0.5 font-mono text-2xs text-ink-800">
                  {brd.sha256.substring(0, 16)}...
                </code>
                . You are ready to offer terms to the freelancer.
              </p>
            </div>
            <Link
              href={`/contract?id=${id}`}
              className="btn btn-primary px-5 py-3 text-sm font-bold shadow-md hover:scale-[1.02] transition-transform flex items-center gap-2 whitespace-nowrap self-stretch sm:self-auto justify-center"
            >
              <span>Proceed to Freelancer Contract</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </section>
      )}

      {/* Specification Hub Header */}
      <div className="card card-pad bg-white rounded-3xl border border-sand-200 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-ink-900">
                Business Requirements Document
              </h1>
              <Badge tone={brdStatus(brd.status).tone}>
                {brdStatus(brd.status).label}
              </Badge>
            </div>
            <p className="text-xs text-ink-500">
              Version {brd.version} · Scored {brd.score_at_generation ?? 90}+ at generation
            </p>
          </div>

          <div className="flex items-center gap-2">
            <a
              href={`${API_BASE}/projects/${id}/brd/${brd.version}.md`}
              download={`BRD-v${brd.version}.md`}
              className="btn btn-secondary px-3.5 py-2 text-xs font-semibold text-ink-700 flex items-center gap-1.5"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download Markdown (.md)</span>
            </a>
          </div>
        </div>

        {/* SHA-256 fingerprint */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-sand-100 pt-3 text-xs">
          <div className="flex items-center gap-2 text-ink-500">
            <ShieldCheck className="w-4 h-4 text-sea-600 flex-shrink-0" />
            <span className="font-semibold text-ink-700">SHA-256 Fingerprint:</span>
            <code className="rounded-lg bg-sand-100 border border-sand-200 px-2 py-0.5 font-mono text-2xs text-ink-800 break-all">
              {brd.sha256}
            </code>
          </div>
        </div>
      </div>

      {actionError && (
        <div role="alert" className="rounded-xl border border-coral-200 bg-coral-50 p-3 text-xs font-medium text-coral-900">
          {actionError}
        </div>
      )}

      {/* Sponsor Approvals Grid */}
      <section aria-label="Approvals" className="card card-pad bg-white rounded-3xl border border-sand-200 shadow-card space-y-4">
        <div className="flex items-center justify-between border-b border-sand-100 pb-2.5">
          <h2 className="font-bold text-ink-900 text-sm sm:text-base">Sponsor Sign-off Matrix</h2>
          <span className="text-2xs font-semibold uppercase tracking-wider text-ink-400">
            {brd.approvals.length} Signed · {brd.awaiting.length} Pending
          </span>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {brd.approvals.map((a) => (
            <div key={a.member_id} className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-3.5 text-xs space-y-1">
              <div className="flex items-center justify-between font-bold text-ink-900">
                <span className="flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>{a.member_name ?? `Member #${a.member_id}`}</span>
                </span>
                <span className="text-emerald-700 font-extrabold">{a.decision}</span>
              </div>
              {a.comment && <p className="text-ink-600 italic">“{a.comment}”</p>}
            </div>
          ))}

          {brd.awaiting.map((m) => (
            <div key={m.member_id} className="rounded-2xl border border-sand-200 bg-sand-50/70 p-3.5 text-xs flex items-center justify-between">
              <span className="font-semibold text-ink-700">{m.member_name ?? `Member #${m.member_id}`}</span>
              <span className="text-2xs font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
                Pending Approval
              </span>
            </div>
          ))}
        </div>

        {/* Decision form if current user is an awaiting sponsor */}
        {canDecide && (
          <div className="mt-4 border-t border-sand-100 pt-4 space-y-3">
            <h3 className="text-xs font-bold text-ink-800 uppercase tracking-wider">
              Sign Your Hash-Bound Approval
            </h3>
            <p className="text-xs text-ink-500">
              By approving, your signature is cryptographically bound to the exact document fingerprint above.
            </p>
            <input
              type="text"
              placeholder="Optional sign-off comment or feedback..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="input w-full text-xs"
            />
            <div className="flex items-center gap-2">
              <button
                disabled={busy !== null}
                onClick={() => void submitDecision("APPROVE")}
                className="btn btn-primary px-4 py-2 text-xs font-bold shadow-xs flex items-center gap-1.5"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{busy === "APPROVE" ? "Submitting..." : "✓ Approve BRD"}</span>
              </button>
              <button
                disabled={busy !== null}
                onClick={() => void submitDecision("REJECT")}
                className="btn btn-danger px-4 py-2 text-xs font-bold shadow-xs flex items-center gap-1.5"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>{busy === "REJECT" ? "Submitting..." : "Reject (Reopen BA)"}</span>
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Full 12-Chapter Book Specification & Interactive Matrix */}
      <BrdDocumentBook
        brd={brd}
        members={project?.members}
        selectedReq={selectedReq}
        onSelectReq={setSelectedReq}
        columns={columns}
        downloadHref={`${API_BASE}/projects/${id}/brd/${brd.version}.md`}
      />
    </div>
  );
}

function FromQuery() {
  const raw = useSearchParams().get("id");
  const id = raw !== null && /^\d{1,9}$/.test(raw) ? Number(raw) : null;
  if (id === null)
    return (
      <Empty title="No project selected">
        Open a project from <Link href="/" className="text-sea-700 underline">the project list</Link>.
      </Empty>
    );
  return <BRDView id={id} />;
}

export default function BRDPage() {
  return (
    <Suspense fallback={<Loading what="Loading BRD" />}>
      <FromQuery />
    </Suspense>
  );
}
