"""Campaign Strategist: the deterministic forecast, deadline advice and nudge ranking (SPEC 7.4). Pure; time is passed in.

Advisory only: it never moves money or contacts anyone. With no history the probability is a transparent heuristic,
labelled 'estimate (heuristic)'; an LLM (T-47, optional) may only word what this code computed.

  pledged       = sum of held (AUTHORIZED) amounts
  expected_inv  = sum over invitees who have not pledged of conv(status) * expected_pledge
  recent_rate   = supporter pledges in the last 6 h / 6                  (cents per hour)
  expected_open = recent_rate * hours_left * 0.5
  projected     = pledged + expected_inv + expected_open
  p             = 1 if pledged >= goal; 0 if no time is left and pledged < goal;
                  else clamp(1 / (1 + exp(-6 * (projected / goal - 1))), 0.02, 0.98)
"""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.campaign_rules import CampaignParams, as_utc, deadline_window

# Tunable constants (SPEC 7.4). Changing one changes every forecast; keep them here and nowhere else.
CONVERSION = {"DECLINED": 0.0, "VIEWED": 0.55, "INVITED": 0.30}
RECENT_WINDOW_HOURS = 6
OPEN_DISCOUNT = 0.5
LOGISTIC_STEEPNESS = 6
P_MIN, P_MAX = 0.02, 0.98
DEFAULT_HOURS = 48
LOW_INITIAL_P = 0.5            # below this at setup, suggest the longest allowed campaign
EXTEND_IF_P_BELOW = 0.6
EXTEND_IF_HOURS_LEFT_BELOW = 24
LABEL = "estimate (heuristic)"


@dataclass(frozen=True)
class Invitee:
    member_id: int
    name: str
    invite_status: str            # INVITED | VIEWED | PLEDGED | DECLINED (as recorded on the member)
    expected_pledge_cents: int | None
    has_pledged: bool             # holds a live pledge in THIS campaign


@dataclass(frozen=True)
class SupporterPledge:
    amount_cents: int
    at: datetime


def conversion(status: str) -> float:
    return CONVERSION.get(status, CONVERSION["INVITED"])


def hours_between(later: datetime, earlier: datetime) -> float:
    return (as_utc(later) - as_utc(earlier)).total_seconds() / 3600


def forecast(*, goal_cents: int, pledged_cents: int, now: datetime, deadline_at: datetime, invitees: list[Invitee],
             supporter_pledges: list[SupporterPledge]) -> dict:
    hours_left = max(0.0, hours_between(deadline_at, now))
    expected_inv = sum(conversion(i.invite_status) * (i.expected_pledge_cents or 0) for i in invitees if not i.has_pledged)
    since = as_utc(now) - timedelta(hours=RECENT_WINDOW_HOURS)
    recent_rate = sum(p.amount_cents for p in supporter_pledges if as_utc(p.at) > since) / RECENT_WINDOW_HOURS
    expected_open = recent_rate * hours_left * OPEN_DISCOUNT
    projected = pledged_cents + expected_inv + expected_open
    ratio = projected / goal_cents
    if pledged_cents >= goal_cents:
        p = 1.0
    elif hours_left == 0:
        p = 0.0
    else:
        p = min(P_MAX, max(P_MIN, 1 / (1 + math.exp(-LOGISTIC_STEEPNESS * (ratio - 1)))))
    return {"label": LABEL, "goal_cents": goal_cents, "pledged_cents": pledged_cents, "gap_cents": max(0, goal_cents - pledged_cents),
            "hours_left": round(hours_left, 2), "expected_invitees_cents": round(expected_inv), "expected_open_cents": round(expected_open),
            "projected_cents": round(projected), "ratio": round(ratio, 4), "probability": round(p, 4)}


def suggest_deadline_for_setup(*, goal_cents: int, now: datetime, invitees: list[Invitee], params: CampaignParams) -> dict:
    """Default 48 h; if the initial forecast is weak (p0 < 0.5) suggest the longest the honor period allows."""
    _, latest = deadline_window(now, params)
    default = as_utc(now) + timedelta(hours=DEFAULT_HOURS)
    p0 = forecast(goal_cents=goal_cents, pledged_cents=0, now=now, deadline_at=default, invitees=invitees, supporter_pledges=[])["probability"]
    if p0 < LOW_INITIAL_P:
        return {"deadline_at": latest.isoformat(), "hours": round(hours_between(latest, now), 1), "initial_probability": p0,
                "reason": "The expected pledges are well below the goal, so run the campaign as long as PayPal's 3-day guarantee allows."}
    return {"deadline_at": default.isoformat(), "hours": DEFAULT_HOURS, "initial_probability": p0,
            "reason": "The expected pledges make the goal look reachable in the default 48 hours."}


def suggest_extension(*, probability: float, hours_left: float, deadline_at: datetime, opens_at: datetime, extension_used: bool,
                      params: CampaignParams) -> dict | None:
    """One-time extension while OPEN: only extends, never shortens, never past the honor limit."""
    if extension_used or probability >= EXTEND_IF_P_BELOW or hours_left >= EXTEND_IF_HOURS_LEFT_BELOW:
        return None
    _, latest = deadline_window(opens_at, params)
    if latest <= as_utc(deadline_at):
        return None
    return {"deadline_at": latest.isoformat(), "reason": "The goal is at risk with less than 24 hours left; extend to the longest the 3-day hold guarantee allows."}


def nudge_targets(invitees: list[Invitee]) -> list[dict]:
    """Invitees who have not pledged, most promising first: conv(status) * expected pledge."""
    rows = []
    for i in invitees:
        if i.has_pledged or i.invite_status == "DECLINED":
            continue
        weight = conversion(i.invite_status) * (i.expected_pledge_cents or 0)
        reason = "hasn't opened the link" if i.invite_status == "INVITED" else "has seen the campaign but not pledged"
        if i.expected_pledge_cents:
            reason += f", said ${i.expected_pledge_cents // 100}" + (f".{i.expected_pledge_cents % 100:02d}" if i.expected_pledge_cents % 100 else "")
        rows.append({"member_id": i.member_id, "name": i.name, "invite_status": i.invite_status,
                     "expected_pledge_cents": i.expected_pledge_cents, "score": round(weight), "reason": reason})
    return sorted(rows, key=lambda r: (-r["score"], r["member_id"]))
