"use client";
import { useState } from "react";
import { Badge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { addressedText, questionState } from "@/lib/ba";
import type { BaQuestion } from "@/lib/types";

/** One question from the analyst: who it is for, why it matters, the answers so far, and (when it is yours) the answer form. */
export function QuestionCard({ q, names, isLead, onChanged }: { q: BaQuestion; names: Record<number, string>; isLead: boolean; onChanged: () => void }) {
  const [text, setText] = useState("");
  const [option, setOption] = useState<string | null>(null);
  const [busy, setBusy] = useState<"answer" | "skip" | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const st = questionState(q.status);

  async function send(kind: "answer" | "skip") {
    setBusy(kind);
    setProblem(null);
    try {
      if (kind === "answer") await api(`/ba/questions/${q.id}/answers`, { method: "POST", body: { answer_text: text.trim(), selected_option: option ?? undefined } });
      else await api(`/ba/questions/${q.id}/skip`, { method: "POST" });
      setText("");
      setOption(null);
      onChanged();
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  }

  return (
    <article aria-label={`Question ${q.id}`} className="space-y-2 rounded-lg border border-gray-200 bg-white p-3 text-sm" data-status={q.status}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs uppercase tracking-wide text-gray-500">{q.dimension_name ?? q.dimension} · for {addressedText(q.addressed_to, names)}</span>
        <Badge tone={st.tone}>{st.label}</Badge>
      </div>
      <p className="font-medium">{q.question}</p>
      <p className="text-gray-600">{q.rationale}</p>
      {q.answers.length > 0 && (
        <ul className="space-y-1" aria-label="Answers">
          {q.answers.map((a) => <li key={a.id} className="rounded bg-gray-50 p-2"><strong>{a.member_name ?? "Someone"}:</strong> {a.answer_text}</li>)}
        </ul>
      )}
      {problem && <p role="alert" className="rounded bg-red-50 p-2 text-red-800">{problem}</p>}
      {q.can_answer && (
        <div className="space-y-2">
          {(q.suggested_options ?? []).length > 0 && (
            <div className="flex flex-wrap gap-2" role="group" aria-label="Suggested answers">
              {(q.suggested_options ?? []).map((o) => (
                <button key={o} aria-pressed={option === o} onClick={() => { setOption(option === o ? null : o); if (option !== o) setText(o); }}
                        className={`rounded-full border px-3 py-1 ${option === o ? "border-sea-600 bg-sea-600 text-white" : "border-gray-300 bg-white text-gray-700"}`}>{o}</button>
              ))}
            </div>
          )}
          <textarea aria-label={`Your answer to question ${q.id}`} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} rows={2} className="w-full rounded border border-gray-300 p-2" />
          <button disabled={busy !== null || text.trim() === ""} onClick={() => void send("answer")} className="rounded bg-sea-600 px-3 py-1.5 text-white hover:bg-sea-700 disabled:opacity-50">{busy === "answer" ? "Sending..." : "Send answer"}</button>
        </div>
      )}
      {isLead && q.status === "OPEN" && (
        <button disabled={busy !== null} onClick={() => void send("skip")} className="text-gray-600 underline disabled:opacity-50">{busy === "skip" ? "Skipping..." : "Skip this question"}</button>
      )}
    </article>
  );
}
