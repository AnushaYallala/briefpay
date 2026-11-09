"""Campaign endpoints (SPEC 10): setup and launch (lead), public view."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, optional_user, require_member
from app.db import get_db
from app.models import Campaign, Project, ProjectMember, User
from app.services import campaign_ops as ops

router = APIRouter()


class CampaignIn(BaseModel):
    deadline_at: datetime
    close_policy: Literal["EARLY_ON_GOAL", "AT_DEADLINE"] | None = None
    min_pledge_cents: int | None = Field(default=None, ge=0)
    suggested_share_cents: int | None = Field(default=None, ge=0)


def _project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise api_error(404, "PROJECT_NOT_FOUND", "No such project")
    return p


def _campaign(db: Session, campaign_id: int) -> Campaign:
    c = db.get(Campaign, campaign_id)
    if c is None:
        raise api_error(404, "CAMPAIGN_NOT_FOUND", "No such campaign")
    return c


def _viewer(db: Session, project_id: int, user: User | None) -> ProjectMember | None:
    if user is None:
        return None
    return db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)).first()


@router.post("/projects/{project_id}/campaigns", status_code=201)
def create_campaign(project_id: int, body: CampaignIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    lead = require_member(db, project_id, user, ("LEAD",))
    project = _project(db, project_id)
    try:
        c = ops.setup_campaign(db, project, lead, deadline_at=body.deadline_at, close_policy=body.close_policy,
                               min_pledge_cents=body.min_pledge_cents, suggested_share_cents=body.suggested_share_cents)
    except ops.CampaignError as e:
        db.rollback()
        raise api_error(e.status, e.code, e.message) from e
    db.commit()
    return ops.campaign_view(db, c, project, lead)


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> dict:
    """Public view: no emails anywhere. The lead additionally gets launch blockers and the deadline limits."""
    c = _campaign(db, campaign_id)
    project = _project(db, c.project_id)
    return ops.campaign_view(db, c, project, _viewer(db, project.id, user))


@router.post("/campaigns/{campaign_id}/launch")
def launch_campaign(campaign_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    c = _campaign(db, campaign_id)
    lead = require_member(db, c.project_id, user, ("LEAD",))
    project = _project(db, c.project_id)
    try:
        ops.launch(db, project, c)
    except ops.CampaignError as e:
        db.rollback()
        raise api_error(e.status, e.code, e.message) from e
    db.commit()
    return ops.campaign_view(db, c, project, lead)
