"""BRD generation (SPEC 7.2): the model drafts, CODE assembles. Everything that must be exact lives here:
REQ codes, AC ids, the 'every MUST is testable' rule, traceability to the analysis, constraints from the project record,
open items from the real score gaps, the Markdown render and the sha256.
"""
import logging
import re
from dataclasses import dataclass

log = logging.getLogger("briefpay.brd")

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.ba_agent import BAInputs
from app.agents.brd_generator import BRDGenerator, BRDInputs
from app.agents.llm_adapter import AgentError
from app.config import get_settings
from app.models import BRD, BRDRequirement as BRDRequirementRow, Project, ProjectMember, User
from app.schemas.brd import AcceptanceCriterion, BRDContent, BRDDraft, BRDRequirement, Constraints, Stakeholder
from app.services import ba_service, project_ops as ops
from app.services.ba_scoring import DIMENSION_NAMES, valid_refs
from app.services.brd_render import content_hash, render_markdown
from app.services.state_machines import ProjectService

PRIORITY_ORDER = {"MUST": 0, "SHOULD": 1, "COULD": 2}
MAX_OPEN_ITEMS = 20


class BRDError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass
class AssembleContext:
    sponsor_ids: set[int]
    sponsor_business: dict[int, str | None]
    line_count: int
    answer_ids: set[int]
    analysis_ids: list[str]            # R1, R2 ... the draft must cover every one
    out_of_scope: list[str]            # from the analysis; always kept
    project: dict                      # budget_cents, currency, delivery_days, title
    code_open_items: list[str]         # computed from the real score gaps


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _dedupe(items: list[str], limit: int | None = None) -> list[str]:
    seen, out = set(), []
    for it in items:
        it = " ".join(it.split())
        if it and _norm(it) not in seen:
            seen.add(_norm(it))
            out.append(it)
    return out[:limit] if limit else out


def open_items_from_score(score_row, *, finalized: bool, target: int) -> list[str]:
    """What is still unsettled, in plain words. A clean READY analysis has none."""
    items = []
    for key, g in score_row.gates_json.items():
        if key.startswith("GT") and not g["passed"]:
            items.append(f"{g['title']}: {g['detail']}")
    unfinished = finalized or score_row.total < target or items
    if unfinished:
        items += [f"{d['name']} is only partly specified." for d in score_row.dimensions_json if d["coverage_effective"] <= 0.5]
    return items


