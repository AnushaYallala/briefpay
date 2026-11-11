"""Taking a pledge (BLK-01, SPEC 8.2, 9). A pledge is only a HOLD on the supporter's PayPal account; no money moves here.

Two steps, both through the Pledge Gate:
  1. `start_pledge`     checks the gate, saves a CREATED pledge, asks PayPal for an AUTHORIZE order, keeps its id.
  2. `authorize_pledge` after the supporter approved it in PayPal's popup: asks PayPal to place the hold, and counts it only
                        if PayPal itself says it exists for exactly the amount we asked for.

This is the only module allowed to call the buyer-side order methods (tests/test_chokepoint.py). Flushes only; the caller
owns the transaction, except that a refused or failed attempt must be remembered, which `PledgeError.keep` tells it to do.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campaign, Pledge, Project, ProjectMember, User
from app.services import pledge_gate as gate
from app.services import pledge_state
from app.services.campaign_rules import as_utc
from app.services.paypal_io import OrderGateway, PayPalWriteError

log = logging.getLogger("briefpay.pledges")

BOARD_STATUSES = ("AUTHORIZED", "CAPTURED", "VOIDED", "EXPIRED")   # CREATED and DENIED rows are never public


class PledgeError(Exception):
    """`keep` = the caller should commit what was changed (a declined pledge is recorded as DENIED) before answering."""

    def __init__(self, code: str, message: str, status: int = 409, keep: bool = False):
        super().__init__(message)
        self.code, self.message, self.status, self.keep = code, message, status, keep


def _now() -> datetime:
    return datetime.now(timezone.utc)


def facts(db: Session, c: Campaign) -> gate.CampaignFacts:
    return gate.CampaignFacts(state=c.state, deadline_at=c.deadline_at, goal_cents=c.goal_cents, min_pledge_cents=c.min_pledge_cents,
                              held_cents=pledge_state.held_cents(db, c.id), currency=c.currency)


def _gate(fn, *a, **k):
    try:
        return fn(*a, **k)
    except gate.GateError as e:
        raise PledgeError(e.code, e.message, e.status) from e


def _viewer_member(db: Session, project_id: int, user: User) -> ProjectMember | None:
    return db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)).first()


def _recent_attempts(db: Session, user: User, now: datetime) -> int:
    cutoff = now - timedelta(hours=1)
    rows = db.scalars(select(Pledge.created_at).where(Pledge.supporter_user_id == user.id).order_by(Pledge.id.desc()).limit(50))
    return sum(1 for t in rows if t is not None and as_utc(t) >= cutoff)


def start_pledge(db: Session, c: Campaign, user: User, *, amount_cents: int, display_name: str | None,
                 orders: OrderGateway, now: datetime | None = None) -> Pledge:
    """Gate -> CREATED row -> PayPal order. Returns the pledge (its `paypal_order_id` is what the PayPal button approves)."""
    now = now or _now()
    member = _viewer_member(db, c.project_id, user)
    _gate(gate.check_new_pledge, facts(db, c), amount_cents=amount_cents, role=member.role if member else None, now=now)
    name = _gate(gate.clean_display_name, display_name or user.display_name)
    if _recent_attempts(db, user, now) >= gate.ORDERS_PER_USER_PER_HOUR:
        raise PledgeError("RATE_LIMITED", f"Please wait: at most {gate.ORDERS_PER_USER_PER_HOUR} pledge attempts an hour", 429)

    p = Pledge(campaign_id=c.id, project_id=c.project_id, member_id=member.id if member else None, supporter_user_id=user.id,
               display_name=name, paypal_order_id=f"PENDING-{uuid.uuid4().hex}", amount_cents=amount_cents, status="CREATED")
    db.add(p)
    db.flush()
    project = db.get(Project, c.project_id)
    try:
        r = orders.create_authorize_order(amount_cents, c.currency, custom_id=f"camp:{c.id}:pledge:{p.id}",
                                          description=f"Pledge for {project.title if project else 'a BriefPay project'} (held, not charged)",
                                          request_id=f"order-{p.id}")
    except PayPalWriteError as e:
        p.status = "DENIED"
        log.warning("pledge %s: PayPal refused to create the order: %s", p.id, e)
        raise PledgeError("PAYPAL_UNAVAILABLE", f"PayPal could not start the pledge: {e}", 502, keep=True) from e
    order_id = (r or {}).get("id")
    if not order_id:
        p.status = "DENIED"
        raise PledgeError("PAYPAL_UNAVAILABLE", "PayPal did not return an order", 502, keep=True)
    p.paypal_order_id = order_id
    db.flush()
    return p


def authorize_pledge(db: Session, c: Campaign, user: User, *, order_id: str, orders: OrderGateway,
                     now: datetime | None = None) -> Pledge:
    """After the supporter approved the order in PayPal's popup: place the hold. Idempotent when already authorized."""
    now = now or _now()
    p = db.scalars(select(Pledge).where(Pledge.paypal_order_id == order_id, Pledge.campaign_id == c.id)).first()
    if p is None:
        raise PledgeError("PLEDGE_NOT_FOUND", "No such pledge on this campaign", 404)
    if p.supporter_user_id != user.id:
        raise PledgeError("FORBIDDEN", "This pledge belongs to someone else", 403)
    if p.status == "AUTHORIZED":
        return p
    if p.status != "CREATED":
        raise PledgeError("PLEDGE_STATE", f"This pledge is {p.status.lower()}; start a new one", 409)
    _gate(gate.check_authorize_allowed, facts(db, c), now=now)
    try:
        r = orders.authorize_order(order_id, request_id=f"authz-{p.id}")
    except PayPalWriteError as e:
        if e.transient:     # the order stays CREATED, so pressing the button again retries with the same request id
            raise PledgeError("PAYPAL_UNAVAILABLE", f"PayPal could not place the hold just now: {e}. Please try again", 502) from e
        p.status = "DENIED"
        log.warning("pledge %s: PayPal refused the hold: %s", p.id, e)
        raise PledgeError("PLEDGE_DECLINED", f"PayPal did not place the hold: {e}", 402, keep=True) from e
    auth = (r or {}).get("authorization")
    try:
        gate.check_hold(pledge_amount_cents=p.amount_cents, campaign_currency=c.currency, auth=auth)
    except gate.GateError as e:
        p.status = "DENIED"
        log.warning("pledge %s: hold not counted (%s)", p.id, e.code)
        raise PledgeError(e.code, e.message, e.status, keep=True) from e
    pledge_state.mark_authorized(db, p, auth["id"], now, payer_email=r.get("payer_email"), payer_id=r.get("payer_id"))
    return p


# ---------------- the board ----------------

def board(db: Session, c: Campaign, *, lead: bool) -> list[dict]:
    """Public: name, amount, status, time; no emails. The lead also sees payer email, honor time and unfinished (CREATED) rows."""
    statuses = BOARD_STATUSES + (("CREATED",) if lead else ())
    rows = db.scalars(select(Pledge).where(Pledge.campaign_id == c.id, Pledge.status.in_(statuses)).order_by(Pledge.id))
    out = []
    for p in rows:
        t = p.authorized_at or p.created_at
        row = {"id": p.id, "display_name": p.display_name, "amount_cents": p.amount_cents, "status": p.status,
               "at": as_utc(t).isoformat() if t else None}
        if lead:
            row["payer_email"] = p.payer_email
            row["honor_until"] = as_utc(p.honor_until).isoformat() if p.honor_until else None
        out.append(row)
    return out
