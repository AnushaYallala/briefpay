"""Poll fallback (SPEC 9, 14.5): ask PayPal about steps that were SENT but never confirmed, in case a webhook did not arrive.

The free API server sleeps, PayPal can fail to deliver. So every ~30 s while the server is awake, and when a member opens
the money screen, we READ the status of each waiting step and turn it into the same event a webhook would have carried. It
then goes through `webhook_processing.process`, the one place that decides how a step is confirmed or failed, so a poll and a
webhook can never disagree and doing both is harmless (processing is idempotent and monotonic).

Read-only toward PayPal: no write method is used or reachable from here.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MoneyPlan, MoneyPlanStep, Pledge
from app.services import plan_lifecycle
from app.services import webhook_processing as wp
from app.services.guardian_rules import PayPalUnavailable

MIN_AGE_SECONDS = 20           # give the webhook the first chance
MAX_STEPS = 50
CAPTURE_DONE = ("COMPLETED", "REFUNDED", "PARTIALLY_REFUNDED")      # it was captured, whatever happened to it afterwards
CAPTURE_REFUSED = ("DECLINED", "FAILED")
REFUND_REFUSED = ("FAILED", "CANCELLED")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def value(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def _event(event_type: str, resource: dict) -> dict:
    return {"id": f"poll-{event_type}-{resource.get('id')}", "event_type": event_type, "resource": resource}


def waiting_steps(db: Session, *, project_id: int | None = None, force: bool = False, now: datetime | None = None) -> list[MoneyPlanStep]:
    now = now or _now()
    q = (select(MoneyPlanStep).join(MoneyPlan, MoneyPlan.id == MoneyPlanStep.plan_id)
         .where(MoneyPlanStep.state == "SENT", MoneyPlanStep.paypal_ref.is_not(None), MoneyPlan.state == "EXECUTING")
         .order_by(MoneyPlanStep.id).limit(MAX_STEPS))
    if project_id is not None:
        q = q.where(MoneyPlan.project_id == project_id)
    steps = list(db.scalars(q))
    if force:
        return steps
    cutoff = now - timedelta(seconds=MIN_AGE_SECONDS)
    return [s for s in steps if _aware(s.updated_at) <= cutoff]


def _poll_capture(db, reader, step, payout_reader, now) -> str:
    pledge = db.get(Pledge, step.target_id)
    got = reader.get_capture(step.paypal_ref)
    if got is None:
        return "not_found"
    resource = {"id": step.paypal_ref, "amount": {"currency_code": got.currency, "value": value(got.amount_cents)},
                "supplementary_data": {"related_ids": {"authorization_id": pledge.paypal_authorization_id if pledge else None}}}
    if got.status in CAPTURE_DONE:
        return wp.process(db, _event("PAYMENT.CAPTURE.COMPLETED", resource), payout_reader=payout_reader, now=now)["effect"]
    if got.status in CAPTURE_REFUSED:
        return wp.process(db, _event("PAYMENT.CAPTURE.DECLINED", resource), payout_reader=payout_reader, now=now)["effect"]
    return "pending"


def _poll_void(db, reader, step, payout_reader, now) -> str:
    pledge = db.get(Pledge, step.target_id)
    if pledge is None or not pledge.paypal_authorization_id:
        return "not_found"
    got = reader.get_authorization(pledge.paypal_authorization_id)
    if got is None:
        return "not_found"
    if got.status == "VOIDED":
        return wp.process(db, _event("PAYMENT.AUTHORIZATION.VOIDED", {"id": pledge.paypal_authorization_id, "status": "VOIDED"}),
                          payout_reader=payout_reader, now=now)["effect"]
    return "pending"


def _poll_refund(db, reader, step, payout_reader, now) -> str:
    got = reader.get_refund(step.paypal_ref)
    if got is None:
        return "not_found"
    if got.status == "COMPLETED":
        return wp.process(db, _event("PAYMENT.CAPTURE.REFUNDED", {"id": step.paypal_ref, "status": "COMPLETED"}), payout_reader=payout_reader, now=now)["effect"]
    if got.status in REFUND_REFUSED:
        plan_lifecycle.fail_step(db, step, {"reason": f"REFUND_{got.status}", "refund_id": step.paypal_ref})
        return "STEP_FAILED"
    return "pending"


def _poll_payout_batch(db, payout_reader, batch_id: str, now) -> list[str]:
    event = _event("PAYMENT.PAYOUTSBATCH.SUCCESS", {"batch_header": {"payout_batch_id": batch_id}})
    return [r["effect"] for r in wp.process(db, event, payout_reader=payout_reader, now=now)["items"]]


def run_periodic(session_factory) -> dict | None:
    """The 30-second tick while the server is awake. Does nothing until PayPal is configured."""
    from app.services import paypal_io
    reader = paypal_io.get_reader()
    if isinstance(reader, paypal_io.UnconfiguredReader):
        return None
    db = session_factory()
    try:
        summary = poll(db, reader, paypal_io.get_payout_reader())
        db.commit()
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def poll(db: Session, reader, payout_reader, *, project_id: int | None = None, force: bool = False, now: datetime | None = None) -> dict:
    """One pass over the waiting steps. PayPal being unreachable only postpones: nothing is guessed, nothing is failed."""
    now = now or _now()
    steps = waiting_steps(db, project_id=project_id, force=force, now=now)
    summary = {"checked": 0, "confirmed": 0, "failed": 0, "pending": 0, "not_found": 0, "unavailable": 0, "mismatch": 0, "other": 0}
    batches: set[str] = set()

    def count(effect: str) -> None:
        key = {"STEP_CONFIRMED": "confirmed", "STEP_FAILED": "failed", "pending": "pending", "STILL_PENDING": "pending",
               "not_found": "not_found", "RECONCILIATION_MISMATCH": "mismatch"}.get(effect, "other")
        summary[key] += 1

    for step in steps:
        summary["checked"] += 1
        try:
            if step.op == "CAPTURE_AUTH":
                count(_poll_capture(db, reader, step, payout_reader, now))
            elif step.op == "VOID_AUTH":
                count(_poll_void(db, reader, step, payout_reader, now))
            elif step.op == "REFUND_CAPTURE":
                count(_poll_refund(db, reader, step, payout_reader, now))
            elif step.op == "PAYOUT_ITEM":
                if step.paypal_ref in batches:                 # a batch is read once per pass, however many items it has
                    summary["checked"] -= 1
                    continue
                batches.add(step.paypal_ref)
                for effect in _poll_payout_batch(db, payout_reader, step.paypal_ref, now):
                    count(effect)
            else:
                summary["other"] += 1
        except (PayPalUnavailable, wp.NotReady):
            summary["unavailable"] += 1
    db.flush()
    return summary
