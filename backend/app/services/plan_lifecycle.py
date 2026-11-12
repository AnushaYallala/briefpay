"""MoneyPlan lifecycle: review -> approve -> (execute) -> confirm (SPEC 7.5.5, 8.4).

PROPOSED -> REVIEWED (ALLOW|HOLD) -> APPROVED -> EXECUTING -> DONE | PARTIAL | FAILED;  BLOCK -> BLOCKED (terminal).
Confirmation (`confirm_step`) is what webhook handlers and poll fallbacks call. It updates step, pledge and
ledger state only and never issues a PayPal write.
"""
import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Campaign, Contract, GuardianReview, MoneyPlan, MoneyPlanStep, PayoutBatch, PayoutItem, PlanApproval, Pledge,
    Project, ProjectMember, Refund,
)
from app.agents.guardian_llm import GuardianLLM
from app.agents.llm_adapter import AgentError
from app.schemas.plans import MoneyPlanSpec
from app.services import guardian_rules as g
from app.services.guardian_decision import combine
from app.services.guardian_facts import build_facts
from app.services import jobs, ledger
from app.services.guardian_tamper import apply_mutation
from app.services.settlement import canonical_json
from app.services.state_machines import CampaignService, ProjectService


class LifecycleError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _review_hash(rules: list[dict], flags: list[dict], decision: str, llm: dict | None) -> str:
    return hashlib.sha256(canonical_json({"rules": rules, "flags": flags, "decision": decision, "llm": llm}).encode()).hexdigest()


# ---------------- review ----------------

def review_plan(db: Session, plan: MoneyPlan, *, reader: g.PayPalReader, params: g.GuardianParams | None = None,
                now: datetime | None = None, llm: GuardianLLM | None = None) -> GuardianReview:
    """Run the Guardian: hard rules first, then (if `llm` is given) the escalate-only AI risk review.

    BLOCK is terminal and the LLM is not consulted. An LLM failure is a HOLD, never a pass. ALLOW on an
    AUTO_ON_ALLOW plan is approved by the system.
    """
    if plan.state not in ("PROPOSED", "REVIEWED"):
        raise LifecycleError("PLAN_STATE", f"plan is {plan.state}; only PROPOSED/REVIEWED plans can be reviewed")
    now = now or _now()
    ev = g.evaluate(db, plan, now=now, reader=reader, params=params)
    rules, flags = [r.as_dict() for r in ev.results], ev.soft_flags

    out, err, run_id = None, None, None
    if llm is not None and ev.decision != "BLOCK":
        try:
            out, run_id = llm.review(build_facts(db, plan, MoneyPlanSpec.model_validate(plan.plan_json), ev), plan.project_id)
        except AgentError as e:
            err, run_id = str(e), getattr(e, "run_id", None)
    decision, llm_record = combine(ev.decision, out, err, llm_expected=llm is not None)

    review = GuardianReview(plan_id=plan.id, plan_hash=plan.plan_hash, rule_results_json=rules, soft_flags_json=flags,
                            llm_review_json=llm_record, decision=decision, simulated=False, agent_run_id=run_id,
                            sha256=_review_hash(rules, flags, decision, llm_record))
    db.add(review)
    db.flush()
    plan.state = "BLOCKED" if decision == "BLOCK" else "REVIEWED"
    ledger.append(db, plan.project_id, "GUARDIAN_DECISION", actor="agent:guardian", ref_type="plan", ref_id=plan.id,
                  meta={"decision": decision, "failed_rules": ev.failed_ids, "flags": [f["id"] for f in flags],
                        "llm": (llm_record or {}).get("status"), "llm_risk": (llm_record or {}).get("risk_level"),
                        "plan_hash": plan.plan_hash, "simulated": False})
    db.flush()
    if decision == "ALLOW" and plan.release_policy == "AUTO_ON_ALLOW":
        approve_plan(db, plan, approver="system:AUTO_ON_ALLOW", plan_hash=plan.plan_hash, guardian_review_id=review.id)
    return review


def simulate_tamper(db: Session, plan: MoneyPlan, mutation: str, *, reader: g.PayPalReader,
                    params: g.GuardianParams | None = None, now: datetime | None = None) -> GuardianReview:
    """DEMO: review a tampered COPY. Stored with simulated=true, can never be approved, never touches PayPal."""
    tampered = apply_mutation(MoneyPlanSpec.model_validate(plan.plan_json), mutation)
    ev = g.evaluate(db, plan, tampered, now=now or _now(), reader=reader, params=params)
    rules, flags = [r.as_dict() for r in ev.results], ev.soft_flags
    review = GuardianReview(plan_id=plan.id, plan_hash=g.plan_hash(tampered), rule_results_json=rules,
                            soft_flags_json=flags, llm_review_json={"simulated_mutation": mutation},
                            decision=ev.decision, simulated=True, sha256=_review_hash(rules, flags, ev.decision, None))
    db.add(review)
    db.flush()
    ledger.append(db, plan.project_id, "GUARDIAN_DECISION", actor="agent:guardian", ref_type="plan", ref_id=plan.id,
                  meta={"decision": ev.decision, "failed_rules": ev.failed_ids, "simulated": True, "mutation": mutation})
    return review


