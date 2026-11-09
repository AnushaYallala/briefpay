"""Campaign setup, launch and the public view (SPEC 8.2, 6.1, 10). Flushes only; the caller owns the transaction."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Campaign, Pledge, Project, ProjectMember
from app.services import campaign_rules as rules
from app.services import contract_service
from app.services.state_machines import CampaignService, ProjectService

LIVE_STATES = ("OPEN", "CAPTURING", "FAILING")


class CampaignError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def params() -> rules.CampaignParams:
    s = get_settings()
    return rules.CampaignParams(s.pledge_max_hours, s.honor_safety_margin_hours, s.pledge_min_cents, s.fee_reserve_per_item_cents)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def latest_campaign(db: Session, project_id: int) -> Campaign | None:
    return db.scalars(select(Campaign).where(Campaign.project_id == project_id).order_by(Campaign.number.desc())).first()


def _rule_error(e: rules.CampaignRuleError) -> CampaignError:
    return CampaignError(e.code, e.message, 422)


def setup_campaign(db: Session, project: Project, lead: ProjectMember, *, deadline_at: datetime, close_policy: str | None,
                   min_pledge_cents: int | None, suggested_share_cents: int | None, now: datetime | None = None) -> Campaign:
    """Create the SETUP campaign, or update the existing SETUP one. The goal comes from the signed contract."""
    now = now or _now()
    if project.state != "CAMPAIGN_SETUP":
        raise CampaignError("PROJECT_STATE", f"A campaign is set up while the project is in CAMPAIGN_SETUP (it is {project.state})")
    contract = contract_service.get_contract(db, project.id)
    if contract is None or contract.signed_at is None:
        raise CampaignError("CONTRACT_NOT_SIGNED", "The freelancer must sign the contract before a campaign can be set up")
    last = latest_campaign(db, project.id)
    if last is not None and last.state in LIVE_STATES:
        raise CampaignError("CAMPAIGN_LIVE", f"Campaign round {last.number} is {last.state}")
    p = params()
    goal, reserve = rules.goal_for(contract.amount_cents, p.fee_reserve_per_item_cents)
    policy = close_policy or get_settings().default_close_policy
    try:
        mn = rules.validate_terms(goal, min_pledge_cents, suggested_share_cents, policy, p)
        deadline = rules.validate_deadline(deadline_at, now, p)  # as if it opened right now; re-checked at launch
    except rules.CampaignRuleError as e:
        raise _rule_error(e) from e

    if last is not None and last.state == "SETUP":
        c = last
    else:
        c = Campaign(project_id=project.id, number=(last.number + 1) if last else 1, proposer_member_id=lead.id)
        db.add(c)
    c.goal_cents, c.fee_reserve_cents, c.currency = goal, reserve, project.currency
    c.min_pledge_cents, c.suggested_share_cents, c.close_policy, c.deadline_at = mn, suggested_share_cents, policy, deadline
    c.state = "SETUP"
    db.flush()
    return c


def blocker_details(db: Session, project: Project, c: Campaign, now: datetime) -> list[tuple[str, str, int]]:
    """Why 'Launch' is disabled: (code, plain-words message, HTTP status). Every disabled button explains itself (SPEC 11.2)."""
    out: list[tuple[str, str, int]] = []
    if c.state != "SETUP":
        return out
    if project.state != "CAMPAIGN_SETUP":
        out.append(("CANNOT_LAUNCH", f"The project is {project.state}, not CAMPAIGN_SETUP.", 409))
    contract = contract_service.get_contract(db, project.id)
    if contract is None or contract.signed_at is None:
        out.append(("CANNOT_LAUNCH", "The freelancer has not signed the contract yet.", 409))
    try:
        rules.validate_deadline(c.deadline_at, now, params())
    except rules.CampaignRuleError as e:
        out.append((e.code, e.message, 422))
    return out


def blockers(db: Session, project: Project, c: Campaign, now: datetime) -> list[str]:
    return [msg for _, msg, _ in blocker_details(db, project, c, now)]


def launch(db: Session, project: Project, c: Campaign, now: datetime | None = None) -> Campaign:
    now = now or _now()
    if c.state != "SETUP":
        raise CampaignError("CAMPAIGN_STATE", f"Only a campaign in SETUP can be launched (it is {c.state})")
    problems = blocker_details(db, project, c, now)
    if problems:
        code, _, status = problems[-1] if problems[-1][2] == 422 else problems[0]
        raise CampaignError(code, " ".join(msg for _, msg, _ in problems), status)
    c.opens_at = now
    CampaignService.transition(db, c, "OPEN", actor=f"user:{db.get(ProjectMember, c.proposer_member_id).user_id}")
    ProjectService.transition(db, project, "PLEDGING", actor="system", reason=f"campaign round {c.number} launched")
    db.flush()
    return c


def pledge_totals(db: Session, c: Campaign) -> dict:
    """Σ over AUTHORIZED holds is 'pledged'; after capture the actual captured amounts. Holds are not money (I-8)."""
    rows = db.execute(select(Pledge.status, Pledge.amount_cents, Pledge.captured_cents).where(
        Pledge.campaign_id == c.id, Pledge.status.in_(("AUTHORIZED", "CAPTURED")))).all()
    held = sum(a for st, a, _ in rows if st == "AUTHORIZED")
    pledged = sum(cap if st == "CAPTURED" else a for st, a, cap in rows)
    return {"pledged_cents": pledged, "pledge_count": len(rows), "held_cents": held}


def campaign_view(db: Session, c: Campaign, project: Project, viewer: ProjectMember | None, now: datetime | None = None) -> dict:
    now = now or _now()
    t = pledge_totals(db, c)
    deadline = rules.as_utc(c.deadline_at)
    out = {
        "id": c.id, "project_id": project.id, "project_title": project.title, "number": c.number, "state": c.state,
        "goal_cents": c.goal_cents, "fee_reserve_cents": c.fee_reserve_cents, "currency": c.currency,
        "min_pledge_cents": c.min_pledge_cents, "suggested_share_cents": c.suggested_share_cents, "close_policy": c.close_policy,
        "opens_at": rules.as_utc(c.opens_at).isoformat() if c.opens_at else None, "deadline_at": deadline.isoformat(),
        "seconds_left": max(0, int((deadline - now).total_seconds())) if c.state == "OPEN" else 0,
        "pledged_cents": t["pledged_cents"], "pledge_count": t["pledge_count"],
        "remaining_need_cents": max(0, c.goal_cents - t["held_cents"]) if c.state in ("SETUP", "OPEN") else 0,
        "goal_reached_at": rules.as_utc(c.goal_reached_at).isoformat() if c.goal_reached_at else None,
        # SPEC 11.2: pledge screens always say 'held, not charged' until the capture plan is DONE
        "held_not_charged": c.state != "CAPTURED", "fail_reason": c.fail_reason,
    }
    if viewer is not None and viewer.role == "LEAD":
        earliest, latest = rules.deadline_window(now if c.state == "SETUP" else (c.opens_at or now), params())
        honors = [rules.as_utc(h) for (h,) in db.execute(select(Pledge.honor_until).where(
            Pledge.campaign_id == c.id, Pledge.status == "AUTHORIZED", Pledge.honor_until.is_not(None)))]
        out["lead"] = {"launch_blockers": blockers(db, project, c, now), "can_launch": c.state == "SETUP" and not blockers(db, project, c, now),
                       "deadline_earliest": earliest.isoformat(), "deadline_latest": latest.isoformat(),
                       "earliest_honor_until": min(honors).isoformat() if honors else None}
    return out
