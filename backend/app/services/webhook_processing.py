"""Turning a verified PayPal event into state (SPEC 9.5). Runs inside the PROCESS_WEBHOOK job.

Rules: never call a PayPal write; only confirm or fail the plan steps we already sent (through `plan_lifecycle`, which owns
the ledger effects); be idempotent and monotonic, because events repeat and arrive out of order. If an event refers to
something we sent but whose record is not committed yet, raise `NotReady` so the job retries a little later.

Pledge-status events (a hold placed, an UNPLANNED void) need `pledge_state` (blocked, BLK-03): they are acknowledged
and recorded as NOT_HANDLED.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LedgerEntry, MoneyPlanStep, PayoutItem, Pledge
from app.services import ledger, plan_lifecycle
from app.services.guardian_rules import PayPalUnavailable
from app.services.paypal_client import value_to_cents

OPEN_STEP_STATES = ("PENDING", "SENT")
PAYOUT_FAILED = ("FAILED", "BLOCKED", "CANCELED", "DENIED")
PAYOUT_REVERSED = ("RETURNED", "REFUNDED")      # the money came back to the platform
# UNCLAIMED is NOT a failure: PayPal has taken the money and holds it until the recipient claims it (or returns it after
# 30 days as RETURNED). Treating it as failed would invite a retry and could pay the freelancer twice.
PAYOUT_WAITING = ("HELD", "ONHOLD", "PENDING", "UNCLAIMED")


class NotReady(Exception):
    """The event is about something we sent, but our record of it is not there yet: retry shortly."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _related(resource: dict, key: str) -> str | None:
    return ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get(key)


def _amount_cents(resource: dict) -> int | None:
    value = (resource.get("amount") or {}).get("value")
    try:
        return value_to_cents(value) if value is not None else None
    except ValueError:
        return None


def _open_step(db: Session, op: str, *, paypal_ref: str | None = None, pledge_id: int | None = None) -> MoneyPlanStep | None:
    """The step this event is about: first by the PayPal id we stored when sending, then by the pledge it targets."""
    if paypal_ref:
        s = db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.op == op, MoneyPlanStep.paypal_ref == paypal_ref)
                       .order_by(MoneyPlanStep.id.desc())).first()
        if s is not None:
            return s
    if pledge_id is not None:
        return db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.op == op, MoneyPlanStep.target_id == pledge_id,
                                                      MoneyPlanStep.state.in_(OPEN_STEP_STATES)).order_by(MoneyPlanStep.id.desc())).first()
    return None


def _pledge_by_auth(db: Session, authorization_id: str | None) -> Pledge | None:
    if not authorization_id:
        return None
    return db.scalars(select(Pledge).where(Pledge.paypal_authorization_id == authorization_id)).first()


# ---------------- captures ----------------

def _capture_event(db: Session, event_type: str, resource: dict, now: datetime) -> dict:
    capture_id = resource.get("id")
    pledge = _pledge_by_auth(db, _related(resource, "authorization_id"))
    step = _open_step(db, "CAPTURE_AUTH", paypal_ref=capture_id, pledge_id=pledge.id if pledge else None)
    if step is None:
        if pledge is None:
            return {"effect": "UNKNOWN_OBJECT", "capture_id": capture_id}
        already = db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.op == "CAPTURE_AUTH", MoneyPlanStep.target_id == pledge.id,
                                                         MoneyPlanStep.state == "CONFIRMED")).first()
        if already is not None:
            return {"effect": "ALREADY_APPLIED", "step_id": already.id}
        raise NotReady(f"no capture step recorded yet for pledge {pledge.id}")
    if step.state == "CONFIRMED":
        return {"effect": "ALREADY_APPLIED", "step_id": step.id}
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        got = _amount_cents(resource)
        if got is not None and got != step.amount_cents:  # money moved differently from the approved plan: do not paper over it
            detail = {"step_id": step.id, "expected_cents": step.amount_cents, "paypal_cents": got}
            _memo_once(db, _project_of_step(db, step), "plan_step", step.id,
                       {"reconciliation": "RECONCILIATION_MISMATCH", "capture_id": capture_id, "plan_id": step.plan_id, **detail})
            return {"effect": "RECONCILIATION_MISMATCH", **detail}
        plan_lifecycle.confirm_step(db, step, paypal_ref=capture_id, now=now)
        return {"effect": "STEP_CONFIRMED", "step_id": step.id}
    if event_type == "PAYMENT.CAPTURE.DECLINED":
        plan_lifecycle.fail_step(db, step, {"reason": "CAPTURE_DECLINED", "capture_id": capture_id})
        return {"effect": "STEP_FAILED", "step_id": step.id}
    return {"effect": "STILL_PENDING", "step_id": step.id}  # PAYMENT.CAPTURE.PENDING


