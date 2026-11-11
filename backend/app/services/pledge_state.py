"""Changing an EXISTING pledge when PayPal tells us something (BLK-03). Monotonic helpers shared by the pledge service
(which hears it synchronously from PayPal's authorize answer) and the webhook processor (which hears it again, or hears it
first). Flushes only; the caller owns the transaction. They never call PayPal.

  CREATED    -> AUTHORIZED   `mark_authorized`   (a hold exists)
  AUTHORIZED -> VOIDED/EXPIRED `mark_hold_ended` (PayPal ended the hold without us asking)
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Campaign, Pledge, ProjectMember
from app.services import ledger
from app.services.pledge_gate import hold_times


def _now() -> datetime:
    return datetime.now(timezone.utc)


def held_cents(db: Session, campaign_id: int) -> int:
    """Σ AUTHORIZED holds. Holds are not money (I-8): this never touches the ledger's POOL."""
    return int(db.scalar(select(func.coalesce(func.sum(Pledge.amount_cents), 0)).where(
        Pledge.campaign_id == campaign_id, Pledge.status == "AUTHORIZED")) or 0)


def mark_authorized(db: Session, pledge: Pledge, authorization_id: str, authorized_at: datetime | None = None, *,
                    payer_email: str | None = None, payer_id: str | None = None) -> bool:
    """Record that PayPal placed the hold. Returns True if this call changed the pledge.

    Only from CREATED. The same authorization id again is a no-op, so a webhook that repeats what the synchronous answer
    already told us changes nothing; a pledge that was already ended or captured is never revived."""
    if pledge.status != "CREATED":
        return False
    at = authorized_at or _now()
    honor_until, valid_until = hold_times(at)
    pledge.status, pledge.paypal_authorization_id = "AUTHORIZED", authorization_id
    pledge.authorized_at, pledge.honor_until, pledge.valid_until = at, honor_until, valid_until
    if payer_email:
        pledge.payer_email = payer_email
    if payer_id:
        pledge.payer_id = payer_id
    db.flush()
    ledger.append(db, pledge.project_id, "PLEDGE_AUTHORIZED", actor="paypal", ref_type="pledge", ref_id=pledge.id,
                  meta={"authorization_id": authorization_id, "campaign_id": pledge.campaign_id})
    if pledge.member_id is not None:
        member = db.get(ProjectMember, pledge.member_id)
        if member is not None and member.role == "SPONSOR":
            member.invite_status = "PLEDGED"
    campaign = db.get(Campaign, pledge.campaign_id)
    if campaign is not None and campaign.goal_reached_at is None and held_cents(db, campaign.id) >= campaign.goal_cents:
        campaign.goal_reached_at = at
    db.flush()
    return True


def mark_hold_ended(db: Session, pledge: Pledge, reason: str) -> bool:
    """PayPal ended a hold we did not ask to end (a buyer cancelled it, or it expired). `reason` is VOIDED or EXPIRED.
    Only from AUTHORIZED. Returns True if this call changed the pledge."""
    if reason not in ("VOIDED", "EXPIRED"):
        raise ValueError("reason must be VOIDED or EXPIRED")
    if pledge.status != "AUTHORIZED":
        return False
    pledge.status = reason
    ledger.append(db, pledge.project_id, f"PLEDGE_{reason}", actor="paypal", ref_type="pledge", ref_id=pledge.id,
                  meta={"unplanned": True, "authorization_id": pledge.paypal_authorization_id})
    db.flush()
    return True
