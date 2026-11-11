"use client";
import { useState } from "react";
import { Badge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { addressedText, questionState } from "@/lib/ba";
import type { BaQuestion } from "@/lib/types";
import { HelpCircle, Send, SkipForward } from "lucide-react";

/** One question from the analyst: who it is for, why it matters, the answers so far, and (when it is yours) the answer form. */
export function QuestionCard({
  q,
  names,
  isLead,
  onChanged,
}: {
  q: BaQuestion;
  names: Record<number, string>;
  isLead: boolean;
  onChanged: () => void;
}) {
  const [text, setText] = useState("");
  const [option, setOption] = useState<string | null>(null);
  const [busy, setBusy] = useState<"answer" | "skip" | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const st = questionState(q.status);

  async function send(kind: "answer" | "skip") {
    setBusy(kind);
    setProblem(null);
    try {
      if (kind === "answer")
        await api(`/ba/questions/${q.id}/answers`, {
          method: "POST",
          body: { answer_text: text.trim(), selected_option: option ?? undefined },
        });
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
    <article
      aria-label={`Question ${q.id}`}
      className="card card-pad bg-white rounded-2xl border border-sand-200 shadow-2xs space-y-3 text-sm transition-all"
      data-status={q.status}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-sand-100 pb-2">
        <span className="text-2xs font-bold uppercase tracking-wider text-ink-500">
          {q.dimension_name ?? q.dimension} · for {addressedText(q.addressed_to, names)}
        </span>
        <Badge tone={st.tone}>{st.label}</Badge>
      </div>

      <div className="space-y-1">
        <p className="font-bold text-ink-900 text-sm sm:text-base leading-snug">{q.question}</p>
        <p className="text-xs text-ink-500 leading-relaxed">{q.rationale}</p>
      </div>

      {q.answers.length > 0 && (
        <ul className="space-y-1.5 pt-1" aria-label="Answers">
          {q.answers.map((a) => (
            <li key={a.id} className="rounded-xl bg-sand-50/80 border border-sand-200/60 p-2.5 text-xs">
              <strong className="text-ink-900">{a.member_name ?? "Someone"}:</strong>{" "}
              <span className="text-ink-700">{a.answer_text}</span>
            </li>
          ))}
        </ul>
      )}

      {problem && <p role="alert" className="rounded-xl bg-coral-50 border border-coral-200 p-2 text-xs text-coral-800">{problem}</p>}

      {q.can_answer && (
        <div className="space-y-2.5 pt-2 border-t border-sand-100">
          {(q.suggested_options ?? []).length > 0 && (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Suggested answers">
              {(q.suggested_options ?? []).map((o) => (
                <button
                  key={o}
                  type="button"
                  aria-pressed={option === o}
                  onClick={() => {
                    setOption(option === o ? null : o);
                    if (option !== o) setText(o);
                  }}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                    option === o
                      ? "border-sea-600 bg-sea-600 text-white shadow-2xs"
                      : "border-sand-200 bg-sand-50/60 text-ink-700 hover:border-sand-300 hover:bg-white"
                  }`}
                >
                  {o}
                </button>
              ))}
            </div>
          )}

          <textarea
            aria-label={`Your answer to question ${q.id}`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={2000}
            rows={2}
            placeholder="Type your response here..."
            className="input w-full text-xs"
          />

          <div className="flex items-center gap-3">
            <button
              disabled={busy !== null || text.trim() === ""}
              onClick={() => void send("answer")}
              className="btn btn-primary px-3.5 py-1.5 text-xs font-semibold shadow-2xs disabled:opacity-50 flex items-center gap-1.5"
            >
              <Send className="w-3 h-3" />
              <span>{busy === "answer" ? "Sending..." : "Send answer"}</span>
            </button>
          </div>
        </div>
      )}

      {isLead && q.status === "OPEN" && (
        <div className="pt-1">
          <button
            disabled={busy !== null}
            onClick={() => void send("skip")}
            className="text-2xs font-semibold text-ink-500 hover:text-ink-800 underline transition-colors disabled:opacity-50"
          >
            {busy === "skip" ? "Skipping..." : "Skip this question"}
          </button>
        </div>
      )}
    </article>
  );
}
