"use client";
import type { ColDef } from "ag-grid-community";
import { AllCommunityModule, ModuleRegistry, themeQuartz } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { Badge } from "@/components/ui";
import { formatMoney } from "@/lib/money";
import { memberName } from "@/lib/verifyview";
import type { BRDRequirementItem, BRDResponse, Member } from "@/lib/types";
import {
  BookOpen,
  CheckCircle2,
  Compass,
  Download,
  FileCode2,
  Globe,
  HelpCircle,
  ListChecks,
  ShieldAlert,
  Sparkles,
  Target,
  Users,
} from "lucide-react";

ModuleRegistry.registerModules([AllCommunityModule]);

type Hint = { type: string; path: string | null; text: string | null };

function describeHint(hint: Hint | null | undefined): string {
  if (!hint) return "";
  if (hint.type === "URL_REACHABLE") return `the page ${hint.path ?? "/"} loads`;
  if (hint.type === "PAGE_CONTAINS") return `the page ${hint.path ?? "/"} contains "${hint.text ?? ""}"`;
  if (hint.type === "FILE_EXISTS") return `the file ${hint.path ?? ""} exists in the repository`;
  if (hint.type === "MOBILE_VIEWPORT") return "the site declares a mobile viewport";
  return hint.type;
}

function priorityTone(p: string): "red" | "blue" | "grey" {
  if (p === "MUST") return "red";
  if (p === "SHOULD") return "blue";
  return "grey";
}

function resolveMemberList(ids: number[], members?: Member[]): string {
  if (!ids.length) return "Not recorded";
  return ids.map((mid) => memberName(members, mid, `Member #${mid}`)).join(", ");
}

function SectionHeading({ num, title, subtitle }: { num: string; title: string; subtitle?: string }) {
  return (
    <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
      <div className="flex items-center gap-2.5">
        <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-md bg-sea-50 px-2 font-mono text-2xs font-bold text-sea-700 border border-sea-200">
          §{num}
        </span>
        <h2 className="text-lg sm:text-xl font-extrabold tracking-tight text-ink-900">{title}</h2>
      </div>
      {subtitle && <span className="text-xs font-medium text-ink-400">{subtitle}</span>}
    </div>
  );
}

