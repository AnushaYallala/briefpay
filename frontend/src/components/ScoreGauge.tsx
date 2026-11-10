"use client";
import { Badge } from "@/components/ui";
import { percent, sessionState, sparkPoints, sparkY } from "@/lib/ba";
import type { BaView } from "@/lib/types";

const W = 240;
const H = 60;

/** The big score, the line it has to reach, the state of the analysis and the score after each round. */
export function ScoreGauge({ view }: { view: BaView }) {
  const s = view.session;
  if (s === null) return null;
  const st = sessionState(s.state);
  const total = view.score?.total ?? s.current_score;
  const reached = total >= s.target_score;
  return (
    <section aria-label="Score" className="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <p><span className={`text-5xl font-bold ${reached ? "text-green-700" : "text-gray-900"}`} data-testid="score">{total}</span><span className="text-xl text-gray-500"> / 100</span></p>
        <Badge tone={st.tone}>{st.label}</Badge>
      </div>
      <div className="relative h-3 w-full rounded-full bg-gray-200" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={total} aria-label="Score">
        <div className={`h-full rounded-full ${reached ? "bg-green-600" : "bg-sea-500"}`} style={{ width: `${percent(total / 100)}%` }} data-testid="score-bar" />
        <div className="absolute -top-1 h-5 w-0.5 bg-gray-800" style={{ left: `${percent(s.target_score / 100)}%` }} data-testid="target-line" title={`The line: ${s.target_score}`} />
      </div>
      <p className="text-sm text-gray-600">The brief can be written once the score reaches <strong>{s.target_score}</strong>. {st.hint}</p>
      <p className="text-xs text-gray-500">Round {s.round} of up to {s.max_rounds}.</p>
      {view.score?.capped && (
        <p className="rounded bg-amber-50 p-2 text-sm text-amber-800" data-testid="capped">
          A red check below holds the score at 89{view.score.total_uncapped !== null ? ` (it would be ${view.score.total_uncapped})` : ""}. Fix it to get past the line.
        </p>
      )}
      {view.history.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-500">Score after each round</p>
          <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 h-16 w-full max-w-sm" role="img" aria-label={`Score history: ${view.history.map((h) => h.total).join(", ")}`}>
            <line x1="0" x2={W} y1={sparkY(s.target_score, H)} y2={sparkY(s.target_score, H)} stroke="#9ca3af" strokeDasharray="4 3" />
            <polyline points={sparkPoints(view.history, W, H)} fill="none" stroke="#0d9488" strokeWidth="2" data-testid="spark" />
          </svg>
          <p className="text-sm text-gray-700" data-testid="history">{view.history.map((h) => `Round ${h.round}: ${h.total}`).join(" · ")}</p>
        </div>
      )}
    </section>
  );
}
