"""PlanBuilder: pure code that turns DB state into an immutable MoneyPlanSpec (SPEC 7.5.1, 8.3).

Nothing here is chosen by an LLM, nothing here calls PayPal. The Guardian re-runs the builder
(rule G-01) and the executor re-runs it again at execution time; both must get the same plan_hash,
so a plan may only depend on database state and the injected `now`, never on wall-clock side effects.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Campaign, Contract, MoneyPlan, MoneyPlanStep, Pledge, Project, Submission, VerificationReport,
)
from app.schemas.plans import MoneyPlanSpec, PlanStep
from app.services import ledger
from app.services.settlement import (
    SettlementError, idempotency_key, plan_captures, plan_freelancer_payout, plan_hash, plan_refunds,
)

RELEASE_REASONS = {"DEADLINE_MISSED", "LEAD_CANCEL"}
REFUND_REASONS = {"CANCEL_BEFORE_WORK", "VERIFICATION_FAILED_FINAL", "FREELANCER_WITHDREW"}
TERMINAL_PLAN_STATES = {"DONE", "FAILED", "BLOCKED"}


class PlanBuildError(Exception):
    """The database state doesn't allow this plan (wrong phase, missing report, hold lapsed, ...)."""


@dataclass(frozen=True)
class BuiltPlan:
    spec: MoneyPlanSpec
    plan_hash: str


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)  # SQLite returns naive datetimes
    return dt


FAILED_PLAN_STATES = ("FAILED", "PARTIAL", "BLOCKED")


def _attempt(db: Session, spec: MoneyPlanSpec, exclude_plan_id: int | None) -> int:
    """How many earlier plans of this kind/scope ended badly. A retry must be a NEW plan with a NEW hash
    (SPEC 8.6); without this, identical inputs would collide with the failed plan's idempotency keys."""
    q = select(func.count()).select_from(MoneyPlan).where(
        MoneyPlan.kind == spec.kind, MoneyPlan.project_id == spec.project_id,
        MoneyPlan.state.in_(FAILED_PLAN_STATES))
    q = q.where(MoneyPlan.campaign_id == spec.campaign_id) if spec.campaign_id else q
    if exclude_plan_id:
        q = q.where(MoneyPlan.id != exclude_plan_id)
    return int(db.scalar(q) or 0)


def _finalize(db: Session, spec: MoneyPlanSpec, exclude_plan_id: int | None = None) -> BuiltPlan:
    """Hash the plan, then derive each step's idempotency key from the hash (D-021)."""
    attempt = _attempt(db, spec, exclude_plan_id)
    if attempt:  # first attempts keep their original hash
        spec = spec.model_copy(update={"inputs": {**spec.inputs, "attempt": attempt}})
    h = plan_hash(spec)
    steps = [s.model_copy(update={"idempotency_key": idempotency_key(h, s.seq)}) for s in spec.steps]
    return BuiltPlan(spec.model_copy(update={"steps": steps}), h)


def _step(seq: int, op: str, target_type: str, target_id: int, amount: int, bucket: str,
          receiver_email: str | None = None) -> PlanStep:
    return PlanStep(seq=seq, phase=1, op=op, target_type=target_type, target_id=target_id,
                    amount_cents=amount, bucket=bucket, receiver_email=receiver_email, idempotency_key="")


def live_valid_pledges(db: Session, campaign_id: int, now: datetime) -> list[Pledge]:
    """Holds PayPal still guarantees: AUTHORIZED with an authorization id and inside the 3-day honor period.

    Conservative on purpose: a hold past `honor_until` may still capture, but isn't guaranteed (SPEC 9.6).
    """
    rows = db.scalars(select(Pledge).where(Pledge.campaign_id == campaign_id, Pledge.status == "AUTHORIZED")
                      .order_by(Pledge.id))
    return [p for p in rows if p.paypal_authorization_id and p.honor_until and _aware(p.honor_until) > now]


def _contract(db: Session, project_id: int) -> Contract | None:
    return db.scalars(select(Contract).where(Contract.project_id == project_id).order_by(Contract.id.desc())).first()


def _campaign(db: Session, campaign_id: int | None) -> Campaign:
    c = db.get(Campaign, campaign_id) if campaign_id else None
    if c is None:
        raise PlanBuildError("campaign not found")
    return c


# ---------------- the four plan kinds ----------------

