"""Strategist endpoints (SPEC 10): run (202 job), read, apply. Lead only: it is the lead's planning tool and shows pledge hopes."""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, require_member
from app.db import get_db
from app.models import Campaign, Project, User
from app.services import campaign_ops, jobs
from app.services import strategist_service as svc

router = APIRouter()


class ApplyIn(BaseModel):
    deadline_at: datetime | None = None


def _campaign(db: Session, campaign_id: int, user: User):
    c = db.get(Campaign, campaign_id)
    if c is None:
        raise api_error(404, "CAMPAIGN_NOT_FOUND", "No such campaign")
    lead = require_member(db, c.project_id, user, ("LEAD",))
    return c, db.get(Project, c.project_id), lead


def _fail(e: svc.StrategistError):
    raise api_error(e.status, e.code, e.message) from e


@router.post("/campaigns/{campaign_id}/strategist/run", status_code=202)
def run(campaign_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    c, _, _ = _campaign(db, campaign_id, user)
    if c.state not in ("SETUP", "OPEN"):
        raise api_error(409, "CAMPAIGN_STATE", f"The Strategist advises on campaigns in SETUP or OPEN (this one is {c.state})")
    job = jobs.enqueue(db, "STRATEGIST_RUN", {"campaign_id": c.id})
    db.commit()
    return {"job_id": job.id}


@router.get("/campaigns/{campaign_id}/strategist")
def get_report(campaign_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    c, _, _ = _campaign(db, campaign_id, user)
    r = svc.latest_report(db, c.id)
    if r is None:
        raise api_error(404, "NO_REPORT", "Run the Strategist first")
    return {"id": r.id, "created_at": r.created_at.isoformat(), "forecast": r.forecast_json, "suggestions": r.suggestions_json,
            "narrative": r.narrative_json, "nudges": r.nudges_json}


@router.post("/campaigns/{campaign_id}/strategist/apply")
def apply(campaign_id: int, body: ApplyIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    c, project, lead = _campaign(db, campaign_id, user)
    try:
        svc.apply_deadline(db, c, project, body.deadline_at)
    except svc.StrategistError as e:
        db.rollback()
        _fail(e)
    db.commit()
    return campaign_ops.campaign_view(db, c, project, lead)
