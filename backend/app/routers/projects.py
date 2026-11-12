"""Projects, members and transcripts (SPEC 10). Reads are public; emails and private fields are members-only."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, optional_user, require_member
from app.config import get_settings
from app.db import get_db
from app.models import Project, ProjectMember, Transcript, User
from app.services import project_ops as ops
from app.services import transcripts as tx

router = APIRouter()


class InviteeIn(BaseModel):
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=120)
    role: Literal["SPONSOR", "FREELANCER"]
    business_name: str | None = Field(default=None, max_length=200)
    business_type: str | None = Field(default=None, max_length=100)
    expected_pledge_cents: int | None = Field(default=None, ge=0, le=100_000_00)


class CreateProjectIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    location_label: str | None = Field(default=None, max_length=200)
    budget_cents: int = Field(ge=0)
    delivery_days: int | None = Field(default=None, ge=1, le=90)
    payout_release_policy: Literal["HUMAN", "AUTO_ON_GUARDIAN_ALLOW"] = "HUMAN"
    lead_business_name: str | None = Field(default=None, max_length=200)
    lead_business_type: str | None = Field(default=None, max_length=100)
    lead_expected_pledge_cents: int | None = Field(default=None, ge=0)
    members: list[InviteeIn] = []


class MembersIn(BaseModel):
    members: list[InviteeIn] = Field(min_length=1, max_length=20)


def raise_project_error(e: ops.ProjectError):
    raise api_error(e.status, e.code, e.message) from e


def viewer_member(db: Session, project_id: int, user: User | None) -> ProjectMember | None:
    if user is None:
        return None
    return db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id,
                                                  ProjectMember.user_id == user.id)).first()


def member_dict(db: Session, m: ProjectMember, viewer: ProjectMember | None) -> dict:
    u = db.get(User, m.user_id)
    out = {"id": m.id, "role": m.role, "display_name": u.display_name, "business_name": m.business_name,
           "business_type": m.business_type}
    if viewer is not None:  # members see each other's contact details and invite status
        out |= {"email": u.email, "invite_status": m.invite_status,
                "last_seen_at": m.last_seen_at.isoformat() if m.last_seen_at else None,
                "paypal_email": m.paypal_email}
    if viewer is not None and viewer.role == "LEAD":  # what an invitee said they'd pledge is the lead's planning data
        out["expected_pledge_cents"] = m.expected_pledge_cents
    return out


def project_card(db: Session, p: Project) -> dict:
    return {"id": p.id, "title": p.title, "summary": p.summary, "location_label": p.location_label, "state": p.state,
            "budget_cents": p.budget_cents, "currency": p.currency, "campaign": ops.campaign_summary(db, p.id)}


def project_detail(db: Session, p: Project, viewer: ProjectMember | None) -> dict:
    out = project_card(db, p)
    members = db.scalars(select(ProjectMember).where(ProjectMember.project_id == p.id).order_by(ProjectMember.id))
    out |= {"delivery_days": p.delivery_days, "payout_release_policy": p.payout_release_policy,
            "created_at": p.created_at.isoformat(), "members": [member_dict(db, m, viewer) for m in members],
            "viewer": {"role": viewer.role, "member_id": viewer.id} if viewer else None}
    if viewer is not None:
        t = ops.latest_transcript(db, p.id)
        out["transcript"] = ({"id": t.id, "source_name": t.source_name, "line_count": t.line_count,
                              "uploaded_at": t.created_at.isoformat()} if t else None)
    return out


@router.post("/projects", status_code=201)
def create_project(body: CreateProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cap = get_settings().payout_max_cents
    if body.budget_cents > cap:
        raise api_error(422, "BUDGET_TOO_HIGH", f"The budget is over the sandbox payout limit of {cap} cents, so the "
                        "freelancer could never be paid")
    try:
        p = ops.create_project(db, user, title=body.title, summary=body.summary, location_label=body.location_label,
                               budget_cents=body.budget_cents, delivery_days=body.delivery_days,
                               payout_release_policy=body.payout_release_policy,
                               lead_business_name=body.lead_business_name, lead_business_type=body.lead_business_type,
                               lead_expected_pledge_cents=body.lead_expected_pledge_cents)
        if body.members:
            ops.upsert_invitees(db, p, [m.model_dump() for m in body.members])
    except ops.ProjectError as e:
        db.rollback()
        raise_project_error(e)
    db.commit()
    return project_detail(db, p, viewer_member(db, p.id, user))


@router.get("/projects")
def list_projects(mine: bool = False, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> dict:
    q = select(Project).order_by(Project.id.desc())
    if mine:
        if user is None:
            raise api_error(401, "UNAUTHENTICATED", "Sign in to list your projects")
        q = q.where(Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)))
    return {"projects": [project_card(db, p) for p in db.scalars(q)]}


@router.get("/projects/{project_id}")
def get_project(project_id: int, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> dict:
    p = db.get(Project, project_id)
    if p is None:
        raise api_error(404, "PROJECT_NOT_FOUND", "No such project")
    viewer = viewer_member(db, p.id, user)
    if viewer is not None:
        ops.touch_member(db, p.id, user.id)
        db.commit()
    return project_detail(db, p, viewer)


@router.put("/projects/{project_id}/members")
def put_members(project_id: int, body: MembersIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_member(db, project_id, user, ("LEAD",))
    p = db.get(Project, project_id)
    try:
        ops.upsert_invitees(db, p, [m.model_dump() for m in body.members])
    except ops.ProjectError as e:
        db.rollback()
        raise_project_error(e)
    db.commit()
    return project_detail(db, p, viewer_member(db, p.id, user))


@router.delete("/projects/{project_id}/members/{member_id}")
def delete_member(project_id: int, member_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_member(db, project_id, user, ("LEAD",))
    p = db.get(Project, project_id)
    try:
        ops.remove_invitee(db, p, member_id)
    except ops.ProjectError as e:
        db.rollback()
        raise_project_error(e)
    db.commit()
    return project_detail(db, p, viewer_member(db, p.id, user))


# ---------------- transcripts ----------------

async def read_transcript_request(request: Request) -> tuple[str, bytes | str]:
    """Accepts JSON {"source_name", "text"} (pasted) or multipart with a `file` part (.txt/.vtt/.md)."""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        f = form.get("file")
        if f is None or not hasattr(f, "read"):
            raise api_error(422, "TRANSCRIPT_NO_FILE", "Send the transcript as a multipart `file` part")
        return f.filename or "", await f.read(tx.MAX_BYTES + 1)
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise api_error(422, "BAD_JSON", "Body must be JSON: {\"text\": \"...\", \"source_name\": \"...\"}") from None
    if not isinstance(body, dict) or not isinstance(body.get("text"), str):
        raise api_error(422, "TRANSCRIPT_NO_TEXT", "Send {\"text\": \"...\"} or upload a file")
    return str(body.get("source_name") or ""), body["text"]


@router.post("/projects/{project_id}/transcripts", status_code=201)
async def upload_transcript(project_id: int, request: Request, user: User = Depends(current_user),
                            db: Session = Depends(get_db)) -> dict:
    require_member(db, project_id, user, ("LEAD",))
    p = db.get(Project, project_id)
    name, raw = await read_transcript_request(request)
    try:
        t = ops.add_transcript(db, p, user, source_name=name, raw=raw)
    except ops.ProjectError as e:
        db.rollback()
        raise_project_error(e)
    db.commit()
    return {"id": t.id, "source_name": t.source_name, "line_count": t.line_count, "sha256": t.sha256,
            "project_state": p.state, "replaced_earlier": ops.transcript_count(db, p.id) > 1}


@router.get("/projects/{project_id}/transcript")
def get_transcript(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Numbered lines for the BA Studio transcript panel (source_refs like L12-L15 point at these numbers)."""
    require_member(db, project_id, user)
    t: Transcript | None = ops.latest_transcript(db, project_id)
    if t is None:
        raise api_error(404, "NO_TRANSCRIPT", "No transcript has been uploaded yet")
    return {"id": t.id, "source_name": t.source_name, "line_count": t.line_count, "sha256": t.sha256,
            "uploaded_at": t.created_at.isoformat(), "lines": tx.numbered(t.text)}
