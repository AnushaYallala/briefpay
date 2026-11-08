"""The Pledge Gate (SPEC 8.2): deterministic checks before and after the PayPal popup. Pure, no DB, no clock reads.

A pledge is only a hold; no money moves here. The gate protects the campaign's promises: only an OPEN campaign before its
deadline takes pledges, an amount is within [minimum, what is still needed], the freelancer cannot fund their own job,
and a hold counts only if PayPal itself says it exists for exactly the amount we asked for.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.campaign_rules import as_utc

HONOR_DAYS = 3        # PayPal's honor period: a hold is only guaranteed this long (SPEC 9.6)
VALID_DAYS = 29       # an authorization stays valid this long, but capture after the honor period is not guaranteed
MAX_NAME = 80
ORDERS_PER_USER_PER_HOUR = 10


class GateError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass(frozen=True)
class CampaignFacts:
    state: str
    deadline_at: datetime
    goal_cents: int
    min_pledge_cents: int
    held_cents: int              # Σ AUTHORIZED holds (holds are not money, I-8)
    currency: str


def clean_display_name(raw: str | None) -> str:
    """Public text: collapse whitespace, no control characters, 1..80 chars."""
    name = re.sub(r"\s+", " ", raw or "").strip()
    if not name:
        raise GateError("BAD_NAME", "Please enter the name to show on the pledge board", 422)
    if len(name) > MAX_NAME:
        raise GateError("BAD_NAME", f"The display name can be at most {MAX_NAME} characters", 422)
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise GateError("BAD_NAME", "The display name contains characters that are not allowed", 422)
    return name


def check_new_pledge(c: CampaignFacts, *, amount_cents: int, role: str | None, now: datetime) -> None:
    """Raise GateError unless this pledge may be started. `role` is the caller's project role, if any."""
    if role == "FREELANCER":
        raise GateError("FREELANCER_CANNOT_PLEDGE", "The freelancer cannot fund their own job", 403)
    if c.state != "OPEN":
        raise GateError("CAMPAIGN_NOT_OPEN", f"This campaign is {c.state.lower()}; it is not taking pledges")
    if as_utc(now) >= as_utc(c.deadline_at):
        raise GateError("DEADLINE_PASSED", "The deadline has passed; this campaign is no longer taking pledges")
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
        raise GateError("BAD_AMOUNT", "The amount must be a positive whole number of cents", 422)
    remaining = c.goal_cents - c.held_cents
    if remaining <= 0:
        raise GateError("GOAL_REACHED", "The goal has already been reached; no more pledges are needed")
    if amount_cents < c.min_pledge_cents:
        raise GateError("BELOW_MINIMUM", f"The minimum pledge is {c.min_pledge_cents} cents", 422)
    if amount_cents > remaining:
        raise GateError("ABOVE_NEED", f"Only {remaining} cents are still needed", 422)


def check_authorize_allowed(c: CampaignFacts, *, now: datetime) -> None:
    """Before asking PayPal to place a hold on an approved order: the campaign must still be taking pledges.
    (An over-pledge from a race is allowed; the capture plan splits pro-rata so the total is exactly the goal.)"""
    if c.state != "OPEN":
        raise GateError("CAMPAIGN_CLOSED", f"This campaign is {c.state.lower()}; no hold was placed")
    if as_utc(now) >= as_utc(c.deadline_at):
        raise GateError("CAMPAIGN_CLOSED", "The deadline passed before the pledge was authorized; no hold was placed")


def check_hold(*, pledge_amount_cents: int, campaign_currency: str, auth: dict | None) -> None:
    """After PayPal answers: the hold counts only if PayPal says CREATED, for exactly the ordered amount and currency."""
    if not auth:
        raise GateError("PLEDGE_DECLINED", "PayPal did not place a hold. Was the payment approved?", 402)
    if auth.get("status") != "CREATED":
        raise GateError("PLEDGE_DECLINED", f"PayPal did not place the hold (status {auth.get('status')})", 402)
    if auth.get("amount_cents") != pledge_amount_cents or auth.get("currency") != campaign_currency:
        raise GateError("HOLD_MISMATCH", "PayPal placed a hold that does not match the pledge; it was not counted", 409)


def hold_times(authorized_at: datetime) -> tuple[datetime, datetime]:
    """(honor_until, valid_until) from the moment the hold was placed."""
    t = as_utc(authorized_at)
    return t + timedelta(days=HONOR_DAYS), t + timedelta(days=VALID_DAYS)
