"""Pure campaign rules (SPEC 8.2, 9.6, D-018). No DB, no clock reads: callers pass `now` / `opens_at`.

A PayPal hold is only guaranteed for the 3-day honor period, and every pledge is made at or after `opens_at`, so a
campaign deadline may be at most `opens_at + PLEDGE_MAX_HOURS - HONOR_SAFETY_MARGIN_HOURS`. Even the earliest hold is
then still inside its honor period when the campaign ends.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

MIN_CAMPAIGN_HOURS = 1          # a campaign shorter than this is not a campaign
FEE_ITEMS = 1                   # the freelancer payout is a single Payouts item (SPEC 7.5.1, 8.7)


class CampaignRuleError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class CampaignParams:
    pledge_max_hours: int = 72
    honor_safety_margin_hours: int = 2
    pledge_min_cents: int = 500
    fee_reserve_per_item_cents: int = 0


def as_utc(dt: datetime) -> datetime:
    """Naive datetimes are taken to be UTC (SQLite returns them naive); aware ones are converted."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def goal_for(contract_amount_cents: int, fee_reserve_per_item_cents: int) -> tuple[int, int]:
    """(goal_cents, fee_reserve_cents). Goal = contract amount + payout fees, so there is never a surplus to refund."""
    reserve = fee_reserve_per_item_cents * FEE_ITEMS
    return contract_amount_cents + reserve, reserve


def deadline_window(opens_at: datetime, p: CampaignParams) -> tuple[datetime, datetime]:
    """(earliest, latest) allowed deadline for a campaign that opens at `opens_at`."""
    opens = as_utc(opens_at)
    return (opens + timedelta(hours=MIN_CAMPAIGN_HOURS),
            opens + timedelta(hours=p.pledge_max_hours - p.honor_safety_margin_hours))


def validate_deadline(deadline_at: datetime, opens_at: datetime, p: CampaignParams) -> datetime:
    """Raise CampaignRuleError unless the deadline fits the window. Returns the deadline in UTC."""
    earliest, latest = deadline_window(opens_at, p)
    d = as_utc(deadline_at)
    if d < earliest:
        raise CampaignRuleError("DEADLINE_TOO_SOON", f"The deadline must be at least {MIN_CAMPAIGN_HOURS} hour after the campaign opens "
                                f"(earliest {earliest.isoformat()})")
    if d > latest:
        raise CampaignRuleError(
            "DEADLINE_TOO_LATE",
            f"PayPal only guarantees a hold for 3 days, so a campaign can run at most {p.pledge_max_hours - p.honor_safety_margin_hours} "
            f"hours after it opens (latest {latest.isoformat()})")
    return d


def validate_terms(goal_cents: int, min_pledge_cents: int | None, suggested_share_cents: int | None, close_policy: str,
                   p: CampaignParams) -> int:
    """Validate the lead's choices; returns the effective minimum pledge."""
    if close_policy not in ("EARLY_ON_GOAL", "AT_DEADLINE"):
        raise CampaignRuleError("BAD_CLOSE_POLICY", "close_policy must be EARLY_ON_GOAL or AT_DEADLINE")
    mn = p.pledge_min_cents if min_pledge_cents is None else min_pledge_cents
    if not 100 <= mn <= goal_cents:
        raise CampaignRuleError("BAD_MIN_PLEDGE", f"The minimum pledge must be between 100 cents and the goal ({goal_cents} cents)")
    if suggested_share_cents is not None and not mn <= suggested_share_cents <= goal_cents:
        raise CampaignRuleError("BAD_SHARE", "The suggested share must be between the minimum pledge and the goal")
    return mn
