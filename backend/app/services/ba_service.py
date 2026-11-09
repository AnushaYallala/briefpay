"""BA scoring orchestration (SPEC 7.1): assemble inputs -> agent judges -> CODE scores -> store. Flushes only."""
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.ba_agent import BAAgent, BAInputs
from app.agents.llm_adapter import AgentError
from app.config import get_settings
from app.models import BAAnswer, BAQuestion, BAScore, BASession, Project, ProjectMember, User
from app.services import project_ops as ops
from app.services import transcripts as tx
from app.services.ba_scoring import ScoreResult, score


class BAError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def get_session(db: Session, project_id: int) -> BASession | None:
    return db.scalars(select(BASession).where(BASession.project_id == project_id).order_by(BASession.id.desc())).first()


def get_or_create_session(db: Session, project: Project) -> BASession:
    s = get_session(db, project.id)
    if s is None:
        s = BASession(project_id=project.id, state="ACTIVE", round=0, current_score=0)
        db.add(s)
        db.flush()
    return s


def sponsor_members(db: Session, project_id: int) -> list[ProjectMember]:
    """The lead is also a sponsor (SPEC 2). Freelancers and supporters have no BRD vote and no needs to capture."""
    return list(db.scalars(select(ProjectMember).where(
        ProjectMember.project_id == project_id, ProjectMember.role.in_(("LEAD", "SPONSOR"))).order_by(ProjectMember.id)))


def qa_pairs(db: Session, session_id: int) -> list[dict]:
    rows = db.execute(select(BAAnswer, BAQuestion).join(BAQuestion, BAQuestion.id == BAAnswer.question_id)
                      .where(BAQuestion.session_id == session_id).order_by(BAAnswer.id)).all()
    return [{"answer_id": a.id, "question_id": q.id, "question": q.question, "member_id": a.member_id,
             "answer": a.answer_text, "selected_option": a.selected_option} for a, q in rows]


def latest_score(db: Session, session_id: int) -> BAScore | None:
    return db.scalars(select(BAScore).where(BAScore.session_id == session_id).order_by(BAScore.id.desc())).first()


def build_inputs(db: Session, project: Project, session: BASession) -> tuple[BAInputs, dict]:
    t = ops.latest_transcript(db, project.id)
    if t is None:
        raise BAError("NO_TRANSCRIPT", "Upload the meeting transcript before running the BA Agent")
    sponsors = sponsor_members(db, project.id)
    names = {u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_([m.user_id for m in sponsors])))}
    qa = qa_pairs(db, session.id)
    prev = latest_score(db, session.id)
    inp = BAInputs(
        round=session.round,
        project={"title": project.title, "summary": project.summary, "location": project.location_label,
                 "budget_cents": project.budget_cents, "delivery_days": project.delivery_days},
        members=[{"member_id": m.id, "name": names.get(m.user_id), "role": m.role, "business_name": m.business_name,
                  "business_type": m.business_type} for m in sponsors],
        transcript_lines=tx.numbered(t.text), qa=qa,
        previous={"requirements": prev.extracted_requirements_json, "conflicts": prev.conflicts_json} if prev else None)
    meta = {"line_count": t.line_count, "answer_ids": {a["answer_id"] for a in qa},
            "sponsor_ids": {m.id for m in sponsors}, "transcript_sha256": t.sha256}
    return inp, meta


def result_to_rows(res: ScoreResult) -> tuple[list[dict], dict]:
    from app.services.ba_scoring import DIMENSION_NAMES
    dims = [{**asdict(d), "name": DIMENSION_NAMES[d.dimension]} for d in res.dimensions]
    gates = {g.id: {"title": g.title, "passed": g.passed, "detail": g.detail} for g in res.gates}
    gates["observations"] = res.observations
    gates["total_uncapped"] = res.total_uncapped
    return dims, gates


def score_round(db: Session, project: Project, agent: BAAgent) -> BAScore:
    """Score the current round. On AI failure nothing changes (SPEC 7.0: BA: no score change)."""
    if project.state != "REQUIREMENTS":
        raise BAError("PROJECT_STATE", f"The BA Agent runs while the project is in REQUIREMENTS (it is {project.state})")
    session = get_or_create_session(db, project)
    if session.state in ("BRD_GENERATED", "FINALIZED"):
        raise BAError("BA_DONE", "This analysis is closed: it was finalized or a BRD was already generated")
    inp, meta = build_inputs(db, project, session)
    try:
        out, run_id = agent.judge(inp, project.id)
    except AgentError as e:
        raise BAError("AI_UNAVAILABLE", f"The BA Agent could not produce a valid analysis: {e}", 503) from e

    res = score(out, line_count=meta["line_count"], answer_ids=meta["answer_ids"], known_member_ids=meta["sponsor_ids"],
                sponsor_member_ids=meta["sponsor_ids"], project_has_budget=project.budget_cents > 0,
                project_has_deadline=project.delivery_days is not None)
    res.observations["transcript_sha256"] = meta["transcript_sha256"]  # lets a re-run tell "same input" from "new upload"
    dims, gates = result_to_rows(res)
    row = BAScore(session_id=session.id, round=session.round, total=res.total, dimensions_json=dims, gates_json=gates,
                  capped=res.capped, extracted_requirements_json=res.requirements, conflicts_json=res.conflicts,
                  agent_run_id=run_id)
    db.add(row)
    session.current_score = res.total
    if session.state not in ("MAX_ROUNDS",):
        session.state = "READY" if res.total >= get_settings().ba_target_score else "ACTIVE"
    db.flush()
    return row