def _void_event(db: Session, resource: dict, now: datetime) -> dict:
    pledge = _pledge_by_auth(db, resource.get("id"))
    if pledge is None:
        return {"effect": "UNKNOWN_OBJECT", "authorization_id": resource.get("id")}
    step = _open_step(db, "VOID_AUTH", pledge_id=pledge.id)
    if step is not None:  # a void we asked for
        plan_lifecycle.confirm_step(db, step, now=now)
        return {"effect": "STEP_CONFIRMED", "step_id": step.id}
    if pledge.status in ("VOIDED", "EXPIRED", "CAPTURED"):
        return {"effect": "ALREADY_APPLIED", "pledge_id": pledge.id}
    return {"effect": "NOT_HANDLED", "why": "unplanned void needs pledge_state (BLK-03)", "pledge_id": pledge.id}


def _refund_event(db: Session, resource: dict, now: datetime) -> dict:
    refund_id = resource.get("id")
    up = next((ln.get("href", "") for ln in resource.get("links") or [] if ln.get("rel") == "up"), "")
    capture_id = up.rstrip("/").rsplit("/", 1)[-1] if up else None
    pledge = db.scalars(select(Pledge).where(Pledge.paypal_capture_id == capture_id)).first() if capture_id else None
    step = _open_step(db, "REFUND_CAPTURE", paypal_ref=refund_id, pledge_id=pledge.id if pledge else None)
    if step is None:
        if refund_id and db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.paypal_ref == refund_id, MoneyPlanStep.state == "CONFIRMED")).first():
            return {"effect": "ALREADY_APPLIED"}
        if pledge is None:
            return {"effect": "UNKNOWN_OBJECT", "refund_id": refund_id}
        raise NotReady(f"no refund step recorded yet for pledge {pledge.id}")
    if step.state == "CONFIRMED":
        return {"effect": "ALREADY_APPLIED", "step_id": step.id}
    plan_lifecycle.confirm_step(db, step, paypal_ref=refund_id, now=now)
    return {"effect": "STEP_CONFIRMED", "step_id": step.id}


# ---------------- payouts ----------------

def _apply_payout_item(db: Session, sender_item_id: str | None, status: str | None, paypal_item_id: str | None, now: datetime) -> dict:
    item = db.scalars(select(PayoutItem).where(PayoutItem.sender_item_id == str(sender_item_id))).first() if sender_item_id else None
    if item is None:
        return {"effect": "UNKNOWN_OBJECT", "sender_item_id": sender_item_id}
    step = db.get(MoneyPlanStep, item.step_id)
    item.paypal_item_id = item.paypal_item_id or paypal_item_id
    if status == "SUCCESS" or status == "SUCCEEDED":
        if step.state == "CONFIRMED":
            return {"effect": "ALREADY_APPLIED", "step_id": step.id}
        plan_lifecycle.confirm_step(db, step, paypal_ref=paypal_item_id or step.paypal_ref, now=now)
        return {"effect": "STEP_CONFIRMED", "step_id": step.id}
    if status in PAYOUT_FAILED or (status in PAYOUT_REVERSED and step.state != "CONFIRMED"):
        if step.state == "CONFIRMED" or item.status == status:
            return {"effect": "ALREADY_APPLIED", "step_id": step.id}
        plan_lifecycle.fail_step(db, step, {"reason": f"PAYOUT_{status}", "payout_item_id": paypal_item_id})
        item.status = status
        return {"effect": "STEP_FAILED", "step_id": step.id}
    if status in PAYOUT_REVERSED:  # it had succeeded and came back: the money is in the pool again
        if item.status == status:
            return {"effect": "ALREADY_APPLIED", "step_id": step.id}
        item.status = status
        ledger.append(db, _project_of_step(db, step), "PAYOUT_RETURNED", item.amount_cents, actor="paypal", ref_type="payout_item",
                      ref_id=item.id, meta={"status": status, "plan_id": step.plan_id})
        return {"effect": "PAYOUT_RETURNED", "step_id": step.id}
    if status in PAYOUT_WAITING:
        if step.state != "CONFIRMED":
            item.status = "UNCLAIMED" if status == "UNCLAIMED" else "HELD" if status in ("HELD", "ONHOLD") else item.status
        return {"effect": "STILL_PENDING", "step_id": step.id, "status": status}
    return {"effect": "IGNORED", "status": status}


