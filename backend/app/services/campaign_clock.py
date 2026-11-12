"""The campaign clock and the lead's actions (BLK-02, SPEC 6.1, 8.2).

The clock looks at every OPEN campaign now and then and asks `decide_campaign_outcome` what should happen. If the answer is
CAPTURE or RELEASE it builds the money plan, stores it and sends it to the Guardian; an ALLOW on these two plan kinds is
approved by the system and the executor takes it from there (SPEC 7.5.1). The clock never moves money itself.

Rules that keep it safe:
  * It never builds a second capture or release plan for a campaign on its own: if any plan exists for the campaign, a human
    decides (the Plans page shows it). A repeated tick therefore changes nothing.
  * The lead's buttons (close, cancel, restart) go through the same builders, with the lead as the proposer, and refuse while
    another plan for the campaign is still in flight.
Flushes only for the lead actions (the endpoint commits); `tick` commits after each campaign so one bad campaign cannot lose
the others.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Campaign, MoneyPlan, Pledge, Project, ProjectMember
from app.services import campaign_ops as ops
from app.services import guardian_rules as g
from app.services import paypal_io
from app.services import plan_builder as pb
from app.services import plan_lifecycle as lc
from app.services.campaign_outcome import decide_campaign_outcome
from app.services.campaign_rules import as_utc
from app.services.state_machines import ProjectService

log = logging.getLogger("briefpay.clock")

CREATED_PLEDGE_MAX_AGE = timedelta(hours=1)      # an order nobody approved is forgotten after an hour
RELAUNCH_HOURS = 48
MONEY_PLAN_KINDS = ("CAPTURE_PLEDGES", "RELEASE_HOLDS")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _guardian_params() -> g.GuardianParams:
    s = get_settings()
    return g.GuardianParams(payout_max_cents=s.payout_max_cents, payout_max_per_hour=s.payout_max_per_hour)


def _default_llm():
    from app.agents.guardian_llm import get_guardian_llm
    return get_guardian_llm()


def campaign_plans(db: Session, campaign_id: int) -> list[MoneyPlan]:
    return list(db.scalars(select(MoneyPlan).where(MoneyPlan.campaign_id == campaign_id, MoneyPlan.kind.in_(MONEY_PLAN_KINDS))
                           .order_by(MoneyPlan.id)))


def _live_cents(db: Session, c: Campaign, now: datetime) -> int:
    return sum(p.amount_cents for p in pb.live_valid_pledges(db, c.id, now))


def _propose(db: Session, c: Campaign, action: str, reason: str, *, proposed_by: str, now: datetime, reader, llm) -> MoneyPlan:
    kind = "CAPTURE_PLEDGES" if action == "CAPTURE" else "RELEASE_HOLDS"
    try:
        built = pb.build(db, kind, project_id=c.project_id, campaign_id=c.id, reason=reason, now=now)
    except pb.PlanBuildError as e:
        raise ops.CampaignError("CANNOT_BUILD_PLAN", str(e)) from e
    plan = pb.save_proposed(db, built, proposed_by=proposed_by)
    db.commit()  # release SQLite write lock before review_plan invokes GuardianLLM._log on a second session
    lc.review_plan(db, plan, reader=reader, params=_guardian_params(), now=now, llm=llm)
    return plan


# ---------------- the clock ----------------

def expire_stale_orders(db: Session, now: datetime) -> int:
    """CREATED pledges (an order started but never approved) older than an hour are forgotten."""
    cutoff, n = now - CREATED_PLEDGE_MAX_AGE, 0
    for p in db.scalars(select(Pledge).where(Pledge.status == "CREATED")):
        if p.created_at is not None and as_utc(p.created_at) < cutoff:
            p.status, n = "EXPIRED", n + 1
    db.flush()
    return n


def tick(db: Session, *, now: datetime | None = None, reader=None, llm=None) -> list[dict]:
    """One pass. Returns what it did, one dict per campaign it acted on or skipped on purpose."""
    now = now or _now()
    reader = reader if reader is not None else paypal_io.get_reader()
    llm = llm if llm is not None else _default_llm()
    out: list[dict] = []
    expired = expire_stale_orders(db, now)
    if expired:
        out.append({"action": "EXPIRED_ORDERS", "count": expired})
    db.commit()
    for cid in [c.id for c in db.scalars(select(Campaign).where(Campaign.state == "OPEN").order_by(Campaign.id))]:
        try:
            r = _tick_campaign(db, db.get(Campaign, cid), now, reader, llm)
            db.commit()
            if r:
                out.append(r)
        except Exception:  # noqa: BLE001  one campaign failing must not stop the others
            db.rollback()
            log.exception("clock: campaign %s failed", cid)
            out.append({"campaign_id": cid, "action": "ERROR"})
    return out


def _tick_campaign(db: Session, c: Campaign, now: datetime, reader, llm) -> dict | None:
    live = _live_cents(db, c, now)
    if c.goal_reached_at is None and live >= c.goal_cents:
        c.goal_reached_at = now
    o = decide_campaign_outcome(state=c.state, goal_cents=c.goal_cents, live_cents=live, now=now, deadline_at=c.deadline_at,
                                close_policy=c.close_policy)
    if o.action == "WAIT":
        return None
    if campaign_plans(db, c.id):
        return {"campaign_id": c.id, "action": "SKIPPED", "why": "PLAN_EXISTS"}      # a human decides from here
    try:
        plan = _propose(db, c, o.action, o.reason or "", proposed_by="system", now=now, reader=reader, llm=llm)
    except ops.CampaignError as e:
        return {"campaign_id": c.id, "action": "SKIPPED", "why": e.code}
    return {"campaign_id": c.id, "action": o.action, "reason": o.reason, "plan_id": plan.id, "plan_state": plan.state}


def run_periodic(session_factory) -> list[dict]:
    """The recurring chore started with the app. Does nothing harmful without PayPal: plans simply fail safe at the Guardian."""
    db = session_factory()
    try:
        return tick(db)
    finally:
        db.close()


# ---------------- the lead's actions ----------------

def _in_flight(db: Session, c: Campaign) -> MoneyPlan | None:
    for p in campaign_plans(db, c.id):
        if p.state not in pb.TERMINAL_PLAN_STATES:
            return p
    return None


def _lead_action(db: Session, c: Campaign, lead: ProjectMember, *, closed: bool, cancelled: bool, reader, llm, now: datetime) -> MoneyPlan:
    if c.state != "OPEN":
        raise ops.CampaignError("CAMPAIGN_STATE", f"Only an open campaign can be closed or cancelled (it is {c.state})")
    busy = _in_flight(db, c)
    if busy is not None:
        raise ops.CampaignError("PLAN_IN_PROGRESS", f"Money plan {busy.id} ({busy.kind}) is already {busy.state}; finish or review it first")
    o = decide_campaign_outcome(state=c.state, goal_cents=c.goal_cents, live_cents=_live_cents(db, c, now), now=now,
                                deadline_at=c.deadline_at, close_policy=c.close_policy, lead_closed=closed, lead_cancelled=cancelled)
    if o.action == "WAIT":
        raise ops.CampaignError("GOAL_NOT_REACHED", "The goal has not been reached by holds PayPal still guarantees, so there is nothing to collect yet")
    reader = reader if reader is not None else paypal_io.get_reader()
    llm = llm if llm is not None else _default_llm()
    return _propose(db, c, o.action, o.reason or "", proposed_by=f"user:{lead.user_id}", now=now, reader=reader, llm=llm)


def close_now(db: Session, c: Campaign, lead: ProjectMember, *, now: datetime | None = None, reader=None, llm=None) -> MoneyPlan:
    """Collect now: only when live holds already cover the goal."""
    return _lead_action(db, c, lead, closed=True, cancelled=False, reader=reader, llm=llm, now=now or _now())


def cancel(db: Session, c: Campaign, lead: ProjectMember, *, now: datetime | None = None, reader=None, llm=None) -> MoneyPlan:
    """Release every hold; nobody is charged."""
    return _lead_action(db, c, lead, closed=False, cancelled=True, reader=reader, llm=llm, now=now or _now())


def relaunch(db: Session, c: Campaign, project: Project, lead: ProjectMember, *, now: datetime | None = None) -> Campaign:
    """Start another round after a failed one: same terms, a fresh 48-hour deadline, ready to launch again."""
    now = now or _now()
    if c.state != "FAILED":
        raise ops.CampaignError("CAMPAIGN_STATE", f"Only a failed campaign can be restarted (it is {c.state})")
    if ops.latest_campaign(db, project.id).id != c.id:
        raise ops.CampaignError("NOT_LATEST", "A newer round already exists")
    if project.state != "CAMPAIGN_FAILED":
        raise ops.CampaignError("PROJECT_STATE", f"The project is {project.state}, not CAMPAIGN_FAILED")
    ProjectService.transition(db, project, "CAMPAIGN_SETUP", actor=f"user:{lead.user_id}", reason=f"restart after round {c.number}")
    return ops.setup_campaign(db, project, lead, deadline_at=now + timedelta(hours=RELAUNCH_HOURS), close_policy=c.close_policy,
                              min_pledge_cents=c.min_pledge_cents, suggested_share_cents=c.suggested_share_cents, now=now)


def expire_deadline_now(db: Session, c: Campaign, *, now: datetime | None = None) -> Campaign:
    """DEMO ONLY (the endpoint is a 404 outside DEMO_MODE): pretend the deadline is now so the clock acts on the next tick."""
    if c.state != "OPEN":
        raise ops.CampaignError("CAMPAIGN_STATE", f"Only an open campaign has a deadline to pull forward (it is {c.state})")
    c.deadline_at = now or _now()
    db.flush()
    return c
