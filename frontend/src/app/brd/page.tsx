"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, useMemo } from "react";
import { AllCommunityModule, ModuleRegistry, type ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { apiPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { BRDResponse, BRDRequirementItem, ProjectDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";

ModuleRegistry.registerModules([AllCommunityModule]);

function BRDView({ id }: { id: number }) {
  const auth = useAuth();
  const [refreshKey, setRefreshKey] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [selectedReq, setSelectedReq] = useState<BRDRequirementItem | null>(null);

  const { data: project } = useApi<ProjectDetail>(auth.status === "loading" ? null : `/projects/${id}`, auth.user?.id ?? null);
  const { data: brd, error, loading, slow, reload } = useApi<BRDResponse>(
    auth.status === "loading" ? null : `/projects/${id}/brd`,
    `${auth.user?.id ?? "anon"}-${refreshKey}`
  );

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

  const columns = useMemo<ColDef<BRDRequirementItem>[]>(() => [
    { field: "code", headerName: "Code", width: 110, pinned: "left", sort: "asc" },
    { field: "title", headerName: "Requirement Title", flex: 1, minWidth: 200 },
    {
      field: "priority",
      headerName: "Priority",
      width: 110,
      cellClass: (p) =>
        p.value === "MUST" ? "font-bold text-red-700" : p.value === "SHOULD" ? "font-semibold text-sea-700" : "text-slate-500",
    },
    {
      headerName: "Criteria",
      width: 100,
      valueGetter: (p) => `${p.data?.acceptance_criteria?.length ?? 0} ACs`,
    },
    { field: "weight", headerName: "Weight", width: 90 },
  ], []);

  if (auth.status === "loading" || loading) return <Loading what="Loading BRD" slow={slow} />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!brd) return null;

  const userMembership = project?.members?.find((m) => m.email === auth.user?.email);
  const isSponsor = userMembership?.role === "LEAD" || userMembership?.role === "SPONSOR";
  const userDecision = brd.approvals.find((a) => a.member_id === userMembership?.id);
  const canDecide = isSponsor && brd.status !== "LOCKED" && !userDecision;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-xs">
        <div className="mb-2">
          <Link href={`/project?id=${id}`} className="inline-flex items-center gap-1 text-xs font-semibold text-sea-700 hover:text-sea-800 transition">
            <span aria-hidden="true">&larr;</span> Back to Project Workspace
          </Link>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
              Business Requirements Document (BRD)
            </h1>
            <p className="mt-1 text-xs text-slate-500">
              Cryptographically locked specification · Hash-bound unanimous approval required
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
              Version {brd.version}
            </span>
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
              Score: {brd.score_at_generation}/100
            </span>
            <Badge tone={brd.status === "APPROVED" || brd.status === "LOCKED" ? "green" : "teal"}>
              {brd.status}
            </Badge>
          </div>
        </div>

        {/* SHA-256 fingerprint pill & download button */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3 text-xs">
          <div className="flex items-center gap-2 text-slate-500">
            <span className="font-semibold text-slate-700">SHA-256 Fingerprint:</span>
            <code className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-800">
              {brd.sha256}
            </code>
          </div>
          <a
            href={`/api/projects/${id}/brd/${brd.version}.md`}
            download={`BRD-v${brd.version}.md`}
            className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
          >
            Download Markdown (.md)
          </a>
        </div>
      </div>

      {actionError && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-900">
          {actionError}
        </div>
      )}

      {/* Sponsor Approvals Grid */}
      <section aria-label="Approvals" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-bold text-slate-900 mb-3 border-b border-slate-100 pb-2">
          Sponsor Approval Status
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {brd.approvals.map((a) => (
            <div key={a.member_id} className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-900">{a.member_name}</span>
                <span className={`font-semibold ${a.decision === "APPROVE" ? "text-emerald-700" : "text-red-700"}`}>
                  ✓ {a.decision}
                </span>
              </div>
              {a.comment && <p className="mt-1 text-slate-600 italic">"{a.comment}"</p>}
            </div>
          ))}
          {brd.awaiting.map((m) => (
            <div key={m.member_id} className="rounded-xl border border-amber-200 bg-amber-50/50 p-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-900">{m.member_name}</span>
                <span className="font-semibold text-amber-700">⏳ Awaiting Decision</span>
              </div>
            </div>
          ))}
        </div>

        {/* Decision form if current user is an awaiting sponsor */}
        {canDecide && (
          <div className="mt-4 border-t border-slate-100 pt-4">
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-2">
              Sign Your Hash-Bound Approval
            </h3>
            <p className="text-xs text-slate-500 mb-3">
              By approving, your signature is cryptographically bound to the exact document fingerprint above.
            </p>
            <div className="space-y-3">
              <input
                type="text"
                placeholder="Optional sign-off comment or feedback..."
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                className="w-full rounded-xl border border-slate-300 px-3.5 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:border-sea-500 focus:outline-none"
              />
              <div className="flex gap-2">
                <button
                  disabled={busy !== null}
                  onClick={() => void submitDecision("APPROVE")}
                  className="rounded-xl bg-gradient-to-r from-emerald-600 to-teal-700 px-4 py-2 text-xs font-bold text-white shadow-sm hover:from-emerald-700 hover:to-teal-800 disabled:opacity-60 transition"
                >
                  {busy === "APPROVE" ? "Submitting..." : "✓ Approve BRD"}
                </button>
                <button
                  disabled={busy !== null}
                  onClick={() => void submitDecision("REJECT")}
                  className="rounded-xl border border-red-300 bg-red-50 px-4 py-2 text-xs font-bold text-red-700 hover:bg-red-100 disabled:opacity-60 transition"
                >
                  {busy === "REJECT" ? "Submitting..." : "Reject (Reopen BA)"}
                </button>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Executive Summary */}
      <section aria-label="Executive Summary" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-bold text-slate-900 mb-2">{brd.content.title}</h2>
        <p className="text-xs sm:text-sm text-slate-600 leading-relaxed mb-4">{brd.content.executive_summary}</p>

        <div className="grid gap-4 sm:grid-cols-2 border-t border-slate-100 pt-3">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Business Goals</h3>
            <ul className="list-disc pl-5 space-y-1 text-xs text-slate-700">
              {brd.content.business_goals.map((g, i) => (
                <li key={i}>{g}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Success Measures</h3>
            <ul className="list-disc pl-5 space-y-1 text-xs text-slate-700">
              {brd.content.success_measures.map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Requirements Table (AG Grid) */}
      <section aria-label="Requirements Matrix" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex items-center justify-between mb-3 border-b border-slate-100 pb-2">
          <div>
            <h2 className="text-base font-bold text-slate-900">Requirements Matrix</h2>
            <p className="text-xs text-slate-500">Click any row to inspect acceptance criteria and evidence requirements</p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
            {brd.content.requirements.length} Requirements
          </span>
        </div>

        <div className="ag-theme-quartz rounded-xl overflow-hidden border border-slate-200" style={{ height: "320px", width: "100%" }}>
          <AgGridReact
            rowData={brd.content.requirements}
            columnDefs={columns}
            rowSelection="single"
            onRowClicked={(e) => setSelectedReq(e.data ?? null)}
            animateRows
          />
        </div>

        {/* Selected Requirement Detail Accordion */}
        {selectedReq && (
          <div className="mt-4 rounded-xl border border-sea-200 bg-sea-50/40 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold text-sea-700 bg-sea-100 px-2 py-0.5 rounded">
                  {selectedReq.code}
                </span>
                <h3 className="text-sm font-bold text-slate-900">{selectedReq.title}</h3>
              </div>
              <span className={`text-xs font-bold ${selectedReq.priority === "MUST" ? "text-red-700" : "text-sea-700"}`}>
                Priority: {selectedReq.priority}
              </span>
            </div>
            <p className="text-xs text-slate-700 leading-relaxed">{selectedReq.description}</p>

            <div className="border-t border-sea-200/60 pt-2 space-y-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Acceptance Criteria ({selectedReq.acceptance_criteria.length}):
              </span>
              {selectedReq.acceptance_criteria.map((ac) => (
                <div key={ac.id} className="rounded-lg bg-white p-3 border border-slate-200 text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-slate-700">{ac.id}</span>
                    <span className="text-[10px] text-slate-500">Evidence: {ac.evidence.join(", ")}</span>
                  </div>
                  <p className="text-slate-800">
                    <strong>Given</strong> {ac.given} <strong>When</strong> {ac.when} <strong>Then</strong> {ac.then}
                  </p>
                </div>
              ))}
            </div>
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
  return <BRDView id={id} />;
}

export default function BRDPage() {
  return (
    <Suspense fallback={<Loading what="Loading BRD" />}>
      <FromQuery />
    </Suspense>
  );
}