def _memo_once(db: Session, project_id: int, ref_type: str, ref_id: int, meta: dict) -> None:
    """A GUARDIAN_DECISION memo (amount 0) that the money box shows as an alert. Written once per object and kind."""
    kind = meta.get("reconciliation") or meta.get("alert")
    for e in db.scalars(select(LedgerEntry).where(LedgerEntry.project_id == project_id, LedgerEntry.type == "GUARDIAN_DECISION",
                                                  LedgerEntry.ref_type == ref_type, LedgerEntry.ref_id == str(ref_id))):
        if (e.meta_json or {}).get("reconciliation", (e.meta_json or {}).get("alert")) == kind:
            return
    ledger.append(db, project_id, "GUARDIAN_DECISION", actor="agent:guardian", ref_type=ref_type, ref_id=ref_id, meta=meta)


def _project_of_step(db: Session, step: MoneyPlanStep) -> int:
    from app.models import MoneyPlan
    return db.get(MoneyPlan, step.plan_id).project_id


def _payout_item_event(db: Session, event_type: str, resource: dict, now: datetime) -> dict:
    status = resource.get("transaction_status") or event_type.rsplit(".", 1)[-1]
    sender_item_id = (resource.get("payout_item") or {}).get("sender_item_id")
    return _apply_payout_item(db, sender_item_id, status, resource.get("payout_item_id"), now)


def _payout_batch_event(db: Session, resource: dict, payout_reader, now: datetime) -> dict:
    batch_id = (resource.get("batch_header") or {}).get("payout_batch_id") or resource.get("id")
    if not batch_id:
        return {"effect": "UNKNOWN_OBJECT"}
    try:
        data = payout_reader.get_payout_batch(batch_id)
    except PayPalUnavailable as e:
        raise NotReady(f"could not fetch payout batch {batch_id}: {e}") from e
    results = [_apply_payout_item(db, i.get("sender_item_id"), i.get("transaction_status"), i.get("payout_item_id"), now) for i in data.get("items", [])]
    return {"effect": "BATCH_APPLIED", "batch_id": batch_id, "items": results}


# ---------------- dispatch ----------------

def process(db: Session, event: dict, *, payout_reader, now: datetime | None = None) -> dict:
    now = now or _now()
    event_type = event.get("event_type", "")
    resource = event.get("resource") if isinstance(event.get("resource"), dict) else {}
    if event_type in ("PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.DECLINED", "PAYMENT.CAPTURE.PENDING"):
        return _capture_event(db, event_type, resource, now)
    if event_type == "PAYMENT.AUTHORIZATION.VOIDED":
        return _void_event(db, resource, now)
    if event_type == "PAYMENT.CAPTURE.REFUNDED":
        return _refund_event(db, resource, now)
    if event_type.startswith("PAYMENT.PAYOUTS-ITEM."):
        return _payout_item_event(db, event_type, resource, now)
    if event_type.startswith("PAYMENT.PAYOUTSBATCH."):
        return _payout_batch_event(db, resource, payout_reader, now)
    if event_type == "PAYMENT.AUTHORIZATION.CREATED":
        return {"effect": "NOT_HANDLED", "why": "needs pledge_state (BLK-03)"}
    if event_type == "PAYMENT.CAPTURE.REVERSED":
        capture_id = resource.get("id")
        pledge = db.scalars(select(Pledge).where(Pledge.paypal_capture_id == capture_id)).first() if capture_id else None
        if pledge is not None:  # money already counted in the POOL was taken back: say so loudly, but book nothing
            _memo_once(db, pledge.project_id, "pledge", pledge.id, {"alert": "CAPTURE_REVERSED", "capture_id": capture_id})
        return {"effect": "ALERT", "why": "a capture was reversed (chargeback-like); resolving it is out of scope", "capture_id": capture_id}
    return {"effect": "INFORMATIONAL" if event_type == "CHECKOUT.ORDER.APPROVED" else "IGNORED"}
