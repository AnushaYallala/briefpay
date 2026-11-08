"""Read side of the money: ledger rows for the grid, the project's money box, and the AI audit trail (SPEC 10, 11.1 #12/#13).

Read-only: nothing here writes, and nothing here calls PayPal. The ledger is public (anyone with the link), so the public
view never shows an email address: the ledger is written without them, and anything that looks like one is masked anyway.
"""
import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AgentRun, Campaign, Contract, LedgerEntry, MoneyPlan, MoneyPlanStep, PayoutItem, Pledge, ProjectMember, User,
)
from app.services.ledger import POOL

EMAIL = re.compile(r"[\w.+%-]+@[\w-]+(?:\.[\w-]+)+")
HIDDEN = "[hidden]"

STATUS_CHIP = {
    "PLEDGE_AUTHORIZED": "Held", "PLEDGE_CAPTURED": "Captured", "PLEDGE_VOIDED": "Voided", "PLEDGE_EXPIRED": "Expired",
    "REFUND": "Refunded", "PAYOUT_SENT": "Paid", "PAYOUT_RETURNED": "Returned",
}
PAYPAL_REF_KEYS = ("capture_id", "refund_id", "payout_ref")
ALERT_KEYS = ("reconciliation", "alert")
AGENT_RUN_LIMIT = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def mask(value):
    """Public view: drop keys that name an email, and mask any text that contains one (comments, notes)."""
    if isinstance(value, dict):
        return {k: mask(v) for k, v in value.items() if "email" not in str(k).lower()}
    if isinstance(value, list):
        return [mask(v) for v in value]
    if isinstance(value, str):
        return EMAIL.sub(HIDDEN, value)
    return value


