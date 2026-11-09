"""Contract endpoints (SPEC 10): offer (lead), accept (freelancer); read (members) added by D-031."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, require_member
from app.db import get_db
from app.models import Project, User
from app.services import contract_service as svc

router = APIRouter()


class OfferIn(BaseModel):
    amount_cents: int = Field(gt=0)
    delivery_days: int = Field(ge=1, le=90)


class AcceptIn(BaseModel):
    paypal_email: EmailStr
    brd_sha256: str = Field(min_length=64, max_length=64)
    terms_sha256: str = Field(min_length=64, max_length=64)


def _project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise api_error(404, "PROJECT_NOT_FOUND", "No such project")
    return p


@router.post("/projects/{project_id}/contract/offer", status_code=201)
def offer(project_id: int, body: OfferIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_member(db, project_id, user, ("LEAD",))
    try:
        c = svc.offer(db, _project(db, project_id), body.amount_cents, body.delivery_days)
    except svc.ContractError as e:
        db.rollback()
        raise api_error(e.status, e.code, e.message) from e
    db.commit()
    return svc.contract_view(db, c, show_email=True)


@router.get("/projects/{project_id}/contract")
def get_contract(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Members only. The PayPal email is visible to members once it is locked in by signing."""
    require_member(db, project_id, user)
    c = svc.get_contract(db, project_id)
    if c is None:
        raise api_error(404, "NO_CONTRACT", "No contract has been offered yet")
    return svc.contract_view(db, c, show_email=True)


@router.post("/projects/{project_id}/contract/accept")
def accept(project_id: int, body: AcceptIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    member = require_member(db, project_id, user, ("FREELANCER",))
    try:
        c = svc.accept(db, _project(db, project_id), member, str(body.paypal_email), body.brd_sha256, body.terms_sha256)
    except svc.ContractError as e:
        db.rollback()
        raise api_error(e.status, e.code, e.message) from e
    db.commit()
    return svc.contract_view(db, c, show_email=True)