# ---------------- approval ----------------

def _member_role(db: Session, project_id: int, user_id: int) -> str | None:
    m = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id,
                                               ProjectMember.user_id == user_id)).first()
    return m.role if m else None


def latest_review(db: Session, plan_id: int) -> GuardianReview | None:
    return db.scalars(select(GuardianReview).where(GuardianReview.plan_id == plan_id, GuardianReview.simulated.is_(False))
                      .order_by(GuardianReview.id.desc())).first()


def approve_plan(db: Session, plan: MoneyPlan, *, approver: str, plan_hash: str, guardian_review_id: int,
                 ack_note: str | None = None) -> PlanApproval:
    """Hash-bound approval (SPEC 7.5.5 step 3). Enqueues EXECUTE_PLAN."""
    if plan.state == "BLOCKED":
        raise LifecycleError("BLOCKED", "a BLOCKED plan can never be approved; fix the data and rebuild the plan")
    if plan.state != "REVIEWED":
        raise LifecycleError("PLAN_STATE", f"plan is {plan.state}; it must be REVIEWED to approve")
    if plan_hash != plan.plan_hash:
        raise LifecycleError("HASH_MISMATCH", "approval must carry the plan's current plan_hash")
    review = db.get(GuardianReview, guardian_review_id)
    if review is None or review.plan_id != plan.id or review.simulated:
        raise LifecycleError("BAD_REVIEW", "guardian_review_id does not belong to this plan (or is a simulation)")
    if review.plan_hash != plan.plan_hash or latest_review(db, plan.id).id != review.id:
        raise LifecycleError("STALE_REVIEW", "that Guardian review is out of date; review the plan again")
    if review.decision == "BLOCK":
        raise LifecycleError("BLOCKED", "the Guardian blocked this plan")
    if review.decision == "HOLD" and not (ack_note or "").strip():
        raise LifecycleError("ACK_REQUIRED", "a HOLD needs an acknowledgement note from a human approver")

    if approver.startswith("system:"):
        if not (plan.release_policy == "AUTO_ON_ALLOW" and review.decision == "ALLOW"):
            raise LifecycleError("NOT_AUTOMATIC", "the system may only approve AUTO_ON_ALLOW plans the Guardian allowed")
    else:
        if not approver.startswith("user:"):
            raise LifecycleError("BAD_APPROVER", "approver must be user:<id> or system:AUTO_ON_ALLOW")
        role = _member_role(db, plan.project_id, int(approver.split(":", 1)[1]))
        lead_only = plan.kind == "REFUND_CAPTURED" or (review.decision == "HOLD" and plan.kind in ("CAPTURE_PLEDGES", "RELEASE_HOLDS"))
        allowed = ("LEAD",) if lead_only else ("LEAD", "SPONSOR")
        if role not in allowed:
            raise LifecycleError("FORBIDDEN", f"only {' or '.join(a.lower() for a in allowed)} may approve this plan")

    approval = PlanApproval(plan_id=plan.id, plan_hash=plan.plan_hash, guardian_review_id=review.id, approver=approver,
                            ack_note=ack_note)
    db.add(approval)
    plan.state = "APPROVED"
    ledger.append(db, plan.project_id, "APPROVAL", actor=approver, ref_type="plan", ref_id=plan.id,
                  meta={"plan_hash": plan.plan_hash, "decision": review.decision, "ack_note": ack_note})
    jobs.enqueue(db, "EXECUTE_PLAN", {"plan_id": plan.id})
    db.flush()
    return approval


# ---------------- confirmation (called by webhooks / poll fallback) ----------------

