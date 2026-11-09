from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services import strategist_math as m
from app.services.campaign_rules import CampaignParams

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
PARAMS = CampaignParams(72, 2, 500, 0)
GOAL = 40000
# The demo: Lakshmi (seen the link) said $150, Ravi $150 and Meena $100 (neither has opened it yet)
TEAM = [m.Invitee(1, "Lakshmi", "VIEWED", 15000, False), m.Invitee(2, "Ravi", "INVITED", 15000, False), m.Invitee(3, "Meena", "INVITED", 10000, False)]


def fc(pledged=0, hours=48, invitees=TEAM, supporters=(), goal=GOAL, now=NOW):
    return m.forecast(goal_cents=goal, pledged_cents=pledged, now=now, deadline_at=now + timedelta(hours=hours), invitees=list(invitees),
                      supporter_pledges=list(supporters))


# ---------------- the forecast ----------------

def test_the_demo_opening_position_is_worked_out_by_hand():
    f = fc()
    # expected from invitees: .55*15000 + .30*15000 + .30*10000 = 8250 + 4500 + 3000 = 15750
    assert f["expected_invitees_cents"] == 15750 and f["expected_open_cents"] == 0 and f["projected_cents"] == 15750
    assert f["ratio"] == 0.3937 and f["probability"] == 0.0256            # 1 / (1 + e^(-6 * (0.39375 - 1)))
    assert f["gap_cents"] == 40000 and f["hours_left"] == 48.0 and f["label"] == "estimate (heuristic)"


def test_a_funded_campaign_is_certain_whatever_the_clock_says():
    assert fc(pledged=GOAL)["probability"] == 1.0
    assert fc(pledged=GOAL + 5000, hours=0)["probability"] == 1.0
    assert fc(pledged=GOAL, hours=-5)["probability"] == 1.0
    assert fc(pledged=GOAL)["gap_cents"] == 0


def test_no_time_left_and_short_of_the_goal_is_impossible():
    for hours in (0, -1, -100):
        f = fc(pledged=GOAL - 1, hours=hours)
        assert f["probability"] == 0.0 and f["hours_left"] == 0.0 and f["gap_cents"] == 1


def test_projecting_exactly_the_goal_is_a_coin_flip():
    f = fc(pledged=GOAL - 15750)
    assert f["ratio"] == 1.0 and f["probability"] == 0.5


def test_the_probability_is_clamped_to_two_and_ninety_eight_percent():
    assert fc(pledged=0, invitees=[])["probability"] == 0.02                       # ratio 0 => 0.25% before clamping
    huge = [m.Invitee(1, "Rich", "VIEWED", 10_000_000, False)]
    assert fc(pledged=1, invitees=huge)["probability"] == 0.98


@given(a=st.integers(0, GOAL - 2), b=st.integers(0, GOAL - 2))
def test_property_more_pledged_never_lowers_the_probability(a, b):
    lo, hi = sorted((a, b))
    assert fc(pledged=lo)["probability"] <= fc(pledged=hi)["probability"]


@given(h1=st.floats(0.5, 70), h2=st.floats(0.5, 70))
def test_property_more_time_never_lowers_the_probability_when_pledges_are_arriving(h1, h2):
    supporters = [m.SupporterPledge(3000, NOW - timedelta(hours=1))]
    lo, hi = sorted((h1, h2))
    assert fc(pledged=10000, hours=lo, supporters=supporters)["probability"] <= fc(pledged=10000, hours=hi, supporters=supporters)["probability"]


# ---------------- the invitees ----------------

def test_declined_invitees_contribute_nothing_and_unknown_statuses_count_as_invited():
    declined = [m.Invitee(1, "A", "DECLINED", 20000, False)]
    assert fc(invitees=declined)["expected_invitees_cents"] == 0
    odd = [m.Invitee(1, "A", "WEIRD", 10000, False)]
    assert fc(invitees=odd)["expected_invitees_cents"] == 3000


def test_invitees_who_already_pledged_are_not_counted_twice():
    team = [m.Invitee(1, "Lakshmi", "VIEWED", 15000, True), *TEAM[1:]]
    f = fc(pledged=15000, invitees=team)
    assert f["expected_invitees_cents"] == 7500 and f["projected_cents"] == 22500


def test_an_invitee_who_gave_no_amount_adds_nothing():
    assert fc(invitees=[m.Invitee(1, "A", "VIEWED", None, False)])["expected_invitees_cents"] == 0


def test_conversion_constants_are_the_specs():
    assert m.CONVERSION == {"DECLINED": 0.0, "VIEWED": 0.55, "INVITED": 0.30}
    assert (m.RECENT_WINDOW_HOURS, m.OPEN_DISCOUNT, m.LOGISTIC_STEEPNESS, m.P_MIN, m.P_MAX) == (6, 0.5, 6, 0.02, 0.98)


# ---------------- the supporters' momentum ----------------

def test_recent_supporter_pledges_project_forward_at_half_strength():
    s = [m.SupporterPledge(6000, NOW - timedelta(hours=2))]          # 6000 cents in the last 6 h = 1000 cents/hour
    f = fc(hours=20, invitees=[], supporters=s)
    assert f["expected_open_cents"] == 10000                          # 1000 * 20 h * 0.5


