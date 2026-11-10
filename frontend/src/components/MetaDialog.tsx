"use client";
import { useEffect } from "react";
import { typeLabel } from "@/lib/ledger";
import { formatDateTime } from "@/lib/time";
import type { LedgerRow } from "@/lib/types";

/** The full record behind one ledger row (its `meta`), shown as plain text so nothing in it can run. Escape or the button closes it. */
export function MetaDialog({ row, onClose }: { row: LedgerRow; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={`Ledger row ${row.seq}`} className="max-h-[80vh] w-full max-w-lg overflow-auto rounded-xl bg-white p-5 shadow-xl"
           onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold">Row {row.seq}: {typeLabel(row.type)}</h2>
        <p className="text-sm text-gray-500">{formatDateTime(row.created_at)} · by {row.actor_name}{row.ref_type ? ` · ${row.ref_type} ${row.ref_id ?? ""}` : ""}</p>
        <pre className="mt-3 overflow-auto rounded bg-gray-50 p-3 text-xs" data-testid="meta-json">{JSON.stringify(row.meta, null, 2)}</pre>
        <button onClick={onClose} className="mt-4 rounded bg-sea-600 px-3 py-1.5 text-white hover:bg-sea-700">Close</button>
      </div>
    </div>
  );
}