def build_capture_pledges(db: Session, campaign_id: int, now: datetime, exclude_plan_id: int | None = None) -> BuiltPlan:
    c = _campaign(db, campaign_id)
    if c.state != "OPEN":
        raise PlanBuildError(f"campaign is {c.state}, not OPEN")
    live = live_valid_pledges(db, c.id, now)
    try:
        caps = plan_captures(c.goal_cents, [(p.id, p.amount_cents) for p in live])
    except SettlementError as e:
        raise PlanBuildError(f"goal not reached by live holds: {e}") from e
    contract = _contract(db, c.project_id)
    steps = [
        _step(0, "CAPTURE_AUTH", "PLEDGE", p.id, caps[p.id], "POOL") for p in live if caps[p.id] > 0
    ]
    steps = [s.model_copy(update={"seq": i}) for i, s in enumerate(steps, start=1)]
    spec = MoneyPlanSpec(
        kind="CAPTURE_PLEDGES", project_id=c.project_id, campaign_id=c.id,
        contract_id=contract.id if contract else None, reason="GOAL_REACHED",
        inputs={
            "goal_cents": c.goal_cents, "currency": c.currency,
            "brd_sha256": contract.brd_sha256 if contract else None,
            "total_authorized_cents": sum(p.amount_cents for p in live),
            "pledges": [{"pledge_id": p.id, "authorization_id": p.paypal_authorization_id,
                         "authorized_cents": p.amount_cents, "capture_cents": caps[p.id]} for p in live],
        },
        steps=steps,
    )
    return _finalize(db, spec, exclude_plan_id)


def build_release_holds(db: Session, campaign_id: int, reason: str, exclude_plan_id: int | None = None) -> BuiltPlan:
    if reason not in RELEASE_REASONS:
        raise PlanBuildError(f"reason must be one of {sorted(RELEASE_REASONS)}")
    c = _campaign(db, campaign_id)
    if c.state not in ("OPEN", "FAILING"):
        raise PlanBuildError(f"campaign is {c.state}; holds are only released from OPEN/FAILING")
    pledges = list(db.scalars(select(Pledge).where(Pledge.campaign_id == c.id).order_by(Pledge.id)))
    if any(p.status == "CAPTURED" or p.captured_cents > 0 for p in pledges):
        raise PlanBuildError("a pledge in this campaign is already captured; release would be wrong")
    holds = [p for p in pledges if p.status == "AUTHORIZED" and p.paypal_authorization_id]
    spec = MoneyPlanSpec(
        kind="RELEASE_HOLDS", project_id=c.project_id, campaign_id=c.id, reason=reason,
        inputs={"goal_cents": c.goal_cents, "currency": c.currency,
                "pledges": [{"pledge_id": p.id, "authorization_id": p.paypal_authorization_id,
                             "authorized_cents": p.amount_cents} for p in holds]},
        steps=[_step(i, "VOID_AUTH", "PLEDGE", p.id, p.amount_cents, "NONE") for i, p in enumerate(holds, 1)],
    )
    return _finalize(db, spec, exclude_plan_id)


def build_freelancer_payout(db: Session, project_id: int, exclude_plan_id: int | None = None) -> BuiltPlan:
    contract = _contract(db, project_id)
    if contract is None or contract.signed_at is None:
        raise PlanBuildError("no signed contract")
    if not contract.freelancer_paypal_email:
        raise PlanBuildError("contract has no locked freelancer PayPal email")
    sub = db.scalars(select(Submission).where(Submission.contract_id == contract.id)
                     .order_by(Submission.attempt_no.desc())).first()
    report = db.scalars(select(VerificationReport).where(VerificationReport.submission_id == sub.id)
                        .order_by(VerificationReport.id.desc())).first() if sub else None
    if report is None or report.overall != "VERIFIED":
        raise PlanBuildError("latest submission has no VERIFIED report")
    campaign = db.scalars(select(Campaign).where(Campaign.project_id == project_id, Campaign.state == "CAPTURED")
                          .order_by(Campaign.number.desc())).first()
    if campaign is None:
        raise PlanBuildError("no captured campaign funds this project")
    pool = ledger.pool_balance(db, project_id)
    try:
        amount = plan_freelancer_payout(contract.amount_cents, pool, campaign.fee_reserve_cents)
    except SettlementError as e:
        raise PlanBuildError(str(e)) from e
    spec = MoneyPlanSpec(
        kind="FREELANCER_PAYOUT", project_id=project_id, campaign_id=campaign.id, contract_id=contract.id,
        reason="VERIFIED",
        inputs={"report_sha256": report.sha256, "submission_id": sub.id, "brd_sha256": contract.brd_sha256,
                "currency": contract.currency, "pool_balance_cents": pool},
        steps=[_step(1, "PAYOUT_ITEM", "CONTRACT", contract.id, amount, "POOL", contract.freelancer_paypal_email)],
    )
    return _finalize(db, spec, exclude_plan_id)


