"""BA Agent endpoints (SPEC 10): run, view, answer, skip, finalize."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, require_member
from app.config import get_settings
from app.db import get_db
from app.models import BAQuestion, BAScore, Project, ProjectMember, User
from app.services import ba_rounds as rounds
from app.services import ba_service as svc
from app.services.ba_scoring import DIMENSION_NAMES

router = APIRouter()


def raise_ba(e: svc.BAError):
    raise api_error(e.status, e.code, e.message) from e


def score_dict(row: BAScore) -> dict:
    gates = [{"id": k, **v} for k, v in row.gates_json.items() if k.startswith("GT")]
    obs = row.gates_json.get("observations", {})
    return {"round": row.round, "total": row.total, "capped": row.capped, "total_uncapped": row.gates_json.get("total_uncapped"),
            "dimensions": row.dimensions_json, "gates": gates, "requirements": row.extracted_requirements_json,
            "conflicts": row.conflicts_json, "out_of_scope": obs.get("out_of_scope", []),
            "injection_attempts": obs.get("injection_attempts", []), "created_at": row.created_at.isoformat()}


def question_dict(db: Session, q: BAQuestion, viewer: ProjectMember, names: dict[int, str]) -> dict:
    answers = rounds.answers_for(db, q.id)
    return {"id": q.id, "round": q.round, "dimension": q.dimension, "dimension_name": DIMENSION_NAMES.get(q.dimension),
            "question": q.question, "rationale": q.rationale, "addressed_to": q.addressed_to_json,
            "suggested_options": q.suggested_options_json, "status": q.status,
            "answers": [{"id": a.id, "member_id": a.member_id, "member_name": names.get(a.member_id),
                         "answer_text": a.answer_text, "selected_option": a.selected_option} for a in answers],
            "can_answer": q.status == "OPEN" and rounds.can_answer(q, viewer) and all(a.member_id != viewer.id for a in answers)}


def ba_view(db: Session, project: Project, viewer: ProjectMember) -> dict:
    s = svc.get_session(db, project.id)
    settings = get_settings()
    out: dict = {"session": None, "score": None, "history": [], "questions": [], "can_run": False, "can_finalize": False}
    if s is None:
        out["can_run"] = viewer.role == "LEAD" and project.state == "REQUIREMENTS"
        return out
    members = db.execute(select(ProjectMember.id, User.display_name).join(User, User.id == ProjectMember.user_id)
                         .where(ProjectMember.project_id == project.id)).all()
    names = {m_id: n for m_id, n in members}
    scores = list(db.scalars(select(BAScore).where(BAScore.session_id == s.id).order_by(BAScore.id)))
    qs = rounds.session_questions(db, s.id)
    has_open = any(q.status == "OPEN" for q in qs if q.round == s.round)
    out |= {
        "session": {"id": s.id, "state": s.state, "round": s.round, "current_score": s.current_score,
                    "target_score": settings.ba_target_score, "max_rounds": settings.ba_max_rounds},
        "score": score_dict(scores[-1]) if scores else None,
        "history": [{"round": x.round, "total": x.total, "capped": x.capped, "created_at": x.created_at.isoformat()} for x in scores],
        "questions": [question_dict(db, q, viewer, names) for q in qs],
        "can_run": viewer.role == "LEAD" and project.state == "REQUIREMENTS" and not has_open
                   and s.state in ("ACTIVE", "READY"),
        "can_finalize": viewer.role == "LEAD" and s.state == "MAX_ROUNDS",
    }
    return out


@router.post("/projects/{project_id}/ba/run", status_code=202)
def run(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_member(db, project_id, user, ("LEAD",))
    try:
        job_id = rounds.request_run(db, db.get(Project, project_id))
    except svc.BAError as e:
        db.rollback()
        raise_ba(e)
    db.commit()
    return {"job_id": job_id}


@router.get("/projects/{project_id}/ba")
def get_ba(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    viewer = require_member(db, project_id, user)
    return ba_view(db, db.get(Project, project_id), viewer)


class AnswerIn(BaseModel):
    answer_text: str = Field(min_length=1, max_length=2000)
    selected_option: str | None = Field(default=None, max_length=80)


def load_question(db: Session, qid: int, user: User, roles: tuple[str, ...] | None = None) -> tuple[BAQuestion, ProjectMember]:
    q = db.get(BAQuestion, qid)
    if q is None:
        raise api_error(404, "QUESTION_NOT_FOUND", "No such question")
    project_id = db.get(svc.BASession, q.session_id).project_id
    return q, require_member(db, project_id, user, roles)


@router.post("/ba/questions/{question_id}/answers", status_code=201)
def answer(question_id: int, body: AnswerIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    q, member = load_question(db, question_id, user)
    try:
        result = rounds.answer_question(db, q, member, body.answer_text, body.selected_option)
    except svc.BAError as e:
        db.rollback()
        raise_ba(e)
    db.commit()
    return result


@router.post("/ba/questions/{question_id}/skip")
def skip(question_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    q, _ = load_question(db, question_id, user, ("LEAD",))
    try:
        result = rounds.skip_question(db, q)
    except svc.BAError as e:
        db.rollback()
        raise_ba(e)
    db.commit()
    return result


@router.post("/projects/{project_id}/ba/finalize")
def finalize(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_member(db, project_id, user, ("LEAD",))
    project = db.get(Project, project_id)
    try:
        s = rounds.finalize(db, project)
    except svc.BAError as e:
        db.rollback()
        raise_ba(e)
    db.commit()
    return {"state": s.state, "score": s.current_score}
