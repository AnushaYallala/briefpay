"""Ledger, money box, AI audit trail and the reconciliation report (SPEC 10). All read-only.

  GET /projects/{id}/ledger      anyone; non-members get the public view (no emails)
  GET /projects/{id}/ledger/paypal-match  members: each PayPal-backed row compared with PayPal's own record
  GET /projects/{id}/money       members
  GET /projects/{id}/agent-runs  members
  GET /admin/reconcile           demo mode only (no admin role exists yet)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, optional_user, require_member
from app.config import get_settings
from app.db import get_db
from app.models import Job, Project, ProjectMember, User
from app.services import jobs, ledger_match, ledger_views, paypal_io, reconcile

router = APIRouter()


def _project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise api_error(404, "PROJECT_NOT_FOUND", "No such project")
    return p


@router.get("/projects/{project_id}/ledger")
def get_ledger(project_id: int, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> dict:
    _project(db, project_id)
    member = user is not None and db.scalars(select(ProjectMember.id).where(
        ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)).first() is not None
    return ledger_views.ledger_rows(db, project_id, public=not member)


@router.get("/projects/{project_id}/ledger/paypal-match")
def get_paypal_match(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db),
                     reader=Depends(paypal_io.get_reader), payout_reader=Depends(paypal_io.get_payout_reader)) -> dict:
    """The 'PayPal match' column: asks PayPal about the project's captures, refunds and payout (read-only, at most 30 lookups)."""
    _project(db, project_id)
    require_member(db, project_id, user)
    return ledger_match.match(db, project_id, reader, payout_reader)


@router.get("/projects/{project_id}/money")
def get_money(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _project(db, project_id)
    require_member(db, project_id, user)
    return ledger_views.money_summary(db, project_id)


@router.post("/projects/{project_id}/money/refresh", status_code=202)
def refresh_money(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """The money screen is open: ask PayPal now about anything still waiting (one such job at a time per project)."""
    _project(db, project_id)
    require_member(db, project_id, user)
    for j in db.scalars(select(Job).where(Job.type == "POLL_STEPS", Job.state.in_(("QUEUED", "RUNNING")))):
        if (j.payload_json or {}).get("project_id") == project_id:
            return {"job_id": j.id, "already_running": True}
    job = jobs.enqueue(db, "POLL_STEPS", {"project_id": project_id, "force": True})
    db.commit()
    return {"job_id": job.id, "already_running": False}


@router.get("/projects/{project_id}/agent-runs")
def get_agent_runs(project_id: int, agent: str | None = Query(default=None, max_length=24),
                   limit: int = Query(default=200, ge=1, le=ledger_views.AGENT_RUN_LIMIT),
                   user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _project(db, project_id)
    require_member(db, project_id, user)
    return ledger_views.agent_runs(db, project_id, agent=agent, limit=limit)


@router.get("/admin/reconcile")
def admin_reconcile(project_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db),
                    reader=Depends(paypal_io.get_reader)) -> dict:
    if not get_settings().demo_mode:
        raise api_error(403, "FORBIDDEN", "The reconciliation report is only available in demo mode")
    return reconcile.report(db, reader=reader, project_id=project_id)
