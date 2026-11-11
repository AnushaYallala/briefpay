"use client";
import Link from "next/link";
import { useState } from "react";
import { CreateProjectModal } from "@/components/CreateProjectModal";
import { ProjectCardView } from "@/components/ProjectCard";
import { Empty, ErrorBox, Loading, StatTile } from "@/components/ui";
import type { ProjectCard } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Plus, Shield, CheckCircle2, Sparkles, Scale, Lock, Search, ArrowRight } from "lucide-react";

export default function Home() {
  const { data, error, loading, slow, reload } = useApi<{ projects: ProjectCard[] }>("/projects");
  const [modalOpen, setModalOpen] = useState(false);
  const [filterQuery, setFilterQuery] = useState("");

  const projects = data?.projects || [];
  const filtered = filterQuery.trim()
    ? projects.filter(
        (p) =>
          p.title.toLowerCase().includes(filterQuery.toLowerCase()) ||
          p.summary?.toLowerCase().includes(filterQuery.toLowerCase()) ||
          p.location_label?.toLowerCase().includes(filterQuery.toLowerCase())
      )
    : projects;

  return (
    <div className="space-y-10 animate-fade-up">
      {/* High-Impact Fintech Hero */}
      <section className="relative overflow-hidden rounded-3xl border border-sand-200 bg-gradient-to-br from-white via-sand-50/50 to-sea-50/40 p-6 sm:p-10 shadow-card">
        {/* Decorative background glow */}
        <div className="absolute top-0 right-0 -mr-20 -mt-20 w-80 h-80 rounded-full bg-sea-200/30 blur-3xl pointer-events-none" />

        <div className="relative z-10 grid gap-8 lg:grid-cols-12 items-center">
          <div className="space-y-5 lg:col-span-8">
            <div className="inline-flex items-center gap-2 rounded-full border border-sea-200 bg-white/90 px-3 py-1 text-xs font-semibold text-sea-800 shadow-2xs">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>Pledge-If: Assurance Contracts on PayPal Authorization Rails</span>
            </div>

            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-ink-900 leading-[1.15]">
              Pledge together. <br className="hidden sm:inline" />
              <span className="text-sea-600">Pay only if we reach the goal.</span>
            </h1>

            <p className="text-base sm:text-lg text-ink-600 max-w-2xl leading-relaxed">
              Local businesses pool resources for shared projects with an all-or-nothing guarantee. Pledges are <strong>authorization holds</strong>, not charges: if the campaign falls short, every hold is released and nobody is charged. Delivered work is autonomously verified before payment.
            </p>

            <div className="flex flex-wrap items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setModalOpen(true)}
                className="btn btn-primary px-5 py-2.5 text-sm font-semibold shadow-xs flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                <span>+ Start Community Initiative</span>
              </button>
              <Link
                href="#how-it-works"
                className="btn btn-secondary px-4 py-2.5 text-sm font-semibold text-ink-700"
              >
                <span>How Pledge-If Works</span>
              </Link>
            </div>

            {/* 4 Trust Feature Tiles */}
            <div className="grid grid-cols-2 gap-3 pt-4 sm:grid-cols-4">
              <div className="rounded-2xl border border-sand-200/80 bg-white/80 p-3.5 shadow-2xs backdrop-blur-xs">
                <div className="text-2xs font-semibold uppercase tracking-wider text-ink-500 flex items-center gap-1">
                  <Lock className="w-3 h-3 text-sea-600" />
                  <span>Hold Guarantee</span>
                </div>
                <div className="mt-1 text-sm font-bold text-ink-900">0% Charged on Miss</div>
              </div>

              <div className="rounded-2xl border border-sand-200/80 bg-white/80 p-3.5 shadow-2xs backdrop-blur-xs">
                <div className="text-2xs font-semibold uppercase tracking-wider text-ink-500 flex items-center gap-1">
                  <Sparkles className="w-3 h-3 text-sea-600" />
                  <span>Requirements</span>
                </div>
                <div className="mt-1 text-sm font-bold text-ink-900">AI BA Scored &ge;90</div>
              </div>

              <div className="rounded-2xl border border-sand-200/80 bg-white/80 p-3.5 shadow-2xs backdrop-blur-xs">
                <div className="text-2xs font-semibold uppercase tracking-wider text-ink-500 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3 text-sea-600" />
                  <span>Deliverables</span>
                </div>
                <div className="mt-1 text-sm font-bold text-ink-900">Vision Verified</div>
              </div>

              <div className="rounded-2xl border border-sand-200/80 bg-white/80 p-3.5 shadow-2xs backdrop-blur-xs">
                <div className="text-2xs font-semibold uppercase tracking-wider text-ink-500 flex items-center gap-1">
                  <Scale className="w-3 h-3 text-sea-600" />
                  <span>Safety Check</span>
                </div>
                <div className="mt-1 text-sm font-bold text-ink-900">13 Guardian Rules</div>
              </div>
            </div>
          </div>

          {/* Cove Illustration Art */}
          <div className="hidden lg:flex lg:col-span-4 items-center justify-center p-4">
            <div className="relative">
              <img
                src="/illustrations/hero-cove.svg"
                alt="Velugu Cove Community"
                className="w-full max-w-sm drop-shadow-md select-none transform hover:scale-[1.02] transition-transform duration-300"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Community Projects Grid Section */}
      <section className="space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-ink-900">
              Community Projects
            </h2>
            <p className="text-xs sm:text-sm text-ink-500 mt-0.5">
              Browse shared initiatives and monitor live funding progress
            </p>
          </div>

          <div className="flex items-center gap-3">
            {projects.length > 0 && (
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-ink-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Filter initiatives..."
                  value={filterQuery}
                  onChange={(e) => setFilterQuery(e.target.value)}
                  className="rounded-xl border border-sand-200 bg-white pl-8 pr-3 py-1.5 text-xs text-ink-800 placeholder:text-ink-400 focus:outline-none focus:ring-2 focus:ring-sea-500/20"
                />
              </div>
            )}
            <button
              type="button"
              onClick={() => setModalOpen(true)}
              className="btn btn-secondary px-3.5 py-1.5 text-xs font-semibold text-ink-700 flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>+ New Initiative</span>
            </button>
          </div>
        </div>

        {loading && <Loading what="Loading projects" slow={slow} />}
        {error && <ErrorBox error={error} onRetry={reload} />}

        {!loading && !error && projects.length === 0 && (
          <div className="space-y-4">
            <Empty title="No projects yet">
              No active projects found. Check back shortly or start a new community initiative.
            </Empty>
            <div className="text-center">
              <button
                type="button"
                onClick={() => setModalOpen(true)}
                className="btn btn-primary px-4 py-2 text-sm font-semibold shadow-xs"
              >
                + Start the First Initiative (Quick Setup)
              </button>
            </div>
          </div>
        )}

        {!loading && !error && projects.length > 0 && (
          <ul className="grid gap-6 sm:grid-cols-2">
            {filtered.map((p) => (
              <ProjectCardView key={p.id} p={p} />
            ))}
          </ul>
        )}
      </section>

      {/* How it Works / Protocol Assurance Cards */}
      <section id="how-it-works" className="pt-6 border-t border-sand-200 space-y-6">
        <div className="text-center max-w-2xl mx-auto space-y-1">
          <span className="eyebrow">Guaranteed Assurance Protocol</span>
          <h2 className="text-2xl font-bold tracking-tight text-ink-900">
            How BriefPay Protects Small Businesses
          </h2>
          <p className="text-xs sm:text-sm text-ink-500">
            Every step is mathematically sealed, autonomously audited, and protected against fraud.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="card card-pad bg-white rounded-2xl border border-sand-200 shadow-2xs space-y-3">
            <div className="w-10 h-10 rounded-xl bg-sea-50 border border-sea-200/60 flex items-center justify-center text-sea-700 font-bold text-sm">
              1
            </div>
            <h3 className="text-sm font-bold text-ink-900">Unanimous BRD Agreement</h3>
            <p className="text-xs text-ink-600 leading-relaxed">
              The AI Business Analyst interviews sponsors until the scope scores &ge;90 with zero unresolved conflicts before any pledge is permitted.
            </p>
          </div>

          <div className="card card-pad bg-white rounded-2xl border border-sand-200 shadow-2xs space-y-3">
            <div className="w-10 h-10 rounded-xl bg-sea-50 border border-sea-200/60 flex items-center justify-center text-sea-700 font-bold text-sm">
              2
            </div>
            <h3 className="text-sm font-bold text-ink-900">Pledge-If Hold Rails</h3>
            <p className="text-xs text-ink-600 leading-relaxed">
              Pledges place temporary authorization holds on PayPal. Zero money moves until 100% of the goal is pledged within the 72-hour window.
            </p>
          </div>

          <div className="card card-pad bg-white rounded-2xl border border-sand-200 shadow-2xs space-y-3">
            <div className="w-10 h-10 rounded-xl bg-sea-50 border border-sea-200/60 flex items-center justify-center text-sea-700 font-bold text-sm">
              3
            </div>
            <h3 className="text-sm font-bold text-ink-900">Vision &amp; Repo Verification</h3>
            <p className="text-xs text-ink-600 leading-relaxed">
              When the builder submits work, Gemini Vision &amp; SSRF-safe checks verify screenshots, Git commits, and test suites against the BRD.
            </p>
          </div>

          <div className="card card-pad bg-white rounded-2xl border border-sand-200 shadow-2xs space-y-3">
            <div className="w-10 h-10 rounded-xl bg-sea-50 border border-sea-200/60 flex items-center justify-center text-sea-700 font-bold text-sm">
              4
            </div>
            <h3 className="text-sm font-bold text-ink-900">13 Guardian Safety Rules</h3>
            <p className="text-xs text-ink-600 leading-relaxed">
              The Payment Guardian audits integer cent math, PayPal balances, and payout accounts before approving execution on PayPal rails.
            </p>
          </div>
        </div>
      </section>

      {/* Create Project Modal */}
      <CreateProjectModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={() => {
          setModalOpen(false);
          void reload();
        }}
      />
    </div>
  );
}
