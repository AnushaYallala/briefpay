from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import current_user, require_member
from app.db import get_db
from app.models import Campaign, Contract, Job, MoneyPlan, Submission, User

router = APIRouter()


def _job_project_id(db: Session, job: Job) -> int | None:
    payload = job.payload_json or {}
    if payload.get("project_id") is not None:
        return int(payload["project_id"])
    if payload.get("campaign_id") is not None:
        c = db.get(Campaign, payload["campaign_id"])
        return c.project_id if c else None
    if payload.get("plan_id") is not None:
        p = db.get(MoneyPlan, payload["plan_id"])
        return p.project_id if p else None
    if payload.get("submission_id") is not None:
        sub = db.get(Submission, payload["submission_id"])
        c = db.get(Contract, sub.contract_id) if sub else None
        return c.project_id if c else None
    return None


@router.get("/jobs/{job_id}")
def get_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Poll target for 202 responses (SPEC 10). Restricted to authenticated project members when scoped to a project."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, {"error": {"code": "JOB_NOT_FOUND", "message": "No such job", "details": {}}})
    project_id = _job_project_id(db, job)
    if project_id is not None:
        require_member(db, project_id, user)
    # RUNNING-after-retry and QUEUED-with-error both mean "still working" to the UI
    return {"state": job.state, "result": job.result_json, "error": job.last_error, "attempts": job.attempts}
