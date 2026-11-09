"""MoneyExecutor: the ONLY code allowed to call PayPal write endpoints (SPEC 7.6, 8.5, 12).

It refuses anything that is not an approved, Guardian-reviewed, hash-identical plan, then sends exactly the
plan's steps with each step's idempotency key as the PayPal request id. It commits as it goes: a step is
marked SENT before the network call so a crash can resume and re-send with the SAME key (PayPal de-duplicates).
It never marks a step CONFIRMED; webhooks / poll fallback do that through plan_lifecycle.confirm_step.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campaign, GuardianReview, MoneyPlan, MoneyPlanStep, PayoutBatch, PayoutItem, PlanApproval, Pledge, Project, Refund
from app.schemas.plans import MoneyPlanSpec
from app.services import plan_builder as pb
from app.services.paypal_io import PayPalWriteError, PayPalWriter
from app.services.plan_lifecycle import fail_step, refresh_plan_state
from app.services.settlement import plan_hash
from app.services.state_machines import CampaignService, ProjectService

MAX_RETRIES = 2  # per step, after the first try; always the same idempotency key


class ExecutionRefused(Exception):
    """The plan is not safe to run. Nothing was sent to PayPal."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _verify_executable(db: Session, plan: MoneyPlan) -> tuple[MoneyPlanSpec, PlanApproval]:
    if plan.state not in ("APPROVED", "EXECUTING"):
        raise ExecutionRefused(f"plan is {plan.state}; only APPROVED (or resuming EXECUTING) plans run")
    approval = db.scalars(select(PlanApproval).where(PlanApproval.plan_id == plan.id, PlanApproval.plan_hash == plan.plan_hash)
                          .order_by(PlanApproval.id.desc())).first()
    if approval is None:
        raise ExecutionRefused("no approval bound to this plan's hash")
    review = db.get(GuardianReview, approval.guardian_review_id)
    if review is None or review.simulated or review.plan_id != plan.id or review.plan_hash != plan.plan_hash:
        raise ExecutionRefused("the approved Guardian review does not belong to this plan hash")
    if review.decision == "BLOCK":
        raise ExecutionRefused("the Guardian blocked this plan")
    if review.decision == "HOLD" and not (approval.ack_note or "").strip():
        raise ExecutionRefused("HOLD without a human acknowledgement note")
    if plan.release_policy == "HUMAN" and not approval.approver.startswith("user:"):
        raise ExecutionRefused("this plan needs a human approval; the system may not approve it")

    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    if plan_hash(spec) != plan.plan_hash:
        raise ExecutionRefused("stored plan does not hash to its plan_hash (tampered)")
    rows = list(db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == plan.id).order_by(MoneyPlanStep.seq)))
    sig = lambda x: (x.seq, x.phase, x.op, x.target_type, x.target_id, x.amount_cents, x.bucket,  # noqa: E731
                     x.receiver_email, x.idempotency_key)
    if [sig(r) for r in rows] != [sig(s) for s in spec.steps]:
        raise ExecutionRefused("step rows differ from the approved plan (a step is missing, extra or altered)")
    return spec, approval


def execute(db: Session, plan_id: int, writer: PayPalWriter, *, now: datetime | None = None) -> MoneyPlan:
    now = now or _now()
    plan = db.get(MoneyPlan, plan_id)
    if plan is None:
        raise ExecutionRefused("no such plan")
    spec, _ = _verify_executable(db, plan)

    if plan.state == "APPROVED":  # first start: G-01 at run time, then enter the executing phase
        try:
            rebuilt = pb.rebuild(db, plan, now)
        except pb.PlanBuildError as e:
            raise ExecutionRefused(f"plan can no longer be built from current data: {e}") from e
        if rebuilt.plan_hash != plan.plan_hash:
            raise ExecutionRefused("plan changed since approval (rebuilt hash differs); build and review a new plan")
        _enter_executing(db, plan)
        db.commit()

    rows = list(db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == plan.id).order_by(MoneyPlanStep.phase, MoneyPlanStep.seq)))
    for phase in sorted({r.phase for r in rows}):
        phase_rows = [r for r in rows if r.phase == phase]
        for step in phase_rows:
            if step.state in ("CONFIRMED", "FAILED"):
                continue
            _send(db, plan, spec, step, writer)
        if any(r.state != "CONFIRMED" for r in phase_rows):
            break  # next phase waits until this one is fully confirmed (webhook or poll)
    refresh_plan_state(db, plan, now=now)
    db.commit()
    return plan


