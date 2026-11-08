"""BRD approvals (SPEC 7.2, 6.1): hash-bound, unanimous; a rejection reopens the BA conversation.

Every sponsor (the lead is also a sponsor) decides on the exact document hash they saw. All APPROVE -> the BRD locks and
the project moves to CONTRACTING. Any REJECT (with a comment) -> the comment becomes a new BA question for everyone, the
project returns to REQUIREMENTS and the next BRD will be version + 1. Flushes only; the caller owns the transaction.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BRD, BAQuestion, BRDApproval, Project, ProjectMember, User
from app.services import ba_service, ledger
from app.services.brd_service import BRDError
from app.services.state_machines import ProjectService

MAX_COMMENT = 1000
REVISION_DIMENSION = "BRD"  # a question raised by a rejection belongs to no rubric dimension


def _now() -> datetime:
    return datetime.now(timezone.utc)


def voters(db: Session, project_id: int) -> list[ProjectMember]:
    return ba_service.sponsor_members(db, project_id)


def decisions_on(db: Session, brd: BRD) -> list[BRDApproval]:
    """Only decisions made on this document's exact hash count."""
    return [a for a in db.scalars(select(BRDApproval).where(BRDApproval.brd_id == brd.id).order_by(BRDApproval.id))
            if a.brd_sha256 == brd.sha256]


def decide(db: Session, project: Project, brd: BRD, member: ProjectMember, decision: str, brd_sha256: str,
           comment: str | None) -> dict:
    if decision not in ("APPROVE", "REJECT"):
        raise BRDError("BAD_DECISION", "decision must be APPROVE or REJECT", 422)
    if member.role not in ("LEAD", "SPONSOR"):
        raise BRDError("FORBIDDEN", "Only the sponsors (including the lead) vote on the BRD", 403)
    if project.state != "BRD_REVIEW":
        raise BRDError("PROJECT_STATE", f"The BRD can be approved or rejected while the project is in BRD_REVIEW (it is {project.state})")
    if brd.status != "PENDING_APPROVAL":
        raise BRDError("BRD_CLOSED", f"BRD v{brd.version} is {brd.status} and can no longer be decided")
    if brd_sha256 != brd.sha256:
        raise BRDError("HASH_MISMATCH", "That is not the document you are deciding on: the hash differs. Reload the BRD and read it again.")
    comment = (comment or "").strip()
    if decision == "REJECT" and not comment:
        raise BRDError("COMMENT_REQUIRED", "Say what should change: a rejection needs a comment", 422)
    if len(comment) > MAX_COMMENT:
        raise BRDError("COMMENT_TOO_LONG", f"Keep the comment under {MAX_COMMENT} characters", 422)

    existing = db.scalars(select(BRDApproval).where(BRDApproval.brd_id == brd.id, BRDApproval.member_id == member.id)).first()
    if existing is not None and existing.decision == decision == "APPROVE":
        return _summary(db, project, brd, changed=False)                       # a repeated click changes nothing
    if existing is not None:                                                    # an approver may withdraw by rejecting
        existing.decision, existing.comment, existing.brd_sha256, existing.created_at = decision, comment or None, brd.sha256, _now()
    else:
        db.add(BRDApproval(brd_id=brd.id, member_id=member.id, decision=decision, comment=comment or None, brd_sha256=brd.sha256))
    db.flush()
    actor = f"user:{db.get(ProjectMember, member.id).user_id}"
    ledger.append(db, project.id, "APPROVAL", actor=actor, ref_type="brd", ref_id=brd.id,
                  meta={"decision": decision, "brd_version": brd.version, "brd_sha256": brd.sha256, "comment": comment or None})

    if decision == "REJECT":
        _reopen_requirements(db, project, brd, member, comment)
    elif all(any(a.member_id == v.id and a.decision == "APPROVE" for a in decisions_on(db, brd)) for v in voters(db, project.id)):
        _lock(db, project, brd)
    return _summary(db, project, brd, changed=True)


def _lock(db: Session, project: Project, brd: BRD) -> None:
    brd.status, brd.locked_at = "APPROVED", _now()
    ledger.append(db, project.id, "BRD_LOCKED", actor="system", ref_type="brd", ref_id=brd.id,
                  meta={"brd_version": brd.version, "brd_sha256": brd.sha256})
    ProjectService.transition(db, project, "CONTRACTING", actor="system", reason=f"BRD v{brd.version} approved by every sponsor")


def _reopen_requirements(db: Session, project: Project, brd: BRD, member: ProjectMember, comment: str) -> None:
    brd.status = "SUPERSEDED"
    session = ba_service.get_or_create_session(db, project)
    name = db.get(User, member.user_id).display_name
    session.round += 1
    session.state = "ACTIVE"
    db.add(BAQuestion(
        session_id=session.id, round=session.round, dimension=REVISION_DIMENSION,
        question=f'{name} asked for changes to BRD v{brd.version}: "{comment}" How should the document change?',
        rationale="Raised when a sponsor rejected the BRD; the next version must settle it.",
        addressed_to_json=["ALL"], suggested_options_json=None, status="OPEN"))
    ProjectService.transition(db, project, "REQUIREMENTS", actor=f"user:{member.user_id}",
                              reason=f"BRD v{brd.version} rejected")
    db.flush()


def _summary(db: Session, project: Project, brd: BRD, *, changed: bool) -> dict:
    required = voters(db, project.id)
    approved = {a.member_id for a in decisions_on(db, brd) if a.decision == "APPROVE"}
    return {"changed": changed, "brd_version": brd.version, "brd_status": brd.status, "project_state": project.state,
            "approved": len([v for v in required if v.id in approved]), "required": len(required), "locked": brd.status == "APPROVED"}
