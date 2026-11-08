from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services import pledge_gate as g

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
DEADLINE = NOW + timedelta(hours=40)


def facts(state="OPEN", goal=40000, held=15000, minimum=500, deadline=DEADLINE, currency="USD"):
    return g.CampaignFacts(state, deadline, goal, minimum, held, currency)


def refused(code, status=None, **kw):
    amount = kw.pop("amount", 1000)
    role = kw.pop("role", None)
    now = kw.pop("now", NOW)
    with pytest.raises(g.GateError) as e:
        g.check_new_pledge(facts(**kw), amount_cents=amount, role=role, now=now)
    assert e.value.code == code
    if status:
        assert e.value.status == status


def allowed(amount=1000, role=None, now=NOW, **kw):
    g.check_new_pledge(facts(**kw), amount_cents=amount, role=role, now=now)


# ---------------- starting a pledge ----------------

def test_a_normal_pledge_is_allowed_for_anyone_but_the_freelancer():
    for role in (None, "LEAD", "SPONSOR", "SUPPORTER"):
        allowed(role=role)


def test_the_freelancer_cannot_fund_their_own_job():
    refused("FREELANCER_CANNOT_PLEDGE", 403, role="FREELANCER")
    refused("FREELANCER_CANNOT_PLEDGE", 403, role="FREELANCER", state="SETUP")          # checked first, whatever else is wrong


@pytest.mark.parametrize("state", ["SETUP", "CAPTURING", "CAPTURED", "FAILING", "FAILED", "CANCELLED"])
def test_only_an_open_campaign_takes_pledges(state):
    refused("CAMPAIGN_NOT_OPEN", 409, state=state)


def test_the_deadline_is_exclusive():
    allowed(now=DEADLINE - timedelta(seconds=1))
    refused("DEADLINE_PASSED", 409, now=DEADLINE)
    refused("DEADLINE_PASSED", 409, now=DEADLINE + timedelta(hours=1))


def test_naive_datetimes_are_read_as_utc():
    allowed(deadline=DEADLINE.replace(tzinfo=None), now=NOW.replace(tzinfo=None))
    refused("DEADLINE_PASSED", deadline=DEADLINE.replace(tzinfo=None), now=DEADLINE.replace(tzinfo=None))


@pytest.mark.parametrize("amount", [0, -1, -500, True, False, 1.5, "500", None])
def test_the_amount_must_be_a_positive_whole_number_of_cents(amount):
    refused("BAD_AMOUNT", 422, amount=amount)


def test_the_amount_must_be_between_the_minimum_and_what_is_still_needed():
    allowed(amount=500)                                                          # exactly the minimum
    allowed(amount=25000)                                                        # exactly what is still needed (40000 - 15000)
    refused("BELOW_MINIMUM", 422, amount=499)
    refused("ABOVE_NEED", 422, amount=25001)
    allowed(amount=500, minimum=500, held=39500)                                 # exactly the last 500 needed
    refused("ABOVE_NEED", 422, amount=501, held=39500)


def test_once_the_goal_is_reached_no_more_pledges_are_taken():
    refused("GOAL_REACHED", 409, held=40000)
    refused("GOAL_REACHED", 409, held=45000)                                     # an earlier race over-pledged
    refused("GOAL_REACHED", 409, held=40000, amount=500)


@given(amount=st.integers(min_value=-100, max_value=60000), held=st.integers(min_value=0, max_value=39999),
       minimum=st.integers(min_value=100, max_value=5000))
def test_property_an_amount_passes_exactly_when_it_is_within_the_window(amount, held, minimum):
    remaining = 40000 - held
    ok = minimum <= amount <= remaining
    try:
        allowed(amount=amount, held=held, minimum=minimum)
        assert ok
    except g.GateError:
        assert not ok


# ---------------- authorizing: the race is allowed ----------------

