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
    <section
      aria-label="Score"
      className="card card-pad bg-white rounded-3xl border border-sand-200 shadow-card space-y-4"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-2xs font-bold uppercase tracking-wider text-ink-400">
            Requirements Completeness Score
          </div>
          <p className="mt-0.5">
            <span
              className={`text-5xl sm:text-6xl font-extrabold tracking-tight ${
                reached ? "text-green-700" : "text-ink-900"
              }`}
              data-testid="score"
            >
              {total}
            </span>
            <span className="text-xl font-medium text-ink-400"> / 100</span>
          </p>
        </div>
        <Badge tone={st.tone}>{st.label}</Badge>
      </div>

      <div
        className="relative h-3.5 w-full rounded-full bg-sand-200 overflow-visible"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={total}
        aria-label="Score"
      >
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            reached ? "bg-green-600" : "bg-sea-500"
          }`}
          style={{ width: `${percent(total / 100)}%` }}
          data-testid="score-bar"
        />
        <div
          className="absolute -top-1.5 h-6 w-1 rounded-full bg-ink-900 shadow-xs"
          style={{ left: `${percent(s.target_score / 100)}%` }}
          data-testid="target-line"
          title={`The line: ${s.target_score}`}
        />
      </div>

      <div className="space-y-1 text-sm text-ink-600">
        <p>
          The brief can be written once the score reaches <strong>{s.target_score}</strong>. {st.hint}
        </p>
        <p className="text-xs text-ink-400">
          Round {s.round} of up to {s.max_rounds}.
        </p>
      </div>

      {view.score?.capped && (
        <p
          className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs sm:text-sm text-amber-900 font-medium shadow-2xs"
          data-testid="capped"
        >
          A red check below holds the score at 89
          {view.score.total_uncapped !== null ? ` (it would be ${view.score.total_uncapped})` : ""}. Fix it to get past the line.
        </p>
      )}

      {view.history.length > 0 && (
        <div className="pt-2 border-t border-sand-100">
          <p className="text-2xs font-bold uppercase tracking-wider text-ink-400">
            Score after each round
          </p>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="mt-2 h-16 w-full max-w-sm rounded-lg bg-sand-50/50 p-1"
            role="img"
            aria-label={`Score history: ${view.history.map((h) => h.total).join(", ")}`}
          >
            <line
              x1="0"
              x2={W}
              y1={sparkY(s.target_score, H)}
              y2={sparkY(s.target_score, H)}
              stroke="#cbd5e1"
              strokeDasharray="4 3"
            />
            <polyline
              points={sparkPoints(view.history, W, H)}
              fill="none"
              stroke="#0d9488"
              strokeWidth="2.5"
              data-testid="spark"
            />
          </svg>
          <p className="mt-1.5 text-xs text-ink-700 font-medium" data-testid="history">
            {view.history.map((h) => `Round ${h.round}: ${h.total}`).join(" · ")}
          </p>
        </div>
      )}
    </section>
  );
}
