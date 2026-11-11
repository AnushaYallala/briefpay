"use client";
import { useEffect, useRef } from "react";
import type { TranscriptResponse } from "@/lib/types";

/** The meeting transcript with line numbers; lines the analyst cited for the chosen item are highlighted and scrolled into view. */
export function TranscriptPanel({
  transcript,
  highlight,
}: {
  transcript: TranscriptResponse;
  highlight: Set<number>;
}) {
  const first = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    first.current?.scrollIntoView?.({ block: "center" });
  }, [highlight]);

  const firstLine = highlight.size > 0 ? Math.min(...highlight) : null;

  return (
    <section
      aria-label="Transcript"
      className="card card-pad bg-white rounded-3xl border border-sand-200 shadow-card sticky top-20 space-y-2"
    >
      <h2 className="font-bold text-ink-900 text-base">Transcript</h2>
      <p className="text-xs text-gray-500 leading-relaxed">
        {transcript.source_name || "Pasted text"} · {transcript.line_count} lines. Choose a source below to see the lines it came from.
      </p>
      <ol
        className="mt-2 max-h-96 overflow-auto font-mono text-xs rounded-xl border border-sand-200 bg-sand-50/50 p-2"
        data-testid="transcript-lines"
      >
        {transcript.lines.map((l) => (
          <li
            key={l.n}
            ref={l.n === firstLine ? first : undefined}
            data-line={l.n}
            data-highlight={highlight.has(l.n) ? "yes" : "no"}
            className={`flex gap-2 px-1 rounded transition-colors ${highlight.has(l.n) ? "bg-yellow-100 font-semibold" : ""}`}
          ><span className="w-8 shrink-0 select-none text-right text-gray-400">{l.n}</span><span className="whitespace-pre-wrap break-words">{l.text}</span></li>
        ))}
      </ol>
    </section>
  );
}
