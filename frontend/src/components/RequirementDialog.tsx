"use client";
import { useEffect } from "react";
import { Badge } from "@/components/ui";
import { evidenceWords, hintWords, namesOf, priorityTone } from "@/lib/brd";
import { refWords } from "@/lib/ba";
import type { BrdRequirement } from "@/lib/types";

/** One requirement in full: what it is, who asked, and each acceptance criterion with the evidence that proves it. Escape or the button closes it. */
export function RequirementDialog({ req, names, onClose }: { req: BrdRequirement; names: Record<number, string>; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={`Requirement ${req.code}`} className="max-h-[85vh] w-full max-w-2xl overflow-auto rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-lg font-semibold">{req.code}: {req.title}</h2>
          <Badge tone={priorityTone(req.priority)}>{req.priority}</Badge>
        </div>
        <p className="mt-1 text-sm text-gray-700">{req.description}</p>
        <p className="mt-1 text-xs text-gray-500">Asked for by {namesOf(names, req.requested_by)} · weight {req.weight} of 5{req.source_refs.length > 0 ? ` · from ${req.source_refs.map(refWords).join(", ")}` : ""}</p>
        <h3 className="mt-4 font-medium">How we will know it is done</h3>
        {req.acceptance_criteria.length === 0 ? <p className="text-sm text-gray-600">No checks yet.</p> : (
          <ol className="mt-1 space-y-2 text-sm" aria-label="Acceptance criteria">
            {req.acceptance_criteria.map((c) => (
              <li key={c.id} className="rounded border border-gray-200 p-2">
                <p className="font-medium">{c.id}</p>
                <p><strong>Given</strong> {c.given}</p>
                <p><strong>When</strong> {c.when}</p>
                <p><strong>Then</strong> {c.then}</p>
                <p className="text-xs text-gray-500">Proof: {evidenceWords(c.evidence)}</p>
                {hintWords(c.auto_check_hint) && <p className="text-xs text-sea-700" data-testid="hint">The platform can check this itself: {hintWords(c.auto_check_hint)}.</p>}
              </li>
            ))}
          </ol>
        )}
        <button onClick={onClose} className="mt-4 rounded bg-sea-600 px-3 py-1.5 text-white hover:bg-sea-700">Close</button>
      </div>
    </div>
  );
}