def _enter_executing(db: Session, plan: MoneyPlan) -> None:
    plan.state = "EXECUTING"
    if plan.kind == "CAPTURE_PLEDGES":
        CampaignService.transition(db, db.get(Campaign, plan.campaign_id), "CAPTURING", actor="system")
    elif plan.kind == "RELEASE_HOLDS":
        camp = db.get(Campaign, plan.campaign_id)
        if camp.state == "OPEN":
            CampaignService.transition(db, camp, "FAILING", actor="system", fail_reason=plan.reason)
    elif plan.kind == "FREELANCER_PAYOUT":
        ProjectService.transition(db, db.get(Project, plan.project_id), "PAYOUT_PENDING", actor="system")
    elif plan.kind == "REFUND_CAPTURED":
        project = db.get(Project, plan.project_id)
        if project.state != "REFUNDING":
            ProjectService.transition(db, project, "REFUNDING", actor="system", reason=plan.reason)


def _send(db: Session, plan: MoneyPlan, spec: MoneyPlanSpec, step: MoneyPlanStep, writer: PayPalWriter) -> None:
    """Mark SENT (committed), call PayPal with the step's key, retry transient errors with the same key."""
    step.state = "SENT"
    db.commit()
    attempts = 0
    while True:
        attempts += 1
        try:
            resp = _call(db, plan, spec, step, writer)
        except PayPalWriteError as e:
            if e.transient and attempts <= MAX_RETRIES:
                continue
            fail_step(db, step, {"message": str(e), "transient": e.transient, "attempts": attempts,
                                 "debug_id": e.debug_id})
            db.commit()
            return
        step.result_json, step.paypal_ref = resp, resp.get("id")
        db.commit()  # stays SENT until PayPal confirms through a webhook or poll
        return


def _call(db: Session, plan: MoneyPlan, spec: MoneyPlanSpec, step: MoneyPlanStep, writer: PayPalWriter) -> dict:
    currency = spec.inputs.get("currency") or db.get(Project, plan.project_id).currency
    key = step.idempotency_key
    if step.op == "CAPTURE_AUTH":
        p = _own_pledge(db, plan, step)
        # final_capture releases whatever part of the hold is left, so a pro-rata partial capture frees the rest (A-8)
        return writer.capture_authorization(p.paypal_authorization_id, step.amount_cents, currency, True, key)
    if step.op == "VOID_AUTH":
        return writer.void_authorization(_own_pledge(db, plan, step).paypal_authorization_id, key)
    if step.op == "REFUND_CAPTURE":
        p = _own_pledge(db, plan, step)
        if not p.paypal_capture_id:
            raise PayPalWriteError("pledge has no capture to refund")
        if not db.scalars(select(Refund).where(Refund.step_id == step.id)).first():
            db.add(Refund(pledge_id=p.id, step_id=step.id, amount_cents=step.amount_cents, reason=plan.reason or "", status="PENDING"))
            db.flush()
        return writer.refund_capture(p.paypal_capture_id, step.amount_cents, currency, key)
    if step.op == "PAYOUT_ITEM":
        batch = db.scalars(select(PayoutBatch).where(PayoutBatch.plan_id == plan.id)).first()
        if batch is None:
            batch = PayoutBatch(plan_id=plan.id, status="PENDING",
                                sender_batch_id=f"briefpay-{plan.project_id}-{plan.id}-{spec.inputs.get('attempt', 0) + 1}")
            db.add(batch)
            db.flush()
        item = db.scalars(select(PayoutItem).where(PayoutItem.step_id == step.id)).first()
        if item is None:
            item = PayoutItem(batch_id=batch.id, step_id=step.id, receiver_email=step.receiver_email,
                              amount_cents=step.amount_cents, sender_item_id=f"tmp-{step.id}", status="PENDING")
            db.add(item)
            db.flush()
            item.sender_item_id = str(item.id)
        db.commit()
        title = db.get(Project, plan.project_id).title
        resp = writer.create_payout_batch(
            batch.sender_batch_id,
            [{"receiver": item.receiver_email, "amount_cents": item.amount_cents, "sender_item_id": item.sender_item_id,
              "note": f"BriefPay: {title}, BRD verified"}],
            currency, f"BriefPay payout: {title}", key)
        batch.paypal_batch_id = resp.get("id")
        return resp
    raise PayPalWriteError(f"{step.op} is not supported by the executor yet")


def _own_pledge(db: Session, plan: MoneyPlan, step: MoneyPlanStep) -> Pledge:
    """Defence in depth: never act on an object that isn't this project's, even if the plan says to."""
    p = db.get(Pledge, step.target_id)
    if p is None or p.project_id != plan.project_id:
        raise PayPalWriteError(f"step {step.seq} targets an object outside this project")
    return p