def _names(db: Session, project_id: int, entries: list[LedgerEntry]) -> tuple[dict, dict]:
    """Display names for counterparties (pledgers, the freelancer) and for user actors. Never emails."""
    pledge_ids = {int(e.ref_id) for e in entries if e.ref_type == "pledge" and (e.ref_id or "").isdigit()}
    pledges = {p.id: p.display_name for p in db.scalars(select(Pledge).where(Pledge.id.in_(pledge_ids)))} if pledge_ids else {}
    freelancer = db.scalars(select(User.display_name).join(ProjectMember, ProjectMember.user_id == User.id).where(
        ProjectMember.project_id == project_id, ProjectMember.role == "FREELANCER")).first()
    user_ids = {int(e.actor[5:]) for e in entries if e.actor.startswith("user:") and e.actor[5:].isdigit()}
    users = {u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    counterparty = {}
    for e in entries:
        if e.ref_type == "pledge" and (e.ref_id or "").isdigit():
            counterparty[e.id] = pledges.get(int(e.ref_id))
        elif e.ref_type in ("contract", "payout_item"):
            counterparty[e.id] = freelancer
    return counterparty, users


def _actor_name(actor: str, users: dict) -> str:
    if actor.startswith("user:") and actor[5:].isdigit():
        return users.get(int(actor[5:]), "a member")
    if actor.startswith("agent:"):
        return actor[6:].replace("_", " ").title() + " agent"
    return {"paypal": "PayPal", "system": "BriefPay"}.get(actor, actor)


def ledger_rows(db: Session, project_id: int, *, public: bool) -> dict:
    entries = list(db.scalars(select(LedgerEntry).where(LedgerEntry.project_id == project_id).order_by(LedgerEntry.seq)))
    counterparty, users = _names(db, project_id, entries)
    rows, balance, pool_in, pool_out = [], 0, 0, 0
    for e in entries:
        if e.bucket == POOL:
            balance += e.amount_cents
            pool_in += max(e.amount_cents, 0)
            pool_out += min(e.amount_cents, 0)
        meta = e.meta_json or {}
        ref = next((meta[k] for k in PAYPAL_REF_KEYS if meta.get(k)), None)
        rows.append({
            "seq": e.seq, "created_at": e.created_at.isoformat(), "bucket": e.bucket, "type": e.type,
            "counterparty": counterparty.get(e.id), "amount_cents": e.amount_cents,
            "running_balance_cents": balance, "status": STATUS_CHIP.get(e.type), "paypal_ref": ref,
            "actor": e.actor, "actor_name": _actor_name(e.actor, users),
            "ref_type": e.ref_type, "ref_id": e.ref_id,
            "paypal_match": None,  # SHOULD (SPEC 11.1 #12): needs a PayPal read per row; not built yet (GAP-50)
            "alert": any(k in meta for k in ALERT_KEYS),
            "meta": mask(meta) if public else meta,
        })
    return {"project_id": project_id, "public": public, "rows": rows,
            "totals": {"pool_in_cents": pool_in, "pool_out_cents": pool_out, "pool_balance_cents": balance, "rows": len(rows)}}


def money_summary(db: Session, project_id: int, *, now: datetime | None = None) -> dict:
    """The workspace "Money" box: POOL, holds outstanding (not money, I-8), next honor deadline, open plans, alerts."""
    now = now or _now()
    data = ledger_rows(db, project_id, public=False)
    held = list(db.scalars(select(Pledge).where(Pledge.project_id == project_id, Pledge.status == "AUTHORIZED")))
    future = [_aware(p.honor_until) for p in held if p.honor_until is not None and _aware(p.honor_until) > now]
    campaign = db.scalars(select(Campaign).where(Campaign.project_id == project_id).order_by(Campaign.number.desc())).first()
    contract = db.scalars(select(Contract).where(Contract.project_id == project_id).order_by(Contract.id.desc())).first()
    open_plans = db.scalars(select(MoneyPlan).where(MoneyPlan.project_id == project_id,
                                                    MoneyPlan.state.in_(("PROPOSED", "REVIEWED", "APPROVED", "EXECUTING")))).all()
    unclaimed = db.scalar(select(func.count(PayoutItem.id)).join(MoneyPlanStep, MoneyPlanStep.id == PayoutItem.step_id)
                          .join(MoneyPlan, MoneyPlan.id == MoneyPlanStep.plan_id)
                          .where(MoneyPlan.project_id == project_id, PayoutItem.status == "UNCLAIMED"))
    return {
        "project_id": project_id,
        "pool_balance_cents": data["totals"]["pool_balance_cents"],
        "holds": {"count": len(held), "total_cents": sum(p.amount_cents for p in held),
                  "note": "Holds are not money: nothing is charged unless the goal is reached."},
        "next_honor_deadline": min(future).isoformat() if future else None,
        "campaign": None if campaign is None else {"id": campaign.id, "number": campaign.number, "state": campaign.state,
                                                   "goal_cents": campaign.goal_cents, "deadline_at": _aware(campaign.deadline_at).isoformat()},
        "contract_amount_cents": contract.amount_cents if contract else None,
        "open_plans": [{"id": p.id, "kind": p.kind, "state": p.state} for p in open_plans],
        "unclaimed_payouts": int(unclaimed or 0),  # paid out by PayPal, waiting for the freelancer to claim it
        "alerts": [{"seq": r["seq"], "created_at": r["created_at"], "meta": r["meta"]} for r in data["rows"] if r["alert"]],
    }


def agent_runs(db: Session, project_id: int, *, agent: str | None = None, limit: int = 200) -> dict:
    limit = max(1, min(int(limit), AGENT_RUN_LIMIT))
    q = select(AgentRun).where(AgentRun.project_id == project_id)
    if agent:
        q = q.where(AgentRun.agent == agent)
    runs = db.scalars(q.order_by(AgentRun.id.desc()).limit(limit)).all()
    return {"project_id": project_id, "rows": [{
        "id": r.id, "created_at": r.created_at.isoformat(), "agent": r.agent, "provider": r.provider, "model": r.model,
        "prompt_version": r.prompt_version, "input_hash": r.input_hash, "latency_ms": r.latency_ms,
        "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "status": r.status,
        "output": r.output_json, "error": r.error} for r in runs]}
