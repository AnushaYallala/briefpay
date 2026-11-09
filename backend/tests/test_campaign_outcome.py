from datetime import datetime, timedelta, timezone
from itertools import product

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.campaign_outcome import Outcome, decide_campaign_outcome

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(hours=10)
PAST = NOW - timedelta(hours=1)
GOAL = 40000


def decide(live=0, deadline=FUTURE, policy="EARLY_ON_GOAL", state="OPEN", now=NOW, **kw):
    return decide_campaign_outcome(state=state, goal_cents=GOAL, live_cents=live, now=now, deadline_at=deadline, close_policy=policy, **kw)


# ---------------- the plain cases ----------------

def test_waiting_while_the_goal_is_not_reached_and_time_remains():
    assert decide(live=0) == Outcome("WAIT", None)
    assert decide(live=GOAL - 1) == Outcome("WAIT", None)


def test_early_on_goal_captures_as_soon_as_the_goal_is_met():
    assert decide(live=GOAL) == Outcome("CAPTURE", "GOAL_REACHED")
    assert decide(live=GOAL + 5000) == Outcome("CAPTURE", "GOAL_REACHED")           # an over-pledge race still captures


def test_at_deadline_policy_waits_until_the_deadline_or_the_lead_closes():
    assert decide(live=GOAL, policy="AT_DEADLINE") == Outcome("WAIT", None)
    assert decide(live=GOAL, policy="AT_DEADLINE", lead_closed=True) == Outcome("CAPTURE", "LEAD_CLOSE")
    assert decide(live=GOAL, policy="AT_DEADLINE", deadline=PAST) == Outcome("CAPTURE", "DEADLINE_MET")


def test_a_missed_deadline_releases_every_hold():
    assert decide(live=GOAL - 1, deadline=PAST) == Outcome("RELEASE", "DEADLINE_MISSED")
    assert decide(live=0, deadline=PAST) == Outcome("RELEASE", "DEADLINE_MISSED")
    assert decide(live=GOAL - 1, deadline=PAST, policy="AT_DEADLINE") == Outcome("RELEASE", "DEADLINE_MISSED")


def test_the_goal_counts_even_if_nobody_clicked_when_the_deadline_passes():
    """SPEC 6.1: 'deadline passed, authorized >= goal -> CAPTURING'."""
    assert decide(live=GOAL, deadline=PAST, policy="AT_DEADLINE").action == "CAPTURE"
    assert decide(live=GOAL, deadline=PAST, policy="EARLY_ON_GOAL").action == "CAPTURE"


def test_the_lead_can_cancel_at_any_time_and_cancel_beats_everything():
    assert decide(live=0, lead_cancelled=True) == Outcome("RELEASE", "LEAD_CANCEL")
    assert decide(live=GOAL, lead_cancelled=True) == Outcome("RELEASE", "LEAD_CANCEL")             # even when funded
    assert decide(live=GOAL, deadline=PAST, lead_cancelled=True, lead_closed=True) == Outcome("RELEASE", "LEAD_CANCEL")


def test_closing_before_the_goal_is_met_does_nothing_and_says_why():
    assert decide(live=GOAL - 1, lead_closed=True) == Outcome("WAIT", "GOAL_NOT_REACHED")
    assert decide(live=GOAL - 1, lead_closed=True, deadline=PAST) == Outcome("WAIT", "GOAL_NOT_REACHED")   # the clock handles the miss


def test_the_deadline_instant_itself_counts_as_passed():
    assert decide(live=0, deadline=NOW) == Outcome("RELEASE", "DEADLINE_MISSED")
    assert decide(live=0, deadline=NOW + timedelta(seconds=1)) == Outcome("WAIT", None)


def test_naive_datetimes_are_read_as_utc():
    assert decide(live=0, deadline=NOW.replace(tzinfo=None), now=NOW.replace(tzinfo=None)).action == "RELEASE"


# ---------------- nothing happens to a campaign that is not open ----------------

@pytest.mark.parametrize("state", ["SETUP", "CAPTURING", "CAPTURED", "FAILING", "FAILED", "CANCELLED"])
@pytest.mark.parametrize("flags", [dict(), dict(lead_closed=True), dict(lead_cancelled=True)])
def test_only_an_open_campaign_can_be_acted_on(state, flags):
    for live, deadline in ((0, FUTURE), (GOAL, FUTURE), (0, PAST), (GOAL, PAST)):
        assert decide(live=live, deadline=deadline, state=state, **flags) == Outcome("WAIT", "NOT_OPEN")


# ---------------- exhaustive and property checks ----------------

def test_every_combination_gives_exactly_one_well_defined_answer():
    seen = set()
    for live, past, policy, closed, cancelled in product((0, GOAL - 1, GOAL, GOAL + 1), (False, True), ("EARLY_ON_GOAL", "AT_DEADLINE"),
                                                         (False, True), (False, True)):
        out = decide(live=live, deadline=PAST if past else FUTURE, policy=policy, lead_closed=closed, lead_cancelled=cancelled)
        assert out.action in ("WAIT", "CAPTURE", "RELEASE")
        assert (out.action == "WAIT") == (out.reason in (None, "GOAL_NOT_REACHED"))
        seen.add(out.action)
    assert seen == {"WAIT", "CAPTURE", "RELEASE"}


@given(live=st.integers(0, 80000), past=st.booleans(), policy=st.sampled_from(["EARLY_ON_GOAL", "AT_DEADLINE"]),
       closed=st.booleans())
def test_property_money_is_never_captured_below_the_goal_nor_released_at_or_above_it(live, past, policy, closed):
    out = decide(live=live, deadline=PAST if past else FUTURE, policy=policy, lead_closed=closed)
    if out.action == "CAPTURE":
        assert live >= GOAL
    if out.action == "RELEASE":
        assert live < GOAL and past, "without a cancel, only a missed deadline releases"


@given(live=st.integers(0, 80000), past=st.booleans(), policy=st.sampled_from(["EARLY_ON_GOAL", "AT_DEADLINE"]))
def test_property_a_cancel_always_releases_an_open_campaign(live, past, policy):
    assert decide(live=live, deadline=PAST if past else FUTURE, policy=policy, lead_cancelled=True) == Outcome("RELEASE", "LEAD_CANCEL")
