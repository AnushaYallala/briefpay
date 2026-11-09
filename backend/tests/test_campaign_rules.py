from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services import campaign_rules as r

P = r.CampaignParams(pledge_max_hours=72, honor_safety_margin_hours=2, pledge_min_cents=500, fee_reserve_per_item_cents=0)
OPENS = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def check(deadline, opens=OPENS, params=P):
    return r.validate_deadline(deadline, opens, params)


def refused(deadline, code, opens=OPENS, params=P):
    with pytest.raises(r.CampaignRuleError) as e:
        check(deadline, opens, params)
    assert e.value.code == code


# ---------------- the goal ----------------

def test_the_goal_is_the_contract_amount_plus_payout_fees():
    assert r.goal_for(40000, 0) == (40000, 0)
    assert r.goal_for(40000, 25) == (40025, 25)
    assert r.goal_for(1, 0) == (1, 0)


# ---------------- the deadline window ----------------

def test_the_window_is_one_hour_to_seventy_hours_after_opening():
    earliest, latest = r.deadline_window(OPENS, P)
    assert earliest == OPENS + timedelta(hours=1) and latest == OPENS + timedelta(hours=70)


def test_the_window_follows_the_settings():
    assert r.deadline_window(OPENS, r.CampaignParams(48, 4))[1] == OPENS + timedelta(hours=44)
    assert r.deadline_window(OPENS, r.CampaignParams(72, 0))[1] == OPENS + timedelta(hours=72)


@pytest.mark.parametrize("delta,ok", [
    (timedelta(hours=1), True), (timedelta(hours=1) - timedelta(seconds=1), False), (timedelta(hours=48), True),
    (timedelta(hours=70), True), (timedelta(hours=70, seconds=1), False), (timedelta(hours=72), False),
    (timedelta(days=10), False), (timedelta(0), False), (timedelta(hours=-5), False),
])
def test_the_window_edges_are_exact(delta, ok):
    if ok:
        assert check(OPENS + delta) == OPENS + delta
    else:
        refused(OPENS + delta, "DEADLINE_TOO_SOON" if delta < timedelta(hours=1) else "DEADLINE_TOO_LATE")


def test_naive_datetimes_are_taken_as_utc_and_other_zones_are_converted():
    assert check(datetime(2026, 11, 11, 12, 0)) == datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
    ist = timezone(timedelta(hours=5, minutes=30))
    got = check(datetime(2026, 11, 11, 17, 30, tzinfo=ist))
    assert got == datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc) and got.utcoffset() == timedelta(0)
    # the latest allowed instant is Nov 13 10:00 UTC (70 h after opening) = Nov 13 15:30 IST
    assert check(datetime(2026, 11, 13, 15, 30, tzinfo=ist)) == datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
    refused(datetime(2026, 11, 13, 15, 31, tzinfo=ist), "DEADLINE_TOO_LATE")


@given(minutes=st.integers(min_value=-600, max_value=20000))
def test_property_the_window_matches_the_arithmetic(minutes):
    d = OPENS + timedelta(minutes=minutes)
    if 60 <= minutes <= 70 * 60:
        assert check(d) == d
    else:
        with pytest.raises(r.CampaignRuleError):
            check(d)


@given(deadline_minutes=st.integers(min_value=60, max_value=70 * 60), data=st.data())
def test_property_no_hold_is_older_than_the_honor_period_when_the_campaign_ends(deadline_minutes, data):
    """The reason for the cap: every pledge is made at or after opens_at, so for ANY deadline the rules accept and ANY
    pledge time before it, the hold is younger than PayPal's 72-hour guarantee when the campaign ends."""
    deadline = check(OPENS + timedelta(minutes=deadline_minutes))
    pledge_at = OPENS + timedelta(minutes=data.draw(st.integers(min_value=0, max_value=deadline_minutes)))
    assert timedelta(0) <= deadline - pledge_at < timedelta(hours=P.pledge_max_hours)
    assert deadline - pledge_at <= timedelta(hours=P.pledge_max_hours - P.honor_safety_margin_hours)


# ---------------- the lead's choices ----------------

def test_terms_validation():
    assert r.validate_terms(40000, None, None, "EARLY_ON_GOAL", P) == 500                      # default minimum
    assert r.validate_terms(40000, 100, 100, "AT_DEADLINE", P) == 100
    assert r.validate_terms(40000, 40000, 40000, "AT_DEADLINE", P) == 40000
    for bad_min in (99, 0, -1, 40001):
        with pytest.raises(r.CampaignRuleError) as e:
            r.validate_terms(40000, bad_min, None, "EARLY_ON_GOAL", P)
        assert e.value.code == "BAD_MIN_PLEDGE"
    for share in (499, 40001):
        with pytest.raises(r.CampaignRuleError) as e:
            r.validate_terms(40000, None, share, "EARLY_ON_GOAL", P)
        assert e.value.code == "BAD_SHARE"
    with pytest.raises(r.CampaignRuleError) as e:
        r.validate_terms(40000, None, None, "WHENEVER", P)
    assert e.value.code == "BAD_CLOSE_POLICY"


def test_a_tiny_goal_still_has_a_workable_minimum():
    with pytest.raises(r.CampaignRuleError):
        r.validate_terms(300, None, None, "EARLY_ON_GOAL", P)                                  # default 500 > goal 300: lead must lower it
    assert r.validate_terms(300, 150, None, "EARLY_ON_GOAL", P) == 150