def assemble(draft: BRDDraft, ctx: AssembleContext) -> BRDContent:
    """Turn the model's draft into the canonical BRD or raise BRDError('BRD_INVALID'). Pure."""
    covered = {t for r in draft.requirements for t in r.from_temp_ids}
    missing = [t for t in ctx.analysis_ids if t not in covered]
    if missing:
        raise BRDError("BRD_INVALID", f"The draft dropped analysis requirement(s) {', '.join(missing)}")
    if not any(r.priority == "MUST" for r in draft.requirements):
        raise BRDError("BRD_INVALID", "The draft has no MUST requirement")

    ordered = sorted(enumerate(draft.requirements), key=lambda p: (PRIORITY_ORDER[p[1].priority], p[0]))
    reqs: list[BRDRequirement] = []
    for n, (_, r) in enumerate(ordered, start=1):
        criteria = [AcceptanceCriterion(id=f"AC-{i}", **c.model_dump()) for i, c in enumerate(r.acceptance_criteria, start=1)]
        if r.priority == "MUST" and not criteria:
            raise BRDError("BRD_INVALID", f"MUST requirement '{r.title}' has no acceptance criterion")
        reqs.append(BRDRequirement(
            code=f"REQ-{n:03d}", title=r.title.strip(), description=r.description.strip(), priority=r.priority,
            weight=r.weight, requested_by=sorted({m for m in r.requested_by if m in ctx.sponsor_ids}),
            acceptance_criteria=criteria, source_refs=valid_refs(r.source_refs, ctx.line_count, ctx.answer_ids)))

    # every sponsor appears; a missing one is filled from what they asked for, never invented
    stake = {s.member_id: s for s in draft.stakeholders if s.member_id in ctx.sponsor_ids}
    for mid in sorted(ctx.sponsor_ids):
        if mid not in stake:
            stake[mid] = Stakeholder(member_id=mid, business_name=ctx.sponsor_business.get(mid),
                                     needs=[r.title for r in reqs if mid in r.requested_by])
    stakeholders = [stake[m] for m in sorted(stake)]
    for s in stakeholders:
        s.business_name = s.business_name or ctx.sponsor_business.get(s.member_id)

    responsibilities = [cr.model_copy(update={"owner_member_id": cr.owner_member_id if cr.owner_member_id in ctx.sponsor_ids else None})
                        for cr in draft.content_responsibilities]
    proj = ctx.project
    return BRDContent(
        title=(draft.title or proj["title"]).strip() or proj["title"],
        executive_summary=draft.executive_summary, business_goals=draft.business_goals,
        success_measures=draft.success_measures, stakeholders=stakeholders, audience=draft.audience,
        sitemap=draft.sitemap, requirements=reqs, non_functional=draft.non_functional,
        content_responsibilities=responsibilities,
        constraints=Constraints(budget_cents=proj["budget_cents"], currency=proj["currency"],
                                delivery_days=proj["delivery_days"], hosting=draft.hosting, domain=draft.domain),
        out_of_scope=_dedupe(ctx.out_of_scope + draft.out_of_scope, 20),
        open_items=_dedupe(ctx.code_open_items + draft.open_items, MAX_OPEN_ITEMS),
        glossary=draft.glossary)


# ---------------- database side ----------------

def latest_brd(db: Session, project_id: int, version: int | None = None) -> BRD | None:
    q = select(BRD).where(BRD.project_id == project_id)
    q = q.where(BRD.version == version) if version else q.order_by(BRD.version.desc())
    return db.scalars(q).first()


def member_names(db: Session, project_id: int) -> dict[int, str]:
    rows = db.execute(select(ProjectMember.id, User.display_name, ProjectMember.business_name)
                      .join(User, User.id == ProjectMember.user_id).where(ProjectMember.project_id == project_id)).all()
    return {mid: (f"{name} ({biz})" if biz else name) for mid, name, biz in rows}


def check_ready(db: Session, project: Project):
    """Returns (session, latest score). The project must be in REQUIREMENTS with a READY or FINALIZED analysis."""
    session = ba_service.get_session(db, project.id)
    if project.state != "REQUIREMENTS":
        raise BRDError("PROJECT_STATE", f"A BRD is generated while the project is in REQUIREMENTS (it is {project.state})")
    if session is None or session.state not in ("READY", "FINALIZED"):
        raise BRDError("BA_NOT_READY", "The BA analysis must reach the target score, or be finalized, before a BRD is generated")
    score = ba_service.latest_score(db, session.id)
    if score is None:
        raise BRDError("BA_NOT_READY", "There is no BA score yet")
    return session, score


def store_brd(db: Session, project: Project, content: BRDContent, *, score: int) -> BRD:
    """Store an assembled BRD as the next version (older drafts are superseded): rendered, hashed, with its requirement rows."""
    version = int(db.scalar(select(func.coalesce(func.max(BRD.version), 0)).where(BRD.project_id == project.id)) or 0) + 1
    for old in db.scalars(select(BRD).where(BRD.project_id == project.id, BRD.status.in_(("DRAFT", "PENDING_APPROVAL")))):
        old.status = "SUPERSEDED"
    md = render_markdown(content, version=version, score=score, names=member_names(db, project.id))
    brd = BRD(project_id=project.id, version=version, status="PENDING_APPROVAL", content_json=content.model_dump(mode="json"),
              content_md=md, sha256=content_hash(content), score_at_generation=score,
              open_items_json=content.open_items)
    db.add(brd)
    db.flush()
    for r in content.requirements:
        db.add(BRDRequirementRow(
            brd_id=brd.id, code=r.code, title=r.title, description=r.description, priority=r.priority, weight=r.weight,
            acceptance_criteria_json=[c.model_dump(mode="json") for c in r.acceptance_criteria],
            evidence_types_json=sorted({e for c in r.acceptance_criteria for e in c.evidence}),
            source_refs_json=r.source_refs))
    return brd


