"""Pledge endpoints (SPEC 10): start a pledge, place the hold, the board. Every rule lives in `pledge_service` / `pledge_gate`."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, optional_user
from app.db import get_db
from app.models import Campaign, ProjectMember, User
from app.services import paypal_io
from app.services import pledge_service as svc

router = APIRouter()


class OrderIn(BaseModel):
    amount_cents: int
    display_name: str | None = Field(default=None, max_length=200)


class AuthorizeIn(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)


def _campaign(db: Session, campaign_id: int) -> Campaign:
    c = db.get(Campaign, campaign_id)
    if c is None:
        raise api_error(404, "CAMPAIGN_NOT_FOUND", "No such campaign")
    return c


def _pledge_dict(p) -> dict:
    return {"id": p.id, "campaign_id": p.campaign_id, "display_name": p.display_name, "amount_cents": p.amount_cents,
            "status": p.status, "order_id": p.paypal_order_id,
            "honor_until": p.honor_until.isoformat() if p.honor_until else None}


def _fail(db: Session, e: svc.PledgeError):
    if e.keep:
        db.commit()      # a declined pledge is remembered as DENIED
    else:
        db.rollback()
    return api_error(e.status, e.code, e.message)


@router.post("/campaigns/{campaign_id}/pledges/order", status_code=201)
def start_pledge(campaign_id: int, body: OrderIn, user: User = Depends(current_user), db: Session = Depends(get_db),
                 orders: paypal_io.OrderGateway = Depends(paypal_io.get_orders)) -> dict:
    c = _campaign(db, campaign_id)
    try:
        p = svc.start_pledge(db, c, user, amount_cents=body.amount_cents, display_name=body.display_name, orders=orders)
    except svc.PledgeError as e:
        raise _fail(db, e) from e
    db.commit()
    return {**_pledge_dict(p), "currency": c.currency}


@router.post("/campaigns/{campaign_id}/pledges/authorize")
def authorize_pledge(campaign_id: int, body: AuthorizeIn, user: User = Depends(current_user), db: Session = Depends(get_db),
                     orders: paypal_io.OrderGateway = Depends(paypal_io.get_orders)) -> dict:
    c = _campaign(db, campaign_id)
    try:
        p = svc.authorize_pledge(db, c, user, order_id=body.order_id, orders=orders)
    except svc.PledgeError as e:
        raise _fail(db, e) from e
    db.commit()
    return _pledge_dict(p)


@router.get("/campaigns/{campaign_id}/pledges")
def list_pledges(campaign_id: int, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> dict:
    """Public board: no emails. The lead of the project also sees payer emails, honor times and unfinished pledges."""
    c = _campaign(db, campaign_id)
    lead = user is not None and db.scalars(select(ProjectMember).where(
        ProjectMember.project_id == c.project_id, ProjectMember.user_id == user.id, ProjectMember.role == "LEAD")).first() is not None
    return {"campaign_id": c.id, "pledges": svc.board(db, c, lead=lead)}
