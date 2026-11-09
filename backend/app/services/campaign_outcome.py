"""What should happen to an OPEN campaign right now? A pure function (SPEC 6.1, 8.2). No DB, no clock reads.

  lead cancels                                  -> RELEASE (LEAD_CANCEL)       every hold is voided, nobody is charged
  live holds >= goal AND (EARLY_ON_GOAL, or the lead closed, or the deadline has passed)
                                                -> CAPTURE                      "goal reached counts even if nobody clicked"
  deadline passed AND live holds < goal         -> RELEASE (DEADLINE_MISSED)
  otherwise                                     -> WAIT

`live_cents` is the sum of holds PayPal still guarantees (inside the honor period), not merely 'AUTHORIZED' rows.
"""
from dataclasses import dataclass
from datetime import datetime

from app.services.campaign_rules import as_utc


@dataclass(frozen=True)
class Outcome:
    action: str                # WAIT | CAPTURE | RELEASE
    reason: str | None = None  # GOAL_REACHED | LEAD_CLOSE | DEADLINE_MET | DEADLINE_MISSED | LEAD_CANCEL | GOAL_NOT_REACHED | NOT_OPEN


def decide_campaign_outcome(*, state: str, goal_cents: int, live_cents: int, now: datetime, deadline_at: datetime,
                            close_policy: str, lead_closed: bool = False, lead_cancelled: bool = False) -> Outcome:
    if state != "OPEN":
        return Outcome("WAIT", "NOT_OPEN")
    if lead_cancelled:
        return Outcome("RELEASE", "LEAD_CANCEL")
    deadline_passed = as_utc(now) >= as_utc(deadline_at)
    goal_met = live_cents >= goal_cents
    if goal_met:
        if lead_closed:
            return Outcome("CAPTURE", "LEAD_CLOSE")
        if close_policy == "EARLY_ON_GOAL":
            return Outcome("CAPTURE", "GOAL_REACHED")
        if deadline_passed:
            return Outcome("CAPTURE", "DEADLINE_MET")
        return Outcome("WAIT", None)
    if lead_closed:
        return Outcome("WAIT", "GOAL_NOT_REACHED")
    if deadline_passed:
        return Outcome("RELEASE", "DEADLINE_MISSED")
    return Outcome("WAIT", None)
