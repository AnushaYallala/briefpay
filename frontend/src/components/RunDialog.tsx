"use client";
import { useEffect } from "react";
import { agentLabel, statusInfo } from "@/lib/audit";
import { formatDateTime } from "@/lib/time";
import type { AgentRun } from "@/lib/types";

/** One AI call in full: what came back (or the error), as plain text so nothing in it can run. Escape or the button closes it. */
export function RunDialog({ run, onClose }: { run: AgentRun; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={`AI call ${run.id}`} className="max-h-[80vh] w-full max-w-2xl overflow-auto rounded-xl bg-white p-5 shadow-xl"
           onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold">Call {run.id}: {agentLabel(run.agent)}</h2>
        <p className="text-sm text-gray-500">{formatDateTime(run.created_at)} · {statusInfo(run.status).label} · prompt {run.prompt_version}</p>
        <p className="mt-1 break-all font-mono text-xs text-gray-500">input {run.input_hash}</p>
        {run.error && <p role="alert" className="mt-3 rounded bg-red-50 p-2 text-sm text-red-800" data-testid="run-error">{run.error}</p>}
        <pre className="mt-3 overflow-auto rounded bg-gray-50 p-3 text-xs" data-testid="run-output">{run.output === null ? "No answer was saved." : JSON.stringify(run.output, null, 2)}</pre>
        <button onClick={onClose} className="mt-4 rounded bg-sea-600 px-3 py-1.5 text-white hover:bg-sea-700">Close</button>
      </div>
    </div>
  );
}