def confirm_step(db: Session, step: MoneyPlanStep, *, paypal_ref: str | None = None, now: datetime | None = None) -> None:
    """A PayPal write is proven complete. Idempotent and monotonic: confirming twice changes nothing."""
    if step.state == "CONFIRMED":
        return
    plan = db.get(MoneyPlan, step.plan_id)
    now = now or _now()
    ref = paypal_ref or step.paypal_ref
    if step.op == "CAPTURE_AUTH":
        p = db.get(Pledge, step.target_id)
        p.status, p.captured_cents = "CAPTURED", step.amount_cents
        p.paypal_capture_id = ref or p.paypal_capture_id
        ledger.append(db, plan.project_id, "PLEDGE_CAPTURED", step.amount_cents, actor="paypal", ref_type="pledge",
                      ref_id=p.id, meta={"capture_id": ref, "plan_id": plan.id})
    elif step.op == "VOID_AUTH":
        p = db.get(Pledge, step.target_id)
        p.status = "VOIDED"
        ledger.append(db, plan.project_id, "PLEDGE_VOIDED", actor="paypal", ref_type="pledge", ref_id=p.id,
                      meta={"plan_id": plan.id})
    elif step.op == "PAYOUT_ITEM":
        ledger.append(db, plan.project_id, "PAYOUT_SENT", -step.amount_cents, actor="paypal", ref_type="contract",
                      ref_id=step.target_id, meta={"plan_id": plan.id, "payout_ref": ref})
        for item in db.scalars(select(PayoutItem).where(PayoutItem.step_id == step.id)):
            item.status = "SUCCEEDED"
            db.get(PayoutBatch, item.batch_id).status = "SUCCESS"
    elif step.op == "REFUND_CAPTURE":
        p = db.get(Pledge, step.target_id)
        p.refunded_cents += step.amount_cents
        ledger.append(db, plan.project_id, "REFUND", -step.amount_cents, actor="paypal", ref_type="pledge", ref_id=p.id,
                      meta={"plan_id": plan.id, "refund_id": ref})
        for r in db.scalars(select(Refund).where(Refund.step_id == step.id)):
            r.status, r.paypal_refund_id = "COMPLETED", ref
    else:
        raise LifecycleError("UNSUPPORTED_OP", f"{step.op} is not supported yet")
    step.state, step.paypal_ref = "CONFIRMED", ref
    db.flush()
    refresh_plan_state(db, plan, now=now)


def fail_step(db: Session, step: MoneyPlanStep, error: dict) -> None:
    if step.state == "CONFIRMED":
        return  # monotonic: a confirmed step never goes back
    step.state, step.error_json = "FAILED", error
    if step.op == "PAYOUT_ITEM":  # a failed batch must not look "pending" to G-12, or the retry would be blocked
        for item in db.scalars(select(PayoutItem).where(PayoutItem.step_id == step.id)):
            item.status, item.error_json = "FAILED", error
            db.get(PayoutBatch, item.batch_id).status = "FAILED"
    db.flush()
    refresh_plan_state(db, db.get(MoneyPlan, step.plan_id))


def refresh_plan_state(db: Session, plan: MoneyPlan, *, now: datetime | None = None) -> str:
    """Derive the plan state from its steps and apply the project/campaign effects of finishing."""
    if plan.state != "EXECUTING":  # DONE/PARTIAL/FAILED/BLOCKED are final; nothing pending can remain
        return plan.state
    steps = list(db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == plan.id)))
    if any(s.state in ("PENDING", "SENT") for s in steps):
        plan.state = "EXECUTING"
        return plan.state
    if all(s.state == "CONFIRMED" for s in steps):  # includes an empty release plan
        plan.state = "DONE"
        _on_done(db, plan, now or _now())
    elif any(s.state == "CONFIRMED" for s in steps):
        plan.state = "PARTIAL"
        _on_failed(db, plan)
    else:
        plan.state = "FAILED"
        _on_failed(db, plan)
    ledger.append(db, plan.project_id, "PLAN_EXECUTED", actor="system", ref_type="plan", ref_id=plan.id,
                  meta={"state": plan.state, "kind": plan.kind})
    db.flush()
    return plan.state


def _on_done(db: Session, plan: MoneyPlan, now: datetime) -> None:
    project = db.get(Project, plan.project_id)
    campaign = db.get(Campaign, plan.campaign_id) if plan.campaign_id else None
    if plan.kind == "CAPTURE_PLEDGES":
        CampaignService.transition(db, campaign, "CAPTURED", actor="system")
        ProjectService.transition(db, project, "IN_PROGRESS", actor="system", reason="CAPTURED")
        contract = db.get(Contract, plan.contract_id) if plan.contract_id else None
        if contract:
            contract.effective_at = now  # the conditional contract becomes effective when the capture plan is DONE
    elif plan.kind == "RELEASE_HOLDS":
        CampaignService.transition(db, campaign, "FAILED", actor="system")
        ProjectService.transition(db, project, "CAMPAIGN_FAILED", actor="system", reason=plan.reason)
    elif plan.kind == "FREELANCER_PAYOUT":
        ProjectService.transition(db, project, "PAID", actor="system")
    elif plan.kind == "REFUND_CAPTURED":
        if campaign is None:
            campaign = db.scalars(select(Campaign).where(Campaign.project_id == project.id, Campaign.state == "CAPTURING")
                                  .order_by(Campaign.number.desc())).first()
        if campaign is not None and campaign.state == "CAPTURING":
            CampaignService.transition(db, campaign, "CANCELLED", actor="system")
        ProjectService.transition(db, project, "CANCELLED", actor="system", reason=plan.reason)


def _on_failed(db: Session, plan: MoneyPlan) -> None:
    if plan.kind == "FREELANCER_PAYOUT":
        project = db.get(Project, plan.project_id)
        if project.state == "PAYOUT_PENDING":
            ProjectService.transition(db, project, "PAYOUT_FAILED", actor="system")
    # CAPTURE_PLEDGES stays CAPTURING by design (SPEC 8.6): the lead repairs it; never leave a half-funded IN_PROGRESS.
