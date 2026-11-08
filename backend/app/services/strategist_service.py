"""Strategist reports and the lead's 'apply' (SPEC 7.4, 10). Reads pledges and invitees, never writes money. Flushes only."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campaign, Pledge, Project, ProjectMember, StrategistReport, User
from app.services import campaign_ops, campaign_rules
from app.services import strategist_math as sm
from app.services.campaign_rules import as_utc

LIVE_PLEDGE_STATES = ("AUTHORIZED", "CAPTURED")


class StrategistError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def latest_report(db: Session, campaign_id: int) -> StrategistReport | None:
    return db.scalars(select(StrategistReport).where(StrategistReport.campaign_id == campaign_id)
                      .order_by(StrategistReport.id.desc())).first()


def extension_applied(db: Session, campaign_id: int) -> bool:
    return any((r.suggestions_json or {}).get("applied_extension")
               for r in db.scalars(select(StrategistReport).where(StrategistReport.campaign_id == campaign_id)))


def gather(db: Session, c: Campaign) -> tuple[list[sm.Invitee], list[sm.SupporterPledge]]:
    pledges = list(db.scalars(select(Pledge).where(Pledge.campaign_id == c.id, Pledge.status.in_(LIVE_PLEDGE_STATES))))
    pledged_members = {p.member_id for p in pledges if p.member_id is not None}
    rows = db.execute(select(ProjectMember, User.display_name).join(User, User.id == ProjectMember.user_id).where(
        ProjectMember.project_id == c.project_id, ProjectMember.role.in_(("LEAD", "SPONSOR"))).order_by(ProjectMember.id)).all()
    invitees = [sm.Invitee(m.id, name, m.invite_status, m.expected_pledge_cents, m.id in pledged_members) for m, name in rows]
    supporters = [sm.SupporterPledge(p.amount_cents, p.authorized_at) for p in pledges if p.supporter_user_id is not None and p.authorized_at]
    return invitees, supporters


def compute(db: Session, c: Campaign, now: datetime) -> dict:
    """The forecast, the deadline advice for the campaign's stage, and the nudge ranking. Pure of side effects."""
    if c.state not in ("SETUP", "OPEN"):
        raise StrategistError("CAMPAIGN_STATE", f"The Strategist advises on campaigns in SETUP or OPEN (this one is {c.state})")
    invitees, supporters = gather(db, c)
    held = campaign_ops.pledge_totals(db, c)["held_cents"]
    params = campaign_ops.params()
    f = sm.forecast(goal_cents=c.goal_cents, pledged_cents=held, now=now, deadline_at=c.deadline_at, invitees=invitees, supporter_pledges=supporters)
    if c.state == "SETUP":
        kind, deadline = "SETUP", sm.suggest_deadline_for_setup(goal_cents=c.goal_cents, now=now, invitees=invitees, params=params)
    else:
        deadline = sm.suggest_extension(probability=f["probability"], hours_left=f["hours_left"], deadline_at=c.deadline_at,
                                        opens_at=c.opens_at or now, extension_used=extension_applied(db, c.id), params=params)
        kind = "EXTEND" if deadline else None
    return {"forecast": f, "suggestions": {"kind": kind, "deadline": deadline, "nudge_targets": sm.nudge_targets(invitees),
                                           "campaign_state": c.state}}


def run_report(db: Session, c: Campaign, now: datetime | None = None) -> StrategistReport:
    out = compute(db, c, now or _now())
    r = StrategistReport(campaign_id=c.id, forecast_json=out["forecast"], suggestions_json=out["suggestions"])
    db.add(r)
    db.flush()
    return r


def apply_deadline(db: Session, c: Campaign, project: Project, deadline_at: datetime | None, now: datetime | None = None) -> Campaign:
    """SETUP: any deadline the window allows. OPEN: exactly one extension, later than the current deadline and inside the
    3-day honor limit measured from when the campaign opened. With no deadline given, the latest suggestion is used."""
    now = now or _now()
    report = latest_report(db, c.id)
    if deadline_at is None:
        suggested = ((report.suggestions_json or {}).get("deadline") or {}).get("deadline_at") if report else None
        if not suggested:
            raise StrategistError("NO_SUGGESTION", "There is no suggested deadline to apply; send a deadline_at or run the Strategist first")
        deadline_at = datetime.fromisoformat(suggested)
    params = campaign_ops.params()
    try:
        if c.state == "SETUP":
            new = campaign_rules.validate_deadline(deadline_at, now, params)
        elif c.state == "OPEN":
            if extension_applied(db, c.id):
                raise StrategistError("EXTENSION_USED", "The deadline has already been extended once")
            new = campaign_rules.validate_deadline(deadline_at, c.opens_at or now, params)
            if new <= as_utc(c.deadline_at):
                raise StrategistError("NOT_AN_EXTENSION", "An open campaign's deadline can only be extended, never shortened")
        else:
            raise StrategistError("CAMPAIGN_STATE", f"The deadline can be changed in SETUP or OPEN (this campaign is {c.state})")
    except campaign_rules.CampaignRuleError as e:
        raise StrategistError(e.code, e.message, 422) from e
    old = as_utc(c.deadline_at)
    c.deadline_at = new
    if c.state == "OPEN":  # remember it, so the one-time extension cannot be used twice
        report = report or run_report(db, c, now)
        report.suggestions_json = {**(report.suggestions_json or {}), "applied_extension": {"from": old.isoformat(), "to": new.isoformat(), "at": now.isoformat()}}
    db.flush()
    return c
