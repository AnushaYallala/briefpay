"""BRD endpoints (SPEC 10): generate (lead), read (public), download Markdown (public). Approvals arrive with T-15."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, require_member
from app.db import get_db
from app.models import BRD, BRDApproval, Project, User
from app.services import ba_service, brd_service

router = APIRouter()


def _project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise api_error(404, "PROJECT_NOT_FOUND", "No such project")
    return p


def brd_dict(db: Session, brd: BRD) -> dict:
    names = brd_service.member_names(db, brd.project_id)
    approvals = [a for a in db.scalars(select(BRDApproval).where(BRDApproval.brd_id == brd.id).order_by(BRDApproval.id))
                 if a.brd_sha256 == brd.sha256]  # a decision only counts for the exact document the person saw
    decided = {a.member_id for a in approvals}
    sponsors = ba_service.sponsor_members(db, brd.project_id)
    versions = db.execute(select(BRD.version, BRD.status, BRD.sha256).where(BRD.project_id == brd.project_id)
                          .order_by(BRD.version)).all()
    return {"id": brd.id, "version": brd.version, "status": brd.status, "sha256": brd.sha256,
            "score_at_generation": brd.score_at_generation, "content": brd.content_json, "markdown": brd.content_md,
            "open_items": brd.open_items_json,
            "approvals": [{"member_id": a.member_id, "member_name": names.get(a.member_id), "decision": a.decision,
                           "comment": a.comment, "created_at": a.created_at.isoformat()} for a in approvals],
            "awaiting": [{"member_id": m.id, "member_name": names.get(m.id)} for m in sponsors if m.id not in decided],
            "created_at": brd.created_at.isoformat(), "locked_at": brd.locked_at.isoformat() if brd.locked_at else None,
            "versions": [{"version": v, "status": s, "sha256": h} for v, s, h in versions]}


@router.post("/projects/{project_id}/brd/generate", status_code=202)
def generate(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_member(db, project_id, user, ("LEAD",))
    try:
        job_id = brd_service.request_generation(db, _project(db, project_id))
    except brd_service.BRDError as e:
        db.rollback()
        raise api_error(e.status, e.code, e.message) from e
    db.commit()
    return {"job_id": job_id}


@router.get("/projects/{project_id}/brd")
def get_brd(project_id: int, version: int | None = None, db: Session = Depends(get_db)) -> dict:
    """Public by design (SPEC 2: supporters and the public can read the BRD). It contains no emails."""
    _project(db, project_id)
    brd = brd_service.latest_brd(db, project_id, version)
    if brd is None:
        raise api_error(404, "NO_BRD", "No BRD has been generated yet")
    return brd_dict(db, brd)


@router.get("/projects/{project_id}/brd/{version}.md")
def download_markdown(project_id: int, version: int, db: Session = Depends(get_db)) -> Response:
    _project(db, project_id)
    brd = brd_service.latest_brd(db, project_id, version)
    if brd is None:
        raise api_error(404, "NO_BRD", "No such BRD version")
    return Response(brd.content_md, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="brd-v{brd.version}.md"',
                             "X-BRD-SHA256": brd.sha256})
