"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { RequirementDialog } from "@/components/RequirementDialog";
import { RequirementsGrid } from "@/components/RequirementsGrid";
import { Badge, Empty, ErrorBox, Loading } from "@/components/ui";
import { API_BASE, api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { BRD_REFRESH_MS, approvedCount, brdState, markdownUrl, mayDecide, mayGenerate, nameOf, progressText, rejectReady, shortHash } from "@/lib/brd";
import { formatMoney } from "@/lib/money";
import { roleOn } from "@/lib/plans";
import { formatDateTime } from "@/lib/time";
import type { BrdDecisionResult, BrdRequirement, BrdView, ProjectDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useJob } from "@/lib/useJob";

const said = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return <section aria-label={title}><h3 className="font-medium">{title}</h3><ul className="list-disc pl-5 text-sm text-gray-700">{items.map((x, i) => <li key={i}>{x}</li>)}</ul></section>;
}

function Brief({ id }: { id: number }) {
  const auth = useAuth();
  const [version, setVersion] = useState<number | null>(null);
  const brd = useApi<BrdView>(auth.status === "loading" ? null : `/projects/${id}/brd${version === null ? "" : `?version=${version}`}`, auth.user?.id ?? null);
  const pr = useApi<ProjectDetail>(auth.status === "loading" ? null : `/projects/${id}`, auth.user?.id ?? null);
  const [open, setOpen] = useState<BrdRequirement | null>(null);
  const [search, setSearch] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [job, setJob] = useState<number | null>(null);
  const { reload: reloadBrd } = brd;
  const { reload: reloadPr } = pr;
  const waiting = brd.data?.status === "PENDING_APPROVAL";

  useEffect(() => {                                   // a document waiting for decisions keeps asking for news while the tab is visible
    if (!waiting) return;
    const t = setInterval(() => document.visibilityState === "visible" && reloadBrd(), BRD_REFRESH_MS);
    return () => clearInterval(t);
  }, [waiting, reloadBrd]);

  const jobDone = useCallback(() => { setJob(null); setVersion(null); reloadBrd(); reloadPr(); }, [reloadBrd, reloadPr]);
  const jobFailed = useCallback((m: string) => { setJob(null); setProblem(`The brief could not be written. ${m}`); }, []);
  useJob(job, jobDone, jobFailed);

  const names = useMemo(() => Object.fromEntries((pr.data?.members ?? []).map((m) => [m.id, m.display_name])) as Record<number, string>, [pr.data]);
  const close = useCallback(() => setOpen(null), []);

  if (auth.status === "loading") return <Loading what="Checking who you are" />;
  const role = roleOn(auth.memberships, id);
  const projectState = pr.data?.state ?? "";
  const none = brd.error?.code === "NO_BRD";

  async function act(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setProblem(null);
    setMessage(null);
    try { await fn(); } catch (e) {
      setProblem(said(e));
      if (e instanceof ApiError && e.code === "HASH_MISMATCH") reloadBrd();       // the document changed under the reader: show the new one
    } finally { setBusy(null); }
  }

  const header = (
    <div>
      <Link href={`/project?id=${id}`} className="text-sm text-sea-700 hover:underline">Back to the project</Link>
      <h1 className="mt-1 text-2xl font-bold">The brief</h1>
      <p className="text-sm text-gray-600">What will be built, in plain words, and exactly how each part will be checked. Sponsors approve one exact version; once all approve it is locked.</p>
    </div>
  );
  const generate = mayGenerate(role, projectState) && (
    <button disabled={busy !== null || job !== null} onClick={() => void act("generate", async () => { const r = await api<{ job_id: number }>(`/projects/${id}/brd/generate`, { method: "POST" }); setJob(r.job_id); })}
            className="rounded bg-sea-600 px-3 py-1.5 text-sm text-white hover:bg-sea-700 disabled:opacity-60">{none ? "Write the brief" : "Write a new version"}</button>
  );

  if (brd.loading && !brd.data) return <Loading what="Loading the brief" slow={brd.slow} />;
  if (none) {
    return (
      <div className="space-y-4">
        {header}
        {problem && <p role="alert" className="rounded bg-red-50 p-2 text-sm text-red-800">{problem}</p>}
        {job !== null && <p role="status" className="rounded bg-sea-50 p-2 text-sm text-sea-700">The brief is being written. This takes a short while.</p>}
        <Empty title="No brief has been written yet">The business analyst has to reach the target score first; then the lead writes the brief here.</Empty>
        {generate}
      </div>
    );
  }
  if (brd.error && !brd.data) return <ErrorBox error={brd.error} onRetry={reloadBrd} />;
  if (!brd.data) return null;

  const b = brd.data;
  const c = b.content;
  const st = brdState(b.status);
  const approved = approvedCount(b.approvals);
  const required = approved + b.awaiting.length;
  const decide = mayDecide(role, b.status, projectState);
  const mine = auth.user ? b.approvals.find((a) => a.member_name === auth.user?.display_name) : undefined;

  return (
    <div className="space-y-5">
      {header}
      {brd.error && <p role="alert" className="rounded bg-amber-50 p-2 text-sm text-amber-800">Could not refresh just now ({brd.error.message}). Showing the last version we have.</p>}
      {problem && <p role="alert" className="rounded bg-red-50 p-2 text-sm text-red-800">{problem}</p>}
      {message && <p role="status" className="rounded bg-sea-50 p-2 text-sm text-sea-700">{message}</p>}
      {job !== null && <p role="status" className="rounded bg-sea-50 p-2 text-sm text-sea-700">The brief is being written. This takes a short while.</p>}

      <section aria-label="Version" className="space-y-2 rounded-xl border border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xl font-semibold" data-testid="title">{c.title || "Untitled brief"} · version {b.version}</h2>
          <Badge tone={st.tone}>{st.label}</Badge>
        </div>
        <p className="text-sm text-gray-600">{st.hint}</p>
        <p className="text-xs text-gray-500">
          Fingerprint <span className="font-mono" title={b.sha256}>{shortHash(b.sha256)}</span>: a decision counts only for this exact text.
          {b.score_at_generation !== null ? ` Written when the analysis scored ${b.score_at_generation}.` : ""}
          {b.locked_at ? ` Locked ${formatDateTime(b.locked_at)}.` : ""}
        </p>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {b.versions.length > 1 && b.versions.map((v) => (
            <button key={v.version} aria-pressed={v.version === b.version} onClick={() => setVersion(v.version)}
                    className={`rounded-full border px-3 py-1 ${v.version === b.version ? "border-sea-600 bg-sea-600 text-white" : "border-gray-300 bg-white text-gray-700"}`}>Version {v.version}</button>
          ))}
          <a href={markdownUrl(API_BASE, id, b.version)} className="text-sea-700 underline">Download as text</a>
          {generate}
        </div>
      </section>

      <section aria-label="Summary" className="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
        <p className="text-gray-800">{c.executive_summary}</p>
        <List title="Goals" items={c.business_goals} />
        <List title="How we will know it worked" items={c.success_measures} />
        <div><h3 className="font-medium">Who it is for</h3><p className="text-sm text-gray-700">{c.audience}</p></div>
      </section>

      {c.stakeholders.length > 0 && (
        <section aria-label="Stakeholders" className="rounded-xl border border-gray-200 bg-white p-4">
          <h2 className="mb-2 font-semibold">What each sponsor needs</h2>
          <ul className="space-y-2 text-sm">
            {c.stakeholders.map((s) => (
              <li key={s.member_id}><strong>{nameOf(names, s.member_id)}</strong>{s.business_name ? ` (${s.business_name})` : ""}
                <ul className="list-disc pl-5 text-gray-700">{s.needs.map((n, i) => <li key={i}>{n}</li>)}</ul></li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Pages" className="rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="mb-2 font-semibold">The pages</h2>
        <table className="w-full text-sm"><tbody>
          {c.sitemap.map((s) => <tr key={s.path} className="border-t border-gray-100"><td className="w-40 py-1 font-mono">{s.path}</td><td className="py-1 text-gray-700">{s.purpose}</td></tr>)}
        </tbody></table>
      </section>

      <section aria-label="Requirements" className="space-y-2 rounded-xl border border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Requirements ({c.requirements.length})</h2>
          <input aria-label="Search the requirements" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} className="rounded border border-gray-300 px-3 py-1.5 text-sm" />
        </div>
        <RequirementsGrid requirements={c.requirements} names={names} quickFilter={search} onOpen={setOpen} />
      </section>

      <section aria-label="Details" className="grid gap-4 rounded-xl border border-gray-200 bg-white p-4 md:grid-cols-2">
        <List title="Non-functional needs" items={c.non_functional} />
        <List title="Out of scope" items={c.out_of_scope} />
        <div>
          <h3 className="font-medium">Terms</h3>
          <dl className="grid grid-cols-2 gap-y-1 text-sm">
            <dt className="text-gray-500">Budget</dt><dd>{formatMoney(c.constraints.budget_cents, c.constraints.currency)}</dd>
            <dt className="text-gray-500">Delivery time</dt><dd>{c.constraints.delivery_days ? `${c.constraints.delivery_days} days` : "not set"}</dd>
            <dt className="text-gray-500">Hosting</dt><dd>{c.constraints.hosting ?? "not set"}</dd>
            <dt className="text-gray-500">Domain</dt><dd>{c.constraints.domain ?? "not set"}</dd>
          </dl>
        </div>
        {c.content_responsibilities.length > 0 && (
          <section aria-label="Content to provide"><h3 className="font-medium">Who provides what</h3>
            <ul className="list-disc pl-5 text-sm text-gray-700">{c.content_responsibilities.map((r, i) => <li key={i}>{r.item}: {nameOf(names, r.owner_member_id)}{r.due ? `, by ${r.due}` : ""}</li>)}</ul></section>
        )}
        {c.glossary.length > 0 && (
          <section aria-label="Glossary"><h3 className="font-medium">Words used</h3>
            <dl className="text-sm">{c.glossary.map((g) => <div key={g.term}><dt className="inline font-medium">{g.term}: </dt><dd className="inline text-gray-700">{g.definition}</dd></div>)}</dl></section>
        )}
      </section>

      {b.open_items.length > 0 && (
        <section aria-label="Open items" className="rounded-xl border border-amber-300 bg-amber-50 p-4">
          <h2 className="font-semibold text-amber-900">Still open</h2>
          <ul className="list-disc pl-5 text-sm text-amber-900">{b.open_items.map((x, i) => <li key={i}>{x}</li>)}</ul>
        </section>
      )}

      <section aria-label="Approvals" className="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="font-semibold">Sponsor decisions</h2>
        <p className="text-sm text-gray-700" data-testid="progress">{progressText(approved, required)}</p>
        {b.approvals.length > 0 && (
          <ul className="space-y-1 text-sm" aria-label="Decisions">
            {b.approvals.map((a) => (
              <li key={a.member_id} data-decision={a.decision}>
                <Badge tone={a.decision === "APPROVE" ? "green" : "red"}>{a.decision === "APPROVE" ? "Approved" : "Asked for changes"}</Badge> {a.member_name ?? "Someone"}
                {a.comment ? `: “${a.comment}”` : ""} <span className="text-xs text-gray-500">{formatDateTime(a.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
        {b.awaiting.length > 0 && <p className="text-sm text-gray-600" data-testid="awaiting">Still to decide: {b.awaiting.map((w) => w.member_name ?? "someone").join(", ")}.</p>}
        {decide && (
          <div className="space-y-2">
            {mine && <p className="text-sm text-gray-600" data-testid="mine">You {mine.decision === "APPROVE" ? "approved" : "asked for changes to"} this version. You can change your mind while it is open.</p>}
            <textarea aria-label="Your comment" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={2000} rows={3} placeholder="Comment (needed if you ask for changes)" className="w-full rounded border border-gray-300 p-2 text-sm" />
            <div className="flex flex-wrap items-center gap-2">
              <button disabled={busy !== null} onClick={() => void act("approve", async () => {
                const r = await api<BrdDecisionResult>(`/projects/${id}/brd/${b.version}/decision`, { method: "POST", body: { decision: "APPROVE", brd_sha256: b.sha256, comment: comment.trim() || undefined } });
                setComment("");
                setMessage(r.locked ? "Every sponsor approved. The brief is locked and the contract comes next." : `Your approval is recorded. ${progressText(r.approved, r.required)}.`);
                reloadBrd(); reloadPr();
              })} className="rounded bg-green-700 px-3 py-1.5 text-sm text-white hover:bg-green-800 disabled:opacity-60">{busy === "approve" ? "Approving..." : "Approve this version"}</button>
              <button disabled={busy !== null || !rejectReady(comment)} onClick={() => void act("reject", async () => {
                await api<BrdDecisionResult>(`/projects/${id}/brd/${b.version}/decision`, { method: "POST", body: { decision: "REJECT", brd_sha256: b.sha256, comment: comment.trim() } });
                setComment("");
                setMessage("Your request for changes is recorded. The analyst will ask how the brief should change.");
                reloadBrd(); reloadPr();
              })} className="rounded border border-red-300 bg-white px-3 py-1.5 text-sm text-red-800 hover:bg-red-50 disabled:opacity-50">{busy === "reject" ? "Sending..." : "Ask for changes"}</button>
              {!rejectReady(comment) && <span className="text-xs text-gray-500" data-testid="why-not-reject">To ask for changes, say what should change.</span>}
            </div>
          </div>
        )}
        {!decide && b.status === "PENDING_APPROVAL" && <p className="text-sm text-gray-600" data-testid="not-yours">Only the lead and the sponsors decide on the brief.</p>}
      </section>

      {open && <RequirementDialog req={open} names={names} onClose={close} />}
    </div>
  );
}

function FromQuery() {
  const raw = useSearchParams().get("id");
  const id = raw !== null && /^\d{1,9}$/.test(raw) ? Number(raw) : null;
  if (id === null) return <Empty title="No project selected">Open the brief from a <Link href="/" className="text-sea-700 underline">project</Link>.</Empty>;
  return <Brief id={id} />;
}

export default function BrdPage() {
  return <Suspense fallback={<Loading what="Loading" />}><FromQuery /></Suspense>;
}
