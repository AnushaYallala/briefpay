"""Project, member and transcript operations (SPEC 6.1, 10). Thin routers call these; they only flush."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Campaign, Pledge, Project, ProjectMember, Transcript, User
from app.services import transcripts as tx
from app.services.state_machines import ProjectService

SPONSOR_EDITABLE = ("DRAFT", "REQUIREMENTS")
FREELANCER_EDITABLE = ("DRAFT", "REQUIREMENTS", "BRD_REVIEW", "CONTRACTING")
TRANSCRIPT_EDITABLE = ("DRAFT", "REQUIREMENTS")
PAYOUT_POLICIES = ("HUMAN", "AUTO_ON_GUARDIAN_ALLOW")


class ProjectError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_project(db: Session, lead: User, *, title: str, summary: str | None, location_label: str | None,
                   budget_cents: int, delivery_days: int | None, payout_release_policy: str,
                   lead_business_name: str | None, lead_business_type: str | None,
                   lead_expected_pledge_cents: int | None) -> Project:
    if payout_release_policy not in PAYOUT_POLICIES:
        raise ProjectError("BAD_POLICY", f"payout_release_policy must be one of {PAYOUT_POLICIES}", 422)
    p = Project(title=title.strip(), summary=summary, location_label=location_label, lead_user_id=lead.id,
                budget_cents=budget_cents, delivery_days=delivery_days, payout_release_policy=payout_release_policy,
                currency="USD", state="DRAFT")
    db.add(p)
    db.flush()
    db.add(ProjectMember(project_id=p.id, user_id=lead.id, role="LEAD", business_name=lead_business_name,
                         business_type=lead_business_type, expected_pledge_cents=lead_expected_pledge_cents,
                         invite_status="VIEWED", joined_at=_now(), last_seen_at=_now()))
    db.flush()
    return p


def upsert_invitees(db: Session, project: Project, invitees: list[dict]) -> list[ProjectMember]:
    """Invite sponsors or the freelancer by email. Idempotent per email; never changes an existing role."""
    emails = [i["email"].lower() for i in invitees]
    if len(set(emails)) != len(emails):
        raise ProjectError("DUPLICATE_INVITEE", "The same email appears twice in this request", 422)
    out = []
    for inv in invitees:
        email, role = inv["email"].lower(), inv["role"]
        if role not in ("SPONSOR", "FREELANCER"):
            raise ProjectError("BAD_ROLE", "role must be SPONSOR or FREELANCER", 422)
        allowed = SPONSOR_EDITABLE if role == "SPONSOR" else FREELANCER_EDITABLE
        if project.state not in allowed:
            raise ProjectError("PROJECT_STATE", f"{role.lower()}s cannot be invited while the project is {project.state}")
        if role == "FREELANCER" and inv.get("expected_pledge_cents"):
            raise ProjectError("BAD_INVITEE", "A freelancer is paid, not a pledger: expected_pledge_cents does not apply", 422)

        user = db.scalars(select(User).where(User.email == email)).first()
        if user is None:
            user = User(email=email, display_name=(inv.get("display_name") or email).strip())
            db.add(user)
            db.flush()
        existing = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project.id,
                                                          ProjectMember.user_id == user.id)).first()
        if existing is not None:
            if existing.role != role:
                raise ProjectError("ROLE_LOCKED", f"{email} is already {existing.role.lower()} on this project; "
                                   "roles cannot be changed (a freelancer must never also be a sponsor)")
            m = existing
        else:
            if role == "FREELANCER" and db.scalars(select(ProjectMember).where(
                    ProjectMember.project_id == project.id, ProjectMember.role == "FREELANCER")).first():
                raise ProjectError("FREELANCER_EXISTS", "This project already has a freelancer invited")
            m = ProjectMember(project_id=project.id, user_id=user.id, role=role, invite_status="INVITED")
            db.add(m)
        for field in ("business_name", "business_type", "expected_pledge_cents"):
            if inv.get(field) is not None:
                setattr(m, field, inv[field])
        if inv.get("display_name") and user.display_name == user.email:
            user.display_name = inv["display_name"].strip()
        out.append(m)
    db.flush()
    return out


def touch_member(db: Session, project_id: int, user_id: int) -> None:
    """A member opening the project counts as 'viewed' (feeds the Strategist's conversion estimate)."""
    m = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id,
                                               ProjectMember.user_id == user_id)).first()
    if m is None:
        return
    m.last_seen_at = _now()
    if m.joined_at is None:
        m.joined_at = _now()
    if m.invite_status == "INVITED":
        m.invite_status = "VIEWED"


def campaign_summary(db: Session, project_id: int) -> dict | None:
    c = db.scalars(select(Campaign).where(Campaign.project_id == project_id).order_by(Campaign.number.desc())).first()
    if c is None:
        return None
    rows = db.execute(select(Pledge.status, Pledge.amount_cents, Pledge.captured_cents).where(
        Pledge.campaign_id == c.id, Pledge.status.in_(("AUTHORIZED", "CAPTURED")))).all()
    pledged = sum(cap if st == "CAPTURED" else amt for st, amt, cap in rows)
    return {"id": c.id, "number": c.number, "state": c.state, "goal_cents": c.goal_cents, "pledged_cents": pledged,
            "pledge_count": len(rows), "deadline_at": c.deadline_at.isoformat() if c.deadline_at else None}


def add_transcript(db: Session, project: Project, user: User, *, source_name: str, raw: bytes | str) -> Transcript:
    """Store the cleaned transcript. The first one moves the project DRAFT -> REQUIREMENTS; later ones supersede it."""
    if project.state not in TRANSCRIPT_EDITABLE:
        raise ProjectError("PROJECT_STATE", f"The transcript can only be changed while the project is DRAFT or "
                           f"REQUIREMENTS (it is {project.state}); the BRD is built from it")
    try:
        name = tx.check_filename(source_name)
        text, lines, digest = tx.normalize(raw, name)
    except tx.TranscriptError as e:
        raise ProjectError(e.code, e.message, 413 if e.code == "TRANSCRIPT_TOO_LARGE" else 422) from e
    t = Transcript(project_id=project.id, uploaded_by=user.id, source_name=name, text=text, line_count=lines, sha256=digest)
    db.add(t)
    db.flush()
    if project.state == "DRAFT":
        ProjectService.transition(db, project, "REQUIREMENTS", actor=f"user:{user.id}", reason="TRANSCRIPT_UPLOADED")
    return t


def latest_transcript(db: Session, project_id: int) -> Transcript | None:
    return db.scalars(select(Transcript).where(Transcript.project_id == project_id).order_by(Transcript.id.desc())).first()


def transcript_count(db: Session, project_id: int) -> int:
    return int(db.scalar(select(func.count()).select_from(Transcript).where(Transcript.project_id == project_id)) or 0)