def test_authorizing_needs_the_campaign_to_still_be_open_and_before_the_deadline():
    g.check_authorize_allowed(facts(), now=NOW)
    for state in ("SETUP", "CAPTURING", "CAPTURED", "FAILING", "FAILED", "CANCELLED"):
        with pytest.raises(g.GateError) as e:
            g.check_authorize_allowed(facts(state=state), now=NOW)
        assert e.value.code == "CAMPAIGN_CLOSED" and e.value.status == 409
    with pytest.raises(g.GateError) as e:
        g.check_authorize_allowed(facts(), now=DEADLINE)
    assert e.value.code == "CAMPAIGN_CLOSED" and "no hold was placed" in e.value.message


def test_a_race_that_over_pledges_is_allowed_at_authorization():
    """The capture plan splits pro-rata so the captured total is exactly the goal (SPEC 8.2 rule 5)."""
    g.check_authorize_allowed(facts(held=40000), now=NOW)
    g.check_authorize_allowed(facts(held=52000), now=NOW)


# ---------------- the hold PayPal gave us ----------------

def hold(**over):
    return {"id": "AUTH1", "status": "CREATED", "amount_cents": 15000, "currency": "USD", **over}


def check(auth, amount=15000, currency="USD"):
    g.check_hold(pledge_amount_cents=amount, campaign_currency=currency, auth=auth)


def test_a_matching_created_hold_counts():
    check(hold())


@pytest.mark.parametrize("auth", [None, {}])
def test_no_hold_at_all_is_a_decline(auth):
    with pytest.raises(g.GateError) as e:
        check(auth)
    assert e.value.code == "PLEDGE_DECLINED" and e.value.status == 402


@pytest.mark.parametrize("status", ["DENIED", "PENDING", "VOIDED", "CAPTURED", "PARTIALLY_CAPTURED", "UNKNOWN", "created", None])
def test_only_the_status_created_counts_as_a_hold(status):
    with pytest.raises(g.GateError) as e:
        check(hold(status=status))
    assert e.value.code == "PLEDGE_DECLINED" and e.value.status == 402


@pytest.mark.parametrize("over", [{"amount_cents": 14999}, {"amount_cents": 15001}, {"amount_cents": None}, {"currency": "EUR"}, {"currency": None}])
def test_a_hold_that_differs_from_the_pledge_is_never_counted(over):
    with pytest.raises(g.GateError) as e:
        check(hold(**over))
    assert e.value.code == "HOLD_MISMATCH" and e.value.status == 409


def test_the_campaign_currency_is_what_the_hold_is_compared_to():
    with pytest.raises(g.GateError):
        check(hold(), currency="EUR")


# ---------------- how long a hold lasts ----------------

def test_the_honor_period_is_three_days_and_validity_twenty_nine():
    honor, valid = g.hold_times(NOW)
    assert honor == NOW + timedelta(days=3) and valid == NOW + timedelta(days=29)
    assert (g.HONOR_DAYS, g.VALID_DAYS) == (3, 29)


def test_hold_times_read_naive_datetimes_as_utc():
    honor, valid = g.hold_times(NOW.replace(tzinfo=None))
    assert honor == NOW + timedelta(days=3) and honor.tzinfo is not None


# ---------------- the name on the public board ----------------

@pytest.mark.parametrize("raw,clean", [("Ravi", "Ravi"), ("  Ravi   Kumar  ", "Ravi Kumar"), ("A\tB\nC", "A B C"),
                                       ("లక్ష్మి", "లక్ష్మి"), ("<b>Meena</b>", "<b>Meena</b>"), ("x" * 80, "x" * 80)])
def test_names_are_tidied_but_not_rewritten(raw, clean):
    assert g.clean_display_name(raw) == clean            # HTML is escaped where it is displayed, not mangled here


@pytest.mark.parametrize("raw", [None, "", "   ", "\n\t ", "x" * 81, "bad" + chr(0) + "name", "bell" + chr(7), "del" + chr(127)])
def test_unusable_names_are_refused(raw):
    with pytest.raises(g.GateError) as e:
        g.clean_display_name(raw)
    assert e.value.code == "BAD_NAME" and e.value.status == 422