def test_only_pledges_inside_the_last_six_hours_count_and_the_edge_is_exclusive():
    inside = m.SupporterPledge(6000, NOW - timedelta(hours=6) + timedelta(seconds=1))
    edge = m.SupporterPledge(6000, NOW - timedelta(hours=6))
    old = m.SupporterPledge(6000, NOW - timedelta(hours=30))
    assert fc(hours=20, invitees=[], supporters=[inside])["expected_open_cents"] == 10000
    assert fc(hours=20, invitees=[], supporters=[edge, old])["expected_open_cents"] == 0


def test_no_momentum_when_no_time_remains():
    s = [m.SupporterPledge(6000, NOW - timedelta(hours=1))]
    assert fc(hours=0, invitees=[], supporters=s)["expected_open_cents"] == 0


def test_naive_datetimes_are_read_as_utc():
    f = m.forecast(goal_cents=GOAL, pledged_cents=0, now=NOW.replace(tzinfo=None), deadline_at=(NOW + timedelta(hours=10)).replace(tzinfo=None),
                   invitees=[], supporter_pledges=[m.SupporterPledge(600, (NOW - timedelta(hours=1)).replace(tzinfo=None))])
    assert f["hours_left"] == 10.0 and f["expected_open_cents"] == 500


# ---------------- deadline advice at setup ----------------

def test_a_weak_start_gets_the_longest_allowed_campaign():
    s = m.suggest_deadline_for_setup(goal_cents=GOAL, now=NOW, invitees=TEAM, params=PARAMS)
    assert datetime.fromisoformat(s["deadline_at"]) == NOW + timedelta(hours=70) and s["hours"] == 70.0
    assert s["initial_probability"] == 0.0256 and "3-day guarantee" in s["reason"]


def test_a_strong_start_gets_the_default_forty_eight_hours():
    strong = [m.Invitee(i, f"S{i}", "VIEWED", 30000, False) for i in range(1, 4)]            # expects 49500 > goal
    s = m.suggest_deadline_for_setup(goal_cents=GOAL, now=NOW, invitees=strong, params=PARAMS)
    assert datetime.fromisoformat(s["deadline_at"]) == NOW + timedelta(hours=48) and s["hours"] == 48 and s["initial_probability"] >= 0.5


def test_the_longest_campaign_follows_the_honor_limit_setting():
    s = m.suggest_deadline_for_setup(goal_cents=GOAL, now=NOW, invitees=[], params=CampaignParams(48, 4, 500, 0))
    assert datetime.fromisoformat(s["deadline_at"]) == NOW + timedelta(hours=44)


# ---------------- extension while open ----------------

OPENS = NOW - timedelta(hours=30)
DEADLINE = OPENS + timedelta(hours=40)                       # 10 h from NOW


def ext(p=0.3, hours_left=10, deadline=DEADLINE, used=False):
    return m.suggest_extension(probability=p, hours_left=hours_left, deadline_at=deadline, opens_at=OPENS, extension_used=used, params=PARAMS)


def test_a_failing_campaign_with_little_time_may_extend_once_to_the_limit():
    s = ext()
    assert datetime.fromisoformat(s["deadline_at"]) == OPENS + timedelta(hours=70) and "at risk" in s["reason"]


@pytest.mark.parametrize("kw", [dict(p=0.6), dict(p=0.95), dict(hours_left=24), dict(hours_left=48), dict(used=True),
                                dict(deadline=OPENS + timedelta(hours=70)), dict(deadline=OPENS + timedelta(hours=71))])
def test_no_extension_unless_every_condition_holds(kw):
    assert ext(**kw) is None


def test_an_extension_never_shortens_or_passes_the_limit():
    s = ext()
    assert datetime.fromisoformat(s["deadline_at"]) > DEADLINE
    assert datetime.fromisoformat(s["deadline_at"]) <= OPENS + timedelta(hours=PARAMS.pledge_max_hours - PARAMS.honor_safety_margin_hours)


# ---------------- who to nudge ----------------

def test_nudge_targets_are_ranked_by_likelihood_times_amount_with_a_reason():
    t = m.nudge_targets(TEAM)
    assert [(x["name"], x["score"]) for x in t] == [("Lakshmi", 8250), ("Ravi", 4500), ("Meena", 3000)]
    assert t[0]["reason"] == "has seen the campaign but not pledged, said $150"
    assert t[1]["reason"] == "hasn't opened the link, said $150"


def test_pledged_and_declined_people_are_never_nudged():
    team = [m.Invitee(1, "Done", "VIEWED", 9000, True), m.Invitee(2, "No", "DECLINED", 9000, False), m.Invitee(3, "Maybe", "INVITED", 9000, False)]
    assert [x["name"] for x in m.nudge_targets(team)] == ["Maybe"]


def test_ties_go_to_the_lower_member_id_and_amounts_without_cents_or_with_them_read_naturally():
    team = [m.Invitee(9, "B", "INVITED", 10000, False), m.Invitee(4, "A", "INVITED", 10000, False), m.Invitee(5, "C", "INVITED", 12550, False),
            m.Invitee(6, "D", "INVITED", None, False)]
    t = m.nudge_targets(team)
    assert [x["name"] for x in t] == ["C", "A", "B", "D"]
    assert t[0]["reason"] == "hasn't opened the link, said $125.50" and t[3]["reason"] == "hasn't opened the link" and t[3]["score"] == 0
