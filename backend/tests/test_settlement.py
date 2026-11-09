import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.schemas.plans import MoneyPlanSpec, PlanStep
from app.services.settlement import (
    SettlementError,
    idempotency_key,
    plan_captures,
    plan_freelancer_payout,
    plan_hash,
    plan_refunds,
    split_pro_rata,
)


def test_worked_example_1_race_overpledge():
    caps = plan_captures(40000, [(1, 15000), (2, 15000), (3, 10000), (4, 2000)])
    assert caps == {1: 14286, 2: 14285, 3: 9524, 4: 1905}
    assert sum(caps.values()) == 40000


def test_worked_example_3_demo_success():
    caps = plan_captures(40000, [(1, 15000), (2, 15000), (3, 10000)])
    assert caps == {1: 15000, 2: 15000, 3: 10000}


def test_sum_equals_goal_exactly():
    assert plan_captures(40000, [(1, 40000)]) == {1: 40000}  # single pledger
    assert plan_captures(100, [(1, 50), (2, 50)]) == {1: 50, 2: 50}  # holds == goal


def test_below_goal_is_an_error():
    with pytest.raises(SettlementError):
        plan_captures(40000, [(1, 15000), (2, 10000), (3, 5000)])  # worked example 2


def test_remainder_tiebreak_is_deterministic():
    # 10 split three equal ways: 4/3/3, the extra cent goes to the smallest key
    assert split_pro_rata(10, [(3, 1), (1, 1), (2, 1)]) == {1: 4, 2: 3, 3: 3}


def test_zero_weights_and_bad_input():
    assert split_pro_rata(100, [(1, 0), (2, 0)]) == {1: 0, 2: 0}
    with pytest.raises(SettlementError):
        split_pro_rata(-1, [(1, 1)])
    with pytest.raises(SettlementError):
        split_pro_rata(10, [])


def test_plan_refunds_only_positive_remaining():
    assert plan_refunds([(1, 1000, 0), (2, 500, 500), (3, 700, 200)]) == {1: 1000, 3: 500}


def test_freelancer_payout():
    assert plan_freelancer_payout(40000, 40000, 0) == 40000
    with pytest.raises(SettlementError):
        plan_freelancer_payout(40000, 39999, 0)
    with pytest.raises(SettlementError):
        plan_freelancer_payout(40000, 40000, 1)


@given(
    holds=st.lists(st.integers(min_value=1, max_value=10_000_000), min_size=1, max_size=40),
    data=st.data(),
)
def test_property_captures_sum_to_goal_and_never_exceed_hold(holds, data):
    pledges = list(enumerate(holds, start=1))
    goal = data.draw(st.integers(min_value=0, max_value=sum(holds)))
    caps = plan_captures(goal, pledges)
    assert sum(caps.values()) == goal
    assert all(0 <= caps[i] <= a for i, a in pledges)
    assert caps == plan_captures(goal, pledges)  # deterministic


@given(
    total=st.integers(min_value=0, max_value=10**9),
    weights=st.lists(st.integers(min_value=0, max_value=10**7), min_size=1, max_size=30),
)
def test_property_split_is_exact(total, weights):
    out = split_pro_rata(total, list(enumerate(weights, start=1)))
    assert sum(out.values()) == (total if sum(weights) else 0)


def _spec(**over) -> MoneyPlanSpec:
    step = PlanStep(seq=1, phase=1, op="PAYOUT_ITEM", target_type="CONTRACT", target_id=7,
                    amount_cents=40000, bucket="POOL", receiver_email="arjun@example.com",
                    idempotency_key="")
    base = dict(kind="FREELANCER_PAYOUT", project_id=1, contract_id=7, reason="VERIFIED",
                inputs={"report_sha256": "ab"}, steps=[step])
    base.update(over)
    return MoneyPlanSpec(**base)


def test_plan_hash_is_stable_and_ignores_idempotency_keys():
    a = _spec()
    b = _spec()
    b.steps[0].idempotency_key = idempotency_key(plan_hash(b), 1)
    assert plan_hash(a) == plan_hash(b)
    assert len(plan_hash(a)) == 64


def test_plan_hash_changes_when_anything_is_tampered():
    base = plan_hash(_spec())
    swapped = _spec()
    swapped.steps[0].receiver_email = "attacker@example.com"
    inflated = _spec()
    inflated.steps[0].amount_cents = 40001
    assert plan_hash(swapped) != base
    assert plan_hash(inflated) != base
    assert plan_hash(_spec(inputs={"report_sha256": "cd"})) != base


def test_idempotency_key_format():
    assert idempotency_key("a" * 64, 3) == "aaaaaaaaaaaaaaaa-3"
