from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Job

router = APIRouter()


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)) -> dict:
    """Poll target for 202 responses (SPEC 10). TODO(auth): restrict to project members once auth lands."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, {"error": {"code": "JOB_NOT_FOUND", "message": "No such job", "details": {}}})
    # RUNNING-after-retry and QUEUED-with-error both mean "still working" to the UI
    return {"state": job.state, "result": job.result_json, "error": job.last_error, "attempts": job.attempts}
