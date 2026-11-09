"""Submission endpoints (SPEC 10): submit work (freelancer), read one, list a project's attempts (members)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, require_member
from app.db import get_db
from app.models import Contract, Project, Submission, User
from app.services import failure_decisions as fd
from app.services import submission_service as svc
from app.services import verify_judge as vj

router = APIRouter()


class SubmissionIn(BaseModel):
    repo_url: str = Field(max_length=500)
    commit_sha: str = Field(max_length=64)
    deployed_url: str = Field(max_length=500)
    notes: str | None = Field(default=None, max_length=5000)


@router.post("/projects/{project_id}/submissions", status_code=202)
def submit(project_id: int, body: SubmissionIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise api_error(404, "PROJECT_NOT_FOUND", "No such project")
    member = require_member(db, project_id, user, ("FREELANCER",))
    try:
        sub, job = svc.create_submission(db, project, member, repo_url=body.repo_url, commit_sha=body.commit_sha,
                                         deployed_url=body.deployed_url, notes=body.notes)
    except svc.SubmissionError as e:
        db.rollback()
        raise api_error(e.status, e.code, e.message) from e
    db.commit()
    return {"submission_id": sub.id, "attempt_no": sub.attempt_no, "job_id": job.id}


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise api_error(404, "SUBMISSION_NOT_FOUND", "No such submission")
    require_member(db, db.get(Contract, sub.contract_id).project_id, user)
    return svc.submission_view(db, sub)


@router.post("/submissions/{submission_id}/judge", status_code=202)
def judge(submission_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise api_error(404, "SUBMISSION_NOT_FOUND", "No such submission")
    member = require_member(db, db.get(Contract, sub.contract_id).project_id, user, ("FREELANCER", "LEAD"))
    try:
        job = vj.request_judge(db, sub, member)
    except vj.JudgeError as e:
        db.rollback()
        raise api_error(e.status, e.code, e.message) from e
    db.commit()
    return {"job_id": job.id, "submission_id": sub.id}


class ExtendIn(BaseModel):
    extra_attempts: int = Field(ge=1, le=10)
    note: str | None = Field(default=None, max_length=1000)


class OverrideIn(BaseModel):
    decision: str = Field(max_length=10)
    note: str | None = Field(default=None, max_length=1000)


def _failed_submission(db: Session, submission_id: int, user: User, roles: tuple[str, ...] | None):
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise api_error(404, "SUBMISSION_NOT_FOUND", "No such submission")
    return sub, require_member(db, db.get(Contract, sub.contract_id).project_id, user, roles)


def _decide(db: Session, fn, *args):
    try:
        out = fn(db, *args)
    except fd.DecisionError as e:
        db.rollback()
        raise api_error(e.status, e.code, e.message) from e
    db.commit()
    return out


@router.get("/submissions/{submission_id}/failure-options")
def failure_options(submission_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    sub, member = _failed_submission(db, submission_id, user, None)
    return fd.options(db, sub, member.project_id)


@router.post("/submissions/{submission_id}/extend")
def extend_attempts(submission_id: int, body: ExtendIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    sub, member = _failed_submission(db, submission_id, user, ("LEAD",))
    return _decide(db, fd.extend, sub, member, body.extra_attempts, body.note)


@router.post("/submissions/{submission_id}/cancel-refund", status_code=201)
def cancel_and_refund(submission_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    sub, member = _failed_submission(db, submission_id, user, ("LEAD",))
    plan = _decide(db, fd.cancel_refund, sub, member)
    return {"plan_id": plan.id, "kind": plan.kind, "state": plan.state}


@router.post("/submissions/{submission_id}/override")
def override_verification(submission_id: int, body: OverrideIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    sub, member = _failed_submission(db, submission_id, user, ("LEAD", "SPONSOR"))
    return _decide(db, fd.vote_override, sub, member, body.decision, body.note)


@router.get("/projects/{project_id}/submissions")
def list_submissions(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if db.get(Project, project_id) is None:
        raise api_error(404, "PROJECT_NOT_FOUND", "No such project")
    require_member(db, project_id, user)
    return {"submissions": [{"id": s.id, "attempt_no": s.attempt_no, "state": s.state, "commit_sha": s.commit_sha,
                             "deployed_url": s.deployed_url, "created_at": s.created_at.isoformat()}
                            for s in svc.project_submissions(db, project_id)]}