def generate_brd(db: Session, project: Project, generator: BRDGenerator) -> BRD:
    """Draft, assemble, render, hash, store. On any failure nothing is stored and no state changes."""
    log.info("[BRD] Preparing to generate BRD for project #%s ('%s')...", project.id, project.title)
    session, score = check_ready(db, project)
    base, meta = ba_service.build_inputs(db, project, session)
    inp = BRDInputs(base=base, requirements=score.extracted_requirements_json, conflicts=score.conflicts_json,
                    out_of_scope=score.gates_json.get("observations", {}).get("out_of_scope", []))
    provider_label = generator.adapter.provider if generator.adapter else "unconfigured"
    log.info("[BRD] Calling AI (%s) with %s analysis requirements and %s transcript lines...",
             provider_label, len(score.extracted_requirements_json), meta["line_count"])
    try:
        draft, _ = generator.draft(inp, project.id)
    except AgentError as e:
        log.error("[BRD] AI drafting failed: %s", e)
        raise BRDError("AI_UNAVAILABLE", f"The BRD Generator could not produce a valid draft: {e}", 503) from e

    log.info("[BRD] AI draft received with %s requirements. Assembling canonical BRD...",
             len(draft.requirements))
    sponsors = ba_service.sponsor_members(db, project.id)
    ctx = AssembleContext(
        sponsor_ids={m.id for m in sponsors}, sponsor_business={m.id: m.business_name for m in sponsors},
        line_count=meta["line_count"], answer_ids=meta["answer_ids"],
        analysis_ids=[r["temp_id"] for r in score.extracted_requirements_json],
        out_of_scope=score.gates_json.get("observations", {}).get("out_of_scope", []),
        project={"title": project.title, "budget_cents": project.budget_cents, "currency": project.currency,
                 "delivery_days": project.delivery_days},
        code_open_items=open_items_from_score(score, finalized=session.state == "FINALIZED",
                                              target=get_settings().ba_target_score))
    content = assemble(draft, ctx)
    brd = store_brd(db, project, content, score=score.total)
    version = brd.version
    session.state = "BRD_GENERATED"
    ProjectService.transition(db, project, "BRD_REVIEW", actor="agent:brd", reason=f"BRD v{version} generated")
    db.flush()
    log.info("[BRD] Stored BRD v%s (SHA-256 fingerprint: %s...). Transitioned project to BRD_REVIEW.",
             version, brd.sha256[:16])
    return brd


def request_generation(db: Session, project: Project) -> int:
    """Lead clicks 'Generate BRD'. Validates now so the user gets an immediate answer, then queues the work."""
    from app.services import jobs
    check_ready(db, project)
    return jobs.enqueue(db, "BRD_GENERATE", {"project_id": project.id}).id


def generate_once(db: Session, project: Project, generator: BRDGenerator) -> dict:
    """Job body. Repeating it is safe: if this analysis already produced a pending BRD, report it instead of making another."""
    if project.state == "BRD_REVIEW":
        existing = latest_brd(db, project.id)
        if existing is not None and existing.status == "PENDING_APPROVAL":
            return {"brd_id": existing.id, "version": existing.version, "sha256": existing.sha256, "already_generated": True}
    brd = generate_brd(db, project, generator)
    return {"brd_id": brd.id, "version": brd.version, "sha256": brd.sha256, "already_generated": False}
