"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { LedgerGrid, type Matches } from "@/components/LedgerGrid";
import { MetaDialog } from "@/components/MetaDialog";
import { WorkflowNav } from "@/components/WorkflowNav";
import { Empty, ErrorBox, Loading } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { REFRESH_MS, filterRows, toCsv, typeLabel, typesPresent } from "@/lib/ledger";
import { formatMoney } from "@/lib/money";
import type { LedgerResponse, LedgerRow, MatchResponse, ProjectDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function Ledger({ id }: { id: number }) {
  const auth = useAuth();
  const { data, error, loading, slow, reload } = useApi<LedgerResponse>(auth.status === "loading" ? null : `/projects/${id}/ledger`, auth.user?.id ?? null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<LedgerRow | null>(null);
  const [matches, setMatches] = useState<Matches>(null);
  const [matchNote, setMatchNote] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {                                   // live refresh while the page is visible
    const t = setInterval(() => document.visibilityState === "visible" && reload(), REFRESH_MS);
    return () => clearInterval(t);
  }, [reload]);

  const rows = useMemo(() => (data ? filterRows(data.rows, chosen) : []), [data, chosen]);
  const close = useCallback(() => setOpen(null), []);
  const toggle = (type: string) => setChosen((s) => { const n = new Set(s); n.has(type) ? n.delete(type) : n.add(type); return n; });

  async function checkWithPayPal() {
    setChecking(true);
    setMatchNote(null);
    try {
      const m = await api<MatchResponse>(`/projects/${id}/ledger/paypal-match`);
      setMatches(m.results);
      const bad = m.counts.MISMATCH + m.counts.NOT_FOUND;
      setMatchNote(Object.keys(m.results).length === 0 ? "There are no PayPal-backed rows to check yet."
        : m.all_match ? `PayPal agrees with all ${Object.keys(m.results).length} checked rows.`
        : `${bad} row${bad === 1 ? "" : "s"} disagree${bad === 1 ? "s" : ""} with PayPal, ${m.counts.PENDING} not final yet, ${m.counts.UNAVAILABLE} could not be checked.${m.limited ? " Only the newest rows were checked." : ""}`);
    } catch (e) {
      setMatchNote(e instanceof ApiError ? e.message : "Could not check with PayPal");
    } finally {
      setChecking(false);
    }
  }

  if (auth.status === "loading" || (loading && !data)) return <Loading what="Loading the ledger" slow={slow} />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const types = typesPresent(data.rows);
  const member = !data.public;
  return (
    <div className="space-y-4">
      <WorkflowNav
        projectId={id}
        currentStep="Ledger"
      />
      <div>
        <Link href={`/project?id=${id}`} className="text-sm text-sea-700 hover:underline">Back to the project</Link>
        <h1 className="mt-1 text-2xl font-bold">Ledger</h1>
        <p className="text-sm text-gray-600">
          Every money and AI event, in order, never edited. In the pool now: <strong data-testid="balance">{formatMoney(data.totals.pool_balance_cents)}</strong>
          {" "}(in {formatMoney(data.totals.pool_in_cents)}, out {formatMoney(Math.abs(data.totals.pool_out_cents))}). {data.public && "Public view: contact details are hidden."}
        </p>
      </div>
      {error && <p role="alert" className="rounded bg-amber-50 p-2 text-sm text-amber-800">Could not refresh the ledger just now ({error.message}). Showing the last rows we have.</p>}
      {data.rows.length === 0 ? <Empty title="The ledger is empty">Rows appear as the project moves.</Empty> : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {types.map((t) => (
              <button key={t} aria-pressed={chosen.has(t)} onClick={() => toggle(t)}
                      className={`rounded-full border px-3 py-1 text-sm ${chosen.has(t) ? "border-sea-600 bg-sea-600 text-white" : "border-gray-300 bg-white text-gray-700"}`}>{typeLabel(t)}</button>
            ))}
            {chosen.size > 0 && <button onClick={() => setChosen(new Set())} className="text-sm text-sea-700 underline">Show all</button>}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <input aria-label="Search the ledger" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} className="rounded border border-gray-300 px-3 py-1.5 text-sm" />
            <button onClick={() => download(`ledger-project-${id}.csv`, toCsv(rows))} className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50">Export CSV</button>
            <button onClick={reload} className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50">Refresh</button>
            {member && <button disabled={checking} onClick={() => void checkWithPayPal()} className="rounded bg-sea-600 px-3 py-1.5 text-sm text-white hover:bg-sea-700 disabled:opacity-60">{checking ? "Checking..." : "Check with PayPal"}</button>}
          </div>
          {matchNote && <p role="status" className="rounded bg-sea-50 p-2 text-sm text-sea-700">{matchNote}</p>}
          <LedgerGrid rows={rows} balanceCents={data.totals.pool_balance_cents} matches={matches} quickFilter={search} onOpenMeta={setOpen} />
          <p className="text-xs text-gray-500">Holds are shown as memo rows of $0: a pledge hold is not money until it is collected.</p>
        </>
      )}
      {open && <MetaDialog row={open} onClose={close} />}
    </div>
  );
}

function FromQuery() {
  const raw = useSearchParams().get("id");
  const id = raw !== null && /^\d{1,9}$/.test(raw) ? Number(raw) : null;
  if (id === null) return <Empty title="No project selected">Open the ledger from a <Link href="/" className="text-sea-700 underline">project</Link>.</Empty>;
  return <Ledger id={id} />;
}

export default function LedgerPage() {
  return <Suspense fallback={<Loading what="Loading" />}><FromQuery /></Suspense>;
}