/** Publication-grade 12-chapter book view matching the canonical BRD structure safely from typed JSON (never raw HTML). */
export function BrdDocumentBook({
  brd,
  members,
  selectedReq,
  onSelectReq,
  columns,
  downloadHref,
}: {
  brd: BRDResponse;
  members?: Member[];
  selectedReq: BRDRequirementItem | null;
  onSelectReq: (r: BRDRequirementItem | null) => void;
  columns: ColDef<BRDRequirementItem>[];
  downloadHref: string;
}) {
  const c = brd.content;
  const openItems = (c.open_items && c.open_items.length > 0 ? c.open_items : brd.open_items) ?? [];
  const chapters = [
    { id: "brd-sec-1", num: "01", title: "Executive summary", show: true },
    { id: "brd-sec-2", num: "02", title: "Goals & measures", show: true },
    { id: "brd-sec-3", num: "03", title: "Stakeholders", show: Boolean(c.stakeholders?.length) },
    { id: "brd-sec-4", num: "04", title: "Audience", show: Boolean(c.audience) },
    { id: "brd-sec-5", num: "05", title: "Site structure", show: Boolean(c.sitemap?.length) },
    { id: "brd-sec-6", num: "06", title: `Requirements (${c.requirements.length})`, show: true },
    { id: "brd-sec-7", num: "07", title: "Non-functional", show: Boolean(c.non_functional?.length) },
    { id: "brd-sec-8", num: "08", title: "Content ownership", show: Boolean(c.content_responsibilities?.length) },
    { id: "brd-sec-9", num: "09", title: "Constraints", show: Boolean(c.constraints) },
    { id: "brd-sec-10", num: "10", title: "Out of scope", show: true },
    { id: "brd-sec-11", num: "11", title: "Open items", show: true },
    { id: "brd-sec-12", num: "12", title: "Glossary", show: Boolean(c.glossary?.length) },
  ].filter((ch) => ch.show);

  const summaryParagraphs = c.executive_summary
    .split(/\n{2,}|\n/)
    .map((p) => p.trim())
    .filter(Boolean);

  return (
    <div id="brd-book-top" className="grid gap-6 lg:grid-cols-12 items-start">
      {/* Left Sticky Book Table of Contents */}
      <aside
        aria-label="Table of contents"
        className="lg:col-span-3 lg:sticky lg:top-6 rounded-3xl border border-sand-200 bg-white p-5 shadow-card space-y-4"
      >
        <div className="flex items-center justify-between border-b border-sand-100 pb-3">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-sea-700" />
            <h2 className="text-sm font-bold text-ink-900">Contents</h2>
          </div>
          <span className="rounded-full bg-sand-100 px-2.5 py-0.5 font-mono text-2xs font-bold text-ink-600">
            v{brd.version}
          </span>
        </div>

        <nav className="space-y-1">
          {chapters.map((ch) => (
            <a
              key={ch.id}
              href={`#${ch.id}`}
              className="group flex items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-xs font-medium text-ink-600 hover:bg-sea-50 hover:text-sea-800 transition-colors"
            >
              <span className="font-mono text-2xs font-semibold text-ink-400 group-hover:text-sea-600">{ch.num}</span>
              <span className="truncate">{ch.title}</span>
            </a>
          ))}
        </nav>

        <div className="border-t border-sand-100 pt-3 flex flex-col gap-2">
          <a
            href="#brd-matrix"
            className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-sand-200 bg-sand-50 px-3 py-2 text-xs font-semibold text-ink-700 hover:bg-sand-100 transition-colors"
          >
            <ListChecks className="w-3.5 h-3.5 text-sea-700" />
            <span>Interactive Matrix</span>
          </a>
          <a
            href={downloadHref}
            download={`BRD-v${brd.version}.md`}
            className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-sea-200 bg-sea-50/70 px-3 py-2 text-xs font-semibold text-sea-800 hover:bg-sea-100 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download .md</span>
          </a>
        </div>
      </aside>

      {/* Right Bound Specification Book */}
      <article
        aria-label="Specification book"
        className="lg:col-span-9 rounded-3xl border border-sand-200 border-t-4 border-t-sea-700 bg-white shadow-card overflow-hidden"
      >
        {/* Document Title Sheet */}
        <header className="px-6 py-7 sm:px-10 sm:py-9 bg-gradient-to-b from-sand-50/90 via-sand-50/40 to-white border-b border-sand-200 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-2xs font-bold uppercase tracking-widest text-sea-700">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Official Specification · Edition {brd.version}</span>
            </span>
            <span className="rounded-full border border-sand-200 bg-white px-2.5 py-0.5 font-mono text-2xs font-semibold text-ink-500">
              {c.requirements.length} Requirements
            </span>
          </div>

          <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-ink-900 leading-tight">
            {c.title}
          </h2>

          <p className="text-xs sm:text-sm text-ink-500">
            Analysis score <strong className="text-ink-800">{brd.score_at_generation ?? 100}/100</strong>
            {c.constraints && (
              <>
                {" · "}Budget <strong className="text-ink-800">{formatMoney(c.constraints.budget_cents, c.constraints.currency)}</strong>
                {" · "}Delivery{" "}
                <strong className="text-ink-800">
                  {c.constraints.delivery_days ? `${c.constraints.delivery_days} days` : "to be agreed"}
                </strong>
              </>
            )}
            {" · "}
            <strong className="text-ink-800">{c.requirements.length}</strong> Requirements
          </p>
        </header>

        {/* Book Chapters */}
        <div className="px-6 py-6 sm:px-10 sm:py-8 divide-y divide-sand-200/80">
          {/* 1. Executive Summary */}
          <section id="brd-sec-1" aria-label="Executive Summary" className="pb-8 scroll-mt-6 space-y-3">
            <SectionHeading num="1" title="Executive summary" />
            <div className="space-y-3 text-sm sm:text-[15px] text-ink-700 leading-7">
              {summaryParagraphs.map((para, i) => (
                <p key={i}>{para}</p>
              ))}
            </div>
          </section>

          {/* 2. Business Goals & Success Measures */}
          <section id="brd-sec-2" aria-label="Business goals and success measures" className="py-8 scroll-mt-6">
            <SectionHeading num="2" title="Business goals and success measures" />
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="rounded-2xl border border-sand-200 bg-sand-50/50 p-5 space-y-3">
                <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-ink-600">
                  <Target className="w-3.5 h-3.5 text-sea-700" />
                  <span>Goals</span>
                </h3>
                <ul className="space-y-2 text-xs sm:text-sm text-ink-700">
                  {c.business_goals.map((g, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                      <span>{g}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-2xl border border-sand-200 bg-sand-50/50 p-5 space-y-3">
                <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-ink-600">
                  <Compass className="w-3.5 h-3.5 text-sea-700" />
                  <span>How we will know it worked</span>
                </h3>
                {c.success_measures.length > 0 ? (
                  <ul className="space-y-2 text-xs sm:text-sm text-ink-700">
                    {c.success_measures.map((m, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-sea-600 flex-shrink-0" />
                        <span>{m}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-ink-500 italic">No quantitative measures listed.</p>
                )}
              </div>
            </div>
          </section>

          {/* 3. Stakeholders */}
          {c.stakeholders && c.stakeholders.length > 0 && (
            <section id="brd-sec-3" aria-label="Stakeholders" className="py-8 scroll-mt-6">
              <SectionHeading num="3" title="Stakeholders" subtitle={`${c.stakeholders.length} sponsors`} />
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {c.stakeholders.map((s) => {
                  const name = memberName(members, s.member_id, `Member #${s.member_id}`);
                  return (
                    <div key={s.member_id} className="rounded-2xl border border-sand-200 bg-white p-4 shadow-2xs space-y-2.5">
                      <div className="border-b border-sand-100 pb-2">
                        <div className="flex items-center gap-2 font-bold text-sm text-ink-900">
                          <Users className="w-3.5 h-3.5 text-sea-700 flex-shrink-0" />
                          <span>{name}</span>
                        </div>
                        {s.business_name && <p className="text-xs text-ink-500 mt-0.5 pl-5">{s.business_name}</p>}
                      </div>
                      <ul className="space-y-1.5 text-xs text-ink-700 pl-1">
                        {s.needs.map((n, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-sea-500 flex-shrink-0" />
                            <span>{n}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* 4. Audience */}
          {c.audience && (
            <section id="brd-sec-4" aria-label="Audience" className="py-8 scroll-mt-6">
              <SectionHeading num="4" title="Audience" />
              <div className="rounded-2xl border border-sand-200 bg-sand-50/70 p-5 text-sm text-ink-700 leading-relaxed">
                {c.audience}
              </div>
            </section>
          )}

          {/* 5. Site Structure */}
          {c.sitemap && c.sitemap.length > 0 && (
            <section id="brd-sec-5" aria-label="Site structure" className="py-8 scroll-mt-6">
              <SectionHeading num="5" title="Site structure" subtitle={`${c.sitemap.length} route${c.sitemap.length === 1 ? "" : "s"}`} />
              <div className="overflow-hidden rounded-2xl border border-sand-200">
                <table className="w-full text-left border-collapse text-xs sm:text-sm">
                  <thead className="bg-sand-50 border-b border-sand-200 text-2xs font-bold uppercase tracking-wider text-ink-500">
                    <tr>
                      <th className="py-3 px-4 w-36">Page</th>
                      <th className="py-3 px-4">Purpose</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-sand-100">
                    {c.sitemap.map((page, i) => (
                      <tr key={i} className="hover:bg-sand-50/50">
                        <td className="py-3 px-4 align-top">
                          <code className="rounded-md bg-sand-100 border border-sand-200 px-2 py-0.5 font-mono text-xs font-bold text-sea-800">
                            {page.path}
                          </code>
                        </td>
                        <td className="py-3 px-4 text-ink-700 leading-relaxed">{page.purpose}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* 6. Requirements Chapters + Matrix */}
          <section id="brd-sec-6" aria-label="Requirements" className="py-8 scroll-mt-6 space-y-8">
            <div>
              <SectionHeading
                num="6"
                title="Requirements"
                subtitle={`${c.requirements.length} numbered specifications`}
              />

              <div className="space-y-6">
                {c.requirements.map((req) => (
                  <div
                    key={req.code}
                    id={`req-${req.code}`}
                    className="rounded-2xl border border-sand-200 bg-white p-5 sm:p-6 shadow-2xs space-y-4 scroll-mt-6"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-sand-100 pb-3">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-lg bg-sea-50 border border-sea-200 px-2.5 py-0.5 font-mono text-xs font-extrabold text-sea-800">
                            {req.code}
                          </span>
                          <h3 className="text-base font-bold text-ink-900">{req.title}</h3>
                        </div>
                        <p className="text-xs text-ink-500">
                          Weight: <strong className="text-ink-700">{req.weight}/5</strong> · Requested by:{" "}
                          <span className="text-ink-700">{resolveMemberList(req.requested_by, members)}</span>
                        </p>
                      </div>
                      <Badge tone={priorityTone(req.priority)}>{req.priority}</Badge>
                    </div>

                    <p className="text-sm text-ink-700 leading-relaxed">{req.description}</p>

                    <div className="space-y-2.5">
                      <h4 className="text-2xs font-bold uppercase tracking-wider text-ink-500">
                        Acceptance criteria ({req.acceptance_criteria.length})
                      </h4>

                      {req.acceptance_criteria.length === 0 ? (
                        <p className="text-xs text-ink-500 italic">
                          No acceptance criteria (not required at this priority).
                        </p>
                      ) : (
                        <ul className="space-y-2.5">
                          {req.acceptance_criteria.map((ac) => (
                            <li
                              key={ac.id}
                              className="rounded-xl border border-sand-200/90 bg-sand-50/50 p-3.5 text-xs space-y-1.5"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <span className="font-mono font-bold text-ink-900 bg-white border border-sand-200 px-2 py-0.5 rounded-md">
                                  {ac.id}
                                </span>
                                <span className="text-2xs font-medium text-ink-500">
                                  Evidence: {ac.evidence.join(", ")}
                                </span>
                              </div>
                              <p className="text-ink-800 leading-relaxed">
                                <strong>Given</strong> {ac.given}, <strong>when</strong> {ac.when},{" "}
                                <strong>then</strong> {ac.then}.
                              </p>
                              {ac.auto_check_hint && (
                                <p className="flex items-center gap-1.5 text-2xs font-medium text-sea-700 pt-0.5">
                                  <FileCode2 className="w-3.5 h-3.5 flex-shrink-0" />
                                  <span>Automatic check: {describeHint(ac.auto_check_hint)}</span>
                                </p>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>

                    {req.source_refs.length > 0 && (
                      <p className="text-2xs font-mono text-ink-400 pt-1">
                        Source: {req.source_refs.join(", ")}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Interactive Requirements Matrix (AG Grid) */}
            <section
              id="brd-matrix"
              aria-label="Requirements Matrix"
              className="pt-4 border-t border-sand-200 space-y-4 scroll-mt-6"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-ink-900 text-base">Verified Requirements Matrix</h3>
                  <p className="text-xs text-ink-500">
                    Click any row to inspect acceptance criteria and evidence requirements
                  </p>
                </div>
                <span className="rounded-full bg-sand-100 px-3 py-1 text-2xs font-bold text-ink-700">
                  {c.requirements.length} Requirements
                </span>
              </div>

              <div className="rounded-2xl overflow-hidden border border-sand-200 shadow-2xs" style={{ height: "320px", width: "100%" }}>
                <AgGridReact
                  theme={themeQuartz}
                  rowData={c.requirements}
                  columnDefs={columns}
                  rowSelection="single"
                  onRowClicked={(e) => onSelectReq(e.data ?? null)}
                  animateRows
                />
              </div>

              {selectedReq && (
                <div className="rounded-2xl border border-sea-200 bg-sea-50/50 p-4 space-y-3 animate-fade-up">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-sea-700 bg-sea-100 px-2 py-0.5 rounded-lg border border-sea-200">
                        {selectedReq.code}
                      </span>
                      <h4 className="text-sm font-bold text-ink-900">{selectedReq.title}</h4>
                    </div>
                    <span className={`text-xs font-bold ${selectedReq.priority === "MUST" ? "text-red-700" : "text-sea-700"}`}>
                      Priority: {selectedReq.priority}
                    </span>
                  </div>
                  <p className="text-xs text-ink-700 leading-relaxed">{selectedReq.description}</p>
                  <div className="border-t border-sea-200/60 pt-2.5 space-y-2">
                    <span className="text-2xs font-bold uppercase tracking-wider text-ink-500">
                      Acceptance Criteria ({selectedReq.acceptance_criteria.length}):
                    </span>
                    {selectedReq.acceptance_criteria.map((ac) => (
                      <div key={ac.id} className="rounded-xl bg-white p-3 border border-sand-200 text-xs space-y-1 shadow-2xs">
                        <div className="flex items-center justify-between">
                          <span className="font-mono font-bold text-ink-800">{ac.id}</span>
                          <span className="text-2xs text-ink-400">Evidence: {ac.evidence.join(", ")}</span>
                        </div>
                        <p className="text-ink-800 leading-relaxed">
                          <strong>Given</strong> {ac.given} <strong>When</strong> {ac.when} <strong>Then</strong> {ac.then}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          </section>

          {/* 7. Non-functional requirements */}
          {c.non_functional && c.non_functional.length > 0 && (
            <section id="brd-sec-7" aria-label="Non-functional requirements" className="py-8 scroll-mt-6">
              <SectionHeading num="7" title="Non-functional requirements" />
              <ul className="grid gap-2.5 sm:grid-cols-2 text-xs sm:text-sm text-ink-700">
                {c.non_functional.map((nf, i) => (
                  <li key={i} className="flex items-start gap-2.5 rounded-xl border border-sand-200 bg-sand-50/40 px-4 py-3">
                    <CheckCircle2 className="w-4 h-4 text-sea-600 flex-shrink-0 mt-0.5" />
                    <span>{nf}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* 8. Who provides the content */}
          {c.content_responsibilities && c.content_responsibilities.length > 0 && (
            <section id="brd-sec-8" aria-label="Content responsibilities" className="py-8 scroll-mt-6">
              <SectionHeading num="8" title="Who provides the content" />
              <div className="overflow-hidden rounded-2xl border border-sand-200">
                <table className="w-full text-left border-collapse text-xs sm:text-sm">
                  <thead className="bg-sand-50 border-b border-sand-200 text-2xs font-bold uppercase tracking-wider text-ink-500">
                    <tr>
                      <th className="py-3 px-4">Item</th>
                      <th className="py-3 px-4">Provided by</th>
                      <th className="py-3 px-4">Due</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-sand-100">
                    {c.content_responsibilities.map((cr, i) => (
                      <tr key={i} className="hover:bg-sand-50/50">
                        <td className="py-3 px-4 font-medium text-ink-800">{cr.item}</td>
                        <td className="py-3 px-4 text-ink-700">
                          {cr.owner_member_id !== null
                            ? memberName(members, cr.owner_member_id, `Member #${cr.owner_member_id}`)
                            : "To be agreed"}
                        </td>
                        <td className="py-3 px-4 text-ink-500">{cr.due || "To be agreed"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* 9. Constraints */}
          {c.constraints && (
            <section id="brd-sec-9" aria-label="Constraints" className="py-8 scroll-mt-6">
              <SectionHeading num="9" title="Constraints" />
              <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-2xl border border-sand-200 bg-sand-50/50 p-4">
                  <dt className="text-2xs font-bold uppercase tracking-wider text-ink-400">Budget</dt>
                  <dd className="mt-1 text-base font-extrabold text-ink-900">
                    {formatMoney(c.constraints.budget_cents, c.constraints.currency)}
                  </dd>
                </div>
                <div className="rounded-2xl border border-sand-200 bg-sand-50/50 p-4">
                  <dt className="text-2xs font-bold uppercase tracking-wider text-ink-400">Delivery time</dt>
                  <dd className="mt-1 text-base font-extrabold text-ink-900">
                    {c.constraints.delivery_days ? `${c.constraints.delivery_days} days` : "To be agreed"}
                  </dd>
                </div>
                {c.constraints.hosting && (
                  <div className="rounded-2xl border border-sand-200 bg-sand-50/50 p-4">
                    <dt className="text-2xs font-bold uppercase tracking-wider text-ink-400">Hosting</dt>
                    <dd className="mt-1 text-sm font-semibold text-ink-800">{c.constraints.hosting}</dd>
                  </div>
                )}
                {c.constraints.domain && (
                  <div className="rounded-2xl border border-sand-200 bg-sand-50/50 p-4">
                    <dt className="flex items-center gap-1 text-2xs font-bold uppercase tracking-wider text-ink-400">
                      <Globe className="w-3 h-3" />
                      <span>Domain</span>
                    </dt>
                    <dd className="mt-1 text-sm font-mono font-semibold text-ink-800">{c.constraints.domain}</dd>
                  </div>
                )}
              </dl>
            </section>
          )}

          {/* 10. Out of scope */}
          <section id="brd-sec-10" aria-label="Out of scope" className="py-8 scroll-mt-6">
            <SectionHeading num="10" title="Out of scope" />
            {c.out_of_scope && c.out_of_scope.length > 0 ? (
              <ul className="grid gap-2 sm:grid-cols-2 rounded-2xl border border-sand-200 bg-sand-50/60 p-5 text-xs sm:text-sm text-ink-700">
                {c.out_of_scope.map((item, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <ShieldAlert className="w-4 h-4 text-ink-400 flex-shrink-0 mt-0.5" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs sm:text-sm text-ink-500 italic">Nothing has been listed as out of scope.</p>
            )}
          </section>

          {/* 11. Open items */}
          <section id="brd-sec-11" aria-label="Open items" className="py-8 scroll-mt-6">
            <SectionHeading num="11" title="Open items" />
            {openItems.length > 0 ? (
              <ul className="space-y-2 rounded-2xl border border-amber-200 bg-amber-50/60 p-5 text-xs sm:text-sm text-amber-950">
                {openItems.map((item, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <HelpCircle className="w-4 h-4 text-amber-700 flex-shrink-0 mt-0.5" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 px-5 py-4 text-xs sm:text-sm text-emerald-900 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span>None. The analysis found nothing left to settle.</span>
              </div>
            )}
          </section>

          {/* 12. Glossary */}
          {c.glossary && c.glossary.length > 0 && (
            <section id="brd-sec-12" aria-label="Glossary" className="pt-8 pb-2 scroll-mt-6">
              <SectionHeading num="12" title="Glossary" />
              <dl className="divide-y divide-sand-100 rounded-2xl border border-sand-200 bg-sand-50/30">
                {c.glossary.map((entry, i) => (
                  <div key={i} className="grid gap-1 sm:grid-cols-4 px-5 py-3.5 text-xs sm:text-sm">
                    <dt className="font-bold text-ink-900">{entry.term}</dt>
                    <dd className="sm:col-span-3 text-ink-700 leading-relaxed">{entry.definition}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}
        </div>

        {/* Book End Colophon */}
        <footer className="px-6 py-4 sm:px-10 bg-sand-50 border-t border-sand-200 flex flex-wrap items-center justify-between gap-3 text-xs text-ink-500">
          <span>
            End of Business Requirements Document · v{brd.version} · Fingerprint{" "}
            <code className="font-mono text-2xs">{brd.sha256.substring(0, 12)}...</code>
          </span>
          <a href="#brd-book-top" className="font-semibold text-sea-700 hover:underline">
            Back to top ↑
          </a>
        </footer>
      </article>
    </div>
  );
}