def build_refund_captured(db: Session, project_id: int, reason: str, exclude_plan_id: int | None = None) -> BuiltPlan:
    if reason not in REFUND_REASONS:
        raise PlanBuildError(f"reason must be one of {sorted(REFUND_REASONS)}")
    pledges = list(db.scalars(select(Pledge).where(Pledge.project_id == project_id, Pledge.captured_cents > 0)
                              .order_by(Pledge.id)))
    refunds = plan_refunds([(p.id, p.captured_cents, p.refunded_cents) for p in pledges])
    if not refunds:
        raise PlanBuildError("nothing left to refund")
    pool = ledger.pool_balance(db, project_id)
    if sum(refunds.values()) > pool:
        raise PlanBuildError("POOL no longer holds the captured funds (a payout already left it)")
    by_id = {p.id: p for p in pledges}
    spec = MoneyPlanSpec(
        kind="REFUND_CAPTURED", project_id=project_id, reason=reason,
        inputs={"pool_balance_cents": pool,
                "captures": [{"pledge_id": i, "capture_id": by_id[i].paypal_capture_id, "refund_cents": a}
                             for i, a in refunds.items()]},
        steps=[_step(n, "REFUND_CAPTURE", "CAPTURE", i, a, "POOL") for n, (i, a) in enumerate(refunds.items(), 1)],
    )
    return _finalize(db, spec, exclude_plan_id)


# ---------------- dispatch, rebuild, persistence ----------------

def build(db: Session, kind: str, *, project_id: int, campaign_id: int | None = None,
          reason: str | None = None, now: datetime | None = None,
          exclude_plan_id: int | None = None) -> BuiltPlan:
    now = now or datetime.now(timezone.utc)
    if kind == "CAPTURE_PLEDGES":
        return build_capture_pledges(db, campaign_id, now, exclude_plan_id)
    if kind == "RELEASE_HOLDS":
        return build_release_holds(db, campaign_id, reason or "", exclude_plan_id)
    if kind == "FREELANCER_PAYOUT":
        return build_freelancer_payout(db, project_id, exclude_plan_id)
    if kind == "REFUND_CAPTURED":
        return build_refund_captured(db, project_id, reason or "", exclude_plan_id)
    raise PlanBuildError(f"cannot build plan kind {kind}")


def rebuild(db: Session, plan: MoneyPlan, now: datetime | None = None) -> BuiltPlan:
    """Re-run the builder for a stored plan from current DB state (Guardian G-01, executor run-time check)."""
    return build(db, plan.kind, project_id=plan.project_id, campaign_id=plan.campaign_id,
                 reason=plan.reason if plan.kind in ("RELEASE_HOLDS", "REFUND_CAPTURED") else None, now=now,
                 exclude_plan_id=plan.id)


def release_policy_for(db: Session, kind: str, project_id: int) -> str:
    """SPEC 7.5.1: captures and releases are automatic on ALLOW; payouts and refunds need a human."""
    if kind in ("CAPTURE_PLEDGES", "RELEASE_HOLDS", "REAUTH_PLEDGES"):
        return "AUTO_ON_ALLOW"
    if kind == "FREELANCER_PAYOUT":
        project = db.get(Project, project_id)
        return "AUTO_ON_ALLOW" if project and project.payout_release_policy == "AUTO_ON_GUARDIAN_ALLOW" else "HUMAN"
    return "HUMAN"  # REFUND_CAPTURED, always


def save_proposed(db: Session, built: BuiltPlan, *, proposed_by: str) -> MoneyPlan:
    """Store a PROPOSED plan + steps. Idempotent: an identical non-terminal plan is returned, not duplicated."""
    spec = built.spec
    existing = db.scalars(select(MoneyPlan).where(
        MoneyPlan.plan_hash == built.plan_hash, MoneyPlan.kind == spec.kind,
        MoneyPlan.project_id == spec.project_id, MoneyPlan.state.not_in(TERMINAL_PLAN_STATES))).first()
    if existing:
        return existing
    plan = MoneyPlan(
        project_id=spec.project_id, campaign_id=spec.campaign_id, contract_id=spec.contract_id, kind=spec.kind,
        plan_json=spec.model_dump(mode="json"), plan_hash=built.plan_hash, state="PROPOSED", reason=spec.reason,
        proposed_by=proposed_by, release_policy=release_policy_for(db, spec.kind, spec.project_id),
    )
    db.add(plan)
    db.flush()
    for s in spec.steps:
        db.add(MoneyPlanStep(
            plan_id=plan.id, seq=s.seq, phase=s.phase, op=s.op, target_type=s.target_type, target_id=s.target_id,
            amount_cents=s.amount_cents, bucket=s.bucket, receiver_email=s.receiver_email,
            idempotency_key=s.idempotency_key, state="PENDING"))
    db.flush()
    return plan
