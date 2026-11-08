"""Money plan endpoints (SPEC 10): list/create/get, review, approve, simulate-tamper."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, require_member
from app.config import get_settings
from app.db import get_db
from app.models import GuardianReview, MoneyPlan, MoneyPlanStep, PlanApproval, User
from app.services import guardian_rules as g
from app.services import paypal_io, plan_builder as pb, plan_lifecycle as lc
from app.services.guardian_tamper import MUTATIONS, TamperError

router = APIRouter()
STATUS = {"FORBIDDEN": 403, "ACK_REQUIRED": 422, "BAD_REVIEW": 422, "BAD_APPROVER": 422, "HASH_MISMATCH": 409,
          "STALE_REVIEW": 409, "BLOCKED": 409, "PLAN_STATE": 409, "NOT_AUTOMATIC": 403}


def params() -> g.GuardianParams:
    s = get_settings()
    return g.GuardianParams(payout_max_cents=s.payout_max_cents, payout_max_per_hour=s.payout_max_per_hour)


def review_dict(r: GuardianReview) -> dict:
    return {"id": r.id, "plan_hash": r.plan_hash, "decision": r.decision, "simulated": r.simulated,
            "rules": r.rule_results_json, "soft_flags": r.soft_flags_json, "llm": r.llm_review_json,
            "created_at": r.created_at.isoformat()}


def plan_dict(db: Session, p: MoneyPlan, detail: bool = False) -> dict:
    out = {"id": p.id, "project_id": p.project_id, "campaign_id": p.campaign_id, "kind": p.kind, "state": p.state,
           "reason": p.reason, "plan_hash": p.plan_hash, "release_policy": p.release_policy,
           "proposed_by": p.proposed_by, "created_at": p.created_at.isoformat()}
    review = lc.latest_review(db, p.id)
    out["decision"] = review.decision if review else None
    if detail:
        steps = db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == p.id).order_by(MoneyPlanStep.seq))
        out["inputs"] = p.plan_json.get("inputs", {})
        out["steps"] = [{"seq": s.seq, "phase": s.phase, "op": s.op, "target_type": s.target_type,
                         "target_id": s.target_id, "amount_cents": s.amount_cents, "bucket": s.bucket,
                         "receiver_email": s.receiver_email, "state": s.state, "paypal_ref": s.paypal_ref,
                         "error": s.error_json} for s in steps]
        out["reviews"] = [review_dict(r) for r in db.scalars(
            select(GuardianReview).where(GuardianReview.plan_id == p.id).order_by(GuardianReview.id.desc()))]
        out["approvals"] = [{"approver": a.approver, "plan_hash": a.plan_hash, "ack_note": a.ack_note,
                             "created_at": a.created_at.isoformat()}
                            for a in db.scalars(select(PlanApproval).where(PlanApproval.plan_id == p.id))]
    return out


def load_plan(db: Session, plan_id: int, user: User, roles: tuple[str, ...] | None = None) -> MoneyPlan:
    plan = db.get(MoneyPlan, plan_id)
    if plan is None:
        raise api_error(404, "PLAN_NOT_FOUND", "No such plan")
    require_member(db, plan.project_id, user, roles)
    return plan


def lifecycle_call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except lc.LifecycleError as e:
        raise api_error(STATUS.get(e.code, 400), e.code, e.message) from e


@router.get("/projects/{project_id}/plans")
def list_plans(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_member(db, project_id, user)
    plans = db.scalars(select(MoneyPlan).where(MoneyPlan.project_id == project_id).order_by(MoneyPlan.id.desc()))
    return {"plans": [plan_dict(db, p) for p in plans]}


class CreatePlanIn(BaseModel):
    kind: str
    reason: str | None = None


@router.post("/projects/{project_id}/plans", status_code=201)
def create_plan(project_id: int, body: CreatePlanIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:
    """Users may only ask for FREELANCER_PAYOUT or REFUND_CAPTURED; capture/release plans are system-built."""
    if body.kind not in ("FREELANCER_PAYOUT", "REFUND_CAPTURED"):
        raise api_error(422, "BAD_KIND", "kind must be FREELANCER_PAYOUT or REFUND_CAPTURED")
    require_member(db, project_id, user, ("LEAD",) if body.kind == "REFUND_CAPTURED" else ("LEAD", "SPONSOR"))
    try:
        built = pb.build(db, body.kind, project_id=project_id, reason=body.reason)
    except pb.PlanBuildError as e:
        raise api_error(409, "CANNOT_BUILD_PLAN", str(e)) from e
    plan = pb.save_proposed(db, built, proposed_by=f"user:{user.id}")
    db.commit()
    return plan_dict(db, plan, detail=True)


@router.get("/plans/{plan_id}")
def get_plan(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return plan_dict(db, load_plan(db, plan_id, user), detail=True)


@router.post("/plans/{plan_id}/review")
def review(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db),
           reader: g.PayPalReader = Depends(paypal_io.get_reader)) -> dict:
    plan = load_plan(db, plan_id, user, ("LEAD", "SPONSOR"))
    lifecycle_call(lc.review_plan, db, plan, reader=reader, params=params())
    db.commit()
    return plan_dict(db, plan, detail=True)


class ApproveIn(BaseModel):
    plan_hash: str
    guardian_review_id: int
    ack_note: str | None = None


@router.post("/plans/{plan_id}/approve")
def approve(plan_id: int, body: ApproveIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    plan = load_plan(db, plan_id, user, ("LEAD", "SPONSOR"))
    lifecycle_call(lc.approve_plan, db, plan, approver=f"user:{user.id}", plan_hash=body.plan_hash,
                   guardian_review_id=body.guardian_review_id, ack_note=body.ack_note)
    db.commit()
    return plan_dict(db, plan, detail=True)


class TamperIn(BaseModel):
    mutation: str


@router.post("/plans/{plan_id}/simulate-tamper")
def simulate_tamper(plan_id: int, body: TamperIn, user: User = Depends(current_user), db: Session = Depends(get_db),
                    reader: g.PayPalReader = Depends(paypal_io.get_reader)) -> dict:
    if not get_settings().demo_mode:
        raise api_error(404, "NOT_FOUND", "Not found")  # demo-only endpoint
    plan = load_plan(db, plan_id, user, ("LEAD", "SPONSOR"))
    if body.mutation not in MUTATIONS:
        raise api_error(422, "BAD_MUTATION", f"mutation must be one of {sorted(MUTATIONS)}")
    try:
        r = lc.simulate_tamper(db, plan, body.mutation, reader=reader, params=params())
    except TamperError as e:
        raise api_error(422, "CANNOT_TAMPER", str(e)) from e
    db.commit()
    return {"simulation": True, "mutation": body.mutation, "review": review_dict(r)}
