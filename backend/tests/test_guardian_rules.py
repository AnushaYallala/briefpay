from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import LedgerEntry, MoneyPlan, MoneyPlanStep, PayoutBatch, Pledge
from app.schemas.plans import MoneyPlanSpec
from app.services import guardian_rules as g
from app.services import ledger
from app.services import plan_builder as pb
from app.services.guardian_tamper import ATTACKER, MUTATIONS, TamperError, apply_mutation
from tests.factories import GOAL, NOW, World


class FakeReader:
    """Stands in for PayPal's own records. Mirrors our DB unless told otherwise."""

    def __init__(self, db, balance=10**9, down=False, overrides=None):
        self.db, self.balance, self.down, self.overrides = db, balance, down, overrides or {}

    def _guard(self):
        if self.down:
            raise g.PayPalUnavailable("connection refused")

    def get_authorization(self, authorization_id):
        self._guard()
        if authorization_id in self.overrides:
            return self.overrides[authorization_id]
        p = self.db.scalars(select(Pledge).where(Pledge.paypal_authorization_id == authorization_id)).first()
        if p is None:
            return None
        return g.PayPalObject("CREATED" if p.status == "AUTHORIZED" else "CAPTURED", p.amount_cents)

    def get_capture(self, capture_id):
        self._guard()
        if capture_id in self.overrides:
            return self.overrides[capture_id]
        p = self.db.scalars(select(Pledge).where(Pledge.paypal_capture_id == capture_id)).first()
        return g.PayPalObject("COMPLETED", p.captured_cents) if p else None

    def platform_balance_cents(self):
        self._guard()
        return self.balance


@pytest.fixture()
def w(db):
    return World(db)


def lead(w):
    return f"user:{w.project.lead_user_id}"


def review(w, built, by="system", spec=None, now=NOW, reader=None, params=None):
    plan = pb.save_proposed(w.db, built, proposed_by=by)
    ev = g.evaluate(w.db, plan, spec, now=now, reader=reader or FakeReader(w.db), params=params)
    return plan, ev


def capture_case(w, holds=(15000, 15000, 10000), by="system", **kw):
    for h in holds:
        w.pledge(h)
    return review(w, pb.build_capture_pledges(w.db, w.campaign.id, NOW), by=by, **kw)


def release_case(w, reason="LEAD_CANCEL", holds=(15000, 10000, 5000), **kw):
    for h in holds:
        w.pledge(h)
    return review(w, pb.build_release_holds(w.db, w.campaign.id, reason), by=lead(w), **kw)


def payout_case(w, **kw):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    w.capture_all()
    w.verified_report()
    w.project.state = "PAYOUT_READY"
    w.db.flush()
    return review(w, pb.build_freelancer_payout(w.db, w.project.id), by=lead(w), **kw)


def refund_case(w, by=None, **kw):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    w.capture_all()
    w.project.state = "IN_PROGRESS"
    w.db.flush()
    return review(w, pb.build_refund_captured(w.db, w.project.id, "CANCEL_BEFORE_WORK"), by=by or lead(w), **kw)


def status(ev, rid):
    return ev.get(rid).status


# ---------------- clean plans: every applicable rule passes ----------------

def test_clean_capture_plan_passes_all_ten_rules_and_is_allowed(w):
    _, ev = capture_case(w)
    assert [r.id for r in ev.results] == [f"G-{i:02d}" for i in range(1, 11)]
    assert {r.status for r in ev.results} == {g.PASS}, [(r.id, r.detail) for r in ev.results if r.status != g.PASS]
    assert ev.soft_flags == [] and ev.decision == "ALLOW"
    assert ev.get("G-06").paypal_verified and ev.get("G-08").paypal_verified


def test_clean_release_payout_and_refund_plans_are_allowed(w):
    _, ev = release_case(w)
    assert [r.id for r in ev.results] == [f"G-{i:02d}" for i in range(1, 9)] + ["G-11"]
    assert ev.decision == "ALLOW", [(r.id, r.detail) for r in ev.results if r.status != g.PASS]
    w2 = World(w.db, tag="P")
    _, ev = payout_case(w2)
    assert [r.id for r in ev.results][-1] == "G-12" and ev.decision == "ALLOW", \
        [(r.id, r.detail) for r in ev.results if r.status != g.PASS]
    w3 = World(w.db, tag="R")
    _, ev = refund_case(w3)
    assert [r.id for r in ev.results][-1] == "G-13" and ev.decision == "ALLOW", \
        [(r.id, r.detail) for r in ev.results if r.status != g.PASS]


def test_applicability_table_matches_the_spec():
    assert len(g.APPLICABLE["CAPTURE_PLEDGES"]) == 10 and len(g.APPLICABLE["RELEASE_HOLDS"]) == 9
    assert g.APPLICABLE["FREELANCER_PAYOUT"][-1] == "G-12" and g.APPLICABLE["REFUND_CAPTURED"][-1] == "G-13"
    assert g.APPLICABLE["REAUTH_PLEDGES"] == [f"G-{i:02d}" for i in range(1, 7)]
    assert set(g.RULES) == set(g.TITLES) == {f"G-{i:02d}" for i in range(1, 14)}


# ---------------- G-01 plan binding ----------------

def test_g01_fails_when_the_database_changed_after_the_preview(w):
    plan, _ = capture_case(w)
    w.db.scalars(select(Pledge)).first().status = "VOIDED"  # buyer voided their hold
    w.db.flush()
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db))
    assert status(ev, "G-01") == g.FAIL and ev.decision == "BLOCK"


def test_g01_fails_when_a_hold_lapses_between_preview_and_run(w):
    plan, _ = capture_case(w)
    ev = g.evaluate(w.db, plan, now=NOW + timedelta(hours=61), reader=FakeReader(w.db))
    assert status(ev, "G-01") == g.FAIL


def test_g01_fails_when_reviewed_steps_do_not_hash_to_the_stored_hash(w):
    plan, _ = capture_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps[0].amount_cents -= 1
    ev = g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db))
    assert status(ev, "G-01") == g.FAIL


# ---------------- G-02 phase and exclusivity ----------------

def test_g02_other_plan_executing_blocks(w):
    plan, _ = capture_case(w)
    w.db.add(MoneyPlan(project_id=w.project.id, kind="RELEASE_HOLDS", plan_json={}, plan_hash="x" * 64,
                       state="EXECUTING", proposed_by="system", release_policy="AUTO_ON_ALLOW"))
    w.db.flush()
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-02") == g.FAIL


def test_g02_same_kind_already_done_blocks(w):
    plan, _ = capture_case(w)
    w.db.add(MoneyPlan(project_id=w.project.id, campaign_id=w.campaign.id, kind="CAPTURE_PLEDGES", plan_json={},
                       plan_hash="y" * 64, state="DONE", proposed_by="system", release_policy="AUTO_ON_ALLOW"))
    w.db.flush()
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-02") == g.FAIL


@pytest.mark.parametrize("campaign_state", ["SETUP", "CAPTURING", "FAILED"])
def test_g02_wrong_campaign_state_blocks_a_capture(w, campaign_state):
    plan, _ = capture_case(w)
    w.campaign.state = campaign_state
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-02") == g.FAIL


def test_g02_a_pledge_cannot_be_both_captured_and_voided(w):
    plan, _ = capture_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps.append(spec.steps[0].model_copy(update={"op": "VOID_AUTH", "bucket": "NONE", "seq": 4}))
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-02") == g.FAIL


# ---------------- G-03 isolation ----------------

def test_g03_another_projects_pledge_is_rejected(w):
    plan, _ = capture_case(w)
    other = World(w.db, tag="B")
    foreign = other.pledge(15000)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps[0].target_id = foreign.id
    ev = g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db))
    assert status(ev, "G-03") == g.FAIL and status(ev, "G-08") == g.FAIL and ev.decision == "BLOCK"


def test_g03_payout_to_an_unrecorded_email_is_rejected(w):
    plan, _ = payout_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps[0].receiver_email = ATTACKER
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-03") == g.FAIL


def test_g03_refund_naming_a_receiver_is_rejected(w):
    plan, _ = refund_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps[0].receiver_email = ATTACKER
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-03") == g.FAIL


# ---------------- G-04 step integrity ----------------

def test_g04_extra_step_is_rejected(w):
    plan, _ = capture_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps.append(spec.steps[0].model_copy(update={"seq": 4}))
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-04") == g.FAIL


def test_g04_key_not_derived_from_hash_is_rejected(w):
    plan, _ = capture_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps[0].idempotency_key = "reused-from-an-old-plan-1"
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-04") == g.FAIL


def test_g04_key_used_by_another_plan_is_rejected(w):
    plan, _ = capture_case(w)
    key = w.db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == plan.id)).first().idempotency_key
    other = MoneyPlan(project_id=w.project.id, kind="RELEASE_HOLDS", plan_json={}, plan_hash="z" * 64,
                      state="DONE", proposed_by="system", release_policy="AUTO_ON_ALLOW")
    w.db.add(other)
    w.db.flush()
    w.db.query(MoneyPlanStep).filter(MoneyPlanStep.plan_id == plan.id, MoneyPlanStep.idempotency_key == key).update(
        {"plan_id": other.id})
    w.db.flush()
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-04") == g.FAIL


# ---------------- G-05 bounds and currency ----------------

def test_g05_capture_above_its_authorization_fails(w):
    plan, _ = capture_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps[0].amount_cents += 1
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-05") == g.FAIL


def test_g05_negative_amount_fails(w):
    plan, _ = capture_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps[0].amount_cents = -5
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-05") == g.FAIL


def test_g05_payout_over_the_max_fails(w):
    plan, _ = payout_case(w)
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db), params=g.GuardianParams(payout_max_cents=39999))
    assert status(ev, "G-05") == g.FAIL


def test_g05_payout_rate_limit_fails(w):
    plan, _ = payout_case(w)
    w.db.add(PayoutBatch(plan_id=plan.id, sender_batch_id="earlier", status="SUCCESS", created_at=NOW))
    w.db.flush()
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db), params=g.GuardianParams(payout_max_per_hour=1))
    assert status(ev, "G-05") == g.FAIL


def test_g05_mixed_currencies_fail(w):
    plan, _ = capture_case(w)
    w.campaign.currency = "EUR"
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-05") == g.FAIL


# ---------------- G-06 PayPal-side proof ----------------

def test_g06_paypal_disagreeing_with_us_fails(w):
    plan, _ = capture_case(w)
    auth = w.db.scalars(select(Pledge)).first().paypal_authorization_id
    reader = FakeReader(w.db, overrides={auth: g.PayPalObject("VOIDED", 15000)})
    ev = g.evaluate(w.db, plan, now=NOW, reader=reader)
    assert status(ev, "G-06") == g.FAIL and status(ev, "G-09") == g.FAIL and ev.decision == "BLOCK"


def test_g06_amount_mismatch_and_unknown_authorization_fail(w):
    plan, _ = capture_case(w)
    auth = w.db.scalars(select(Pledge)).first().paypal_authorization_id
    for override in (g.PayPalObject("CREATED", 14999), None):
        ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db, overrides={auth: override}))
        assert status(ev, "G-06") == g.FAIL


def test_g06_refund_checks_the_capture_record(w):
    plan, _ = refund_case(w)
    cap = w.db.scalars(select(Pledge)).first().paypal_capture_id
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db, overrides={cap: g.PayPalObject("REFUNDED", 15000)}))
    assert status(ev, "G-06") == g.FAIL


def test_g06_paypal_down_is_unverified_and_forces_a_hold_not_a_block(w):
    plan, _ = capture_case(w)
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db, down=True))
    assert status(ev, "G-06") == g.UNVERIFIED and status(ev, "G-08") == g.SKIPPED
    assert [f["id"] for f in ev.soft_flags] == ["S-03"] and ev.decision == "HOLD"


def test_g06_payout_references_no_paypal_objects(w):
    _, ev = payout_case(w)
    assert ev.get("G-06").status == g.PASS and not ev.get("G-06").paypal_verified


# ---------------- G-07 conservation and buckets ----------------

def test_g07_wrong_bucket_fails(w):
    plan, _ = capture_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps[0].bucket = "NONE"
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-07") == g.FAIL


def test_g07_outflow_beyond_the_pool_fails(w):
    plan, _ = payout_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps[0].amount_cents = GOAL + 1
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-07") == g.FAIL


def test_g07_release_plan_touching_pool_fails(w):
    plan, _ = release_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps[0].bucket = "POOL"
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-07") == g.FAIL


# ---------------- G-08 solvency ----------------

def test_g08_pool_larger_than_paypal_balance_fails(w):
    plan, _ = payout_case(w)
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db, balance=GOAL - 1))
    assert status(ev, "G-08") == g.FAIL


def test_g08_unavailable_balance_is_skipped_never_a_failure(w):
    plan, _ = payout_case(w)
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db, balance=None))
    assert status(ev, "G-08") == g.SKIPPED and ev.decision == "ALLOW"


# ---------------- G-09 success condition ----------------

def test_g09_needs_a_trigger_when_policy_is_at_deadline(w):
    w.campaign.close_policy = "AT_DEADLINE"
    for h in (15000, 15000, 10000):
        w.pledge(h)
    built = pb.build_capture_pledges(w.db, w.campaign.id, NOW)
    plan, ev = review(w, built, by="system")
    assert status(ev, "G-09") == g.FAIL
    assert status(g.evaluate(w.db, plan, now=NOW + timedelta(hours=41), reader=FakeReader(w.db)), "G-09") == g.PASS  # deadline passed
    plan2 = MoneyPlan(**{c.name: getattr(plan, c.name) for c in MoneyPlan.__table__.c if c.name not in ("id",)})
    plan2.proposed_by = lead(w)  # a lead click is also a valid trigger
    plan2.plan_hash = "q" * 64
    assert status(g.evaluate(w.db, plan2, MoneyPlanSpec.model_validate(plan.plan_json), now=NOW,
                             reader=FakeReader(w.db)), "G-09") == g.PASS


def test_g09_unlocked_brd_or_unsigned_contract_fails(w):
    plan, _ = capture_case(w)
    from app.models import BRD
    w.db.get(BRD, w.contract.brd_id).locked_at = None
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-09") == g.FAIL
    w.db.get(BRD, w.contract.brd_id).locked_at = NOW
    w.contract.signed_at = None
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-09") == g.FAIL


def test_g09_goal_not_reached_by_live_holds_fails(w):
    plan, _ = capture_case(w)
    w.db.scalars(select(Pledge)).first().honor_until = NOW - timedelta(hours=1)
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-09") == g.FAIL


# ---------------- G-10 capture math ----------------

def test_g10_split_that_is_not_the_pro_rata_recomputation_fails(w):
    plan, _ = capture_case(w, holds=(15000, 15000, 10000, 2000))
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    assert [s.amount_cents for s in spec.steps] == [14286, 14285, 9524, 1905]
    spec.steps[0].amount_cents, spec.steps[1].amount_cents = 14285, 14286  # same total, wrong split
    ev = g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db))
    assert status(ev, "G-10") == g.FAIL
    assert sum(s.amount_cents for s in spec.steps) == GOAL


def test_g10_total_not_equal_to_goal_fails(w):
    plan, _ = capture_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps.pop()
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-10") == g.FAIL


# ---------------- G-11 failure condition ----------------

def test_g11_deadline_missed_requires_the_deadline_to_have_passed(w):
    _, ev = release_case(w, reason="DEADLINE_MISSED")
    assert status(ev, "G-11") == g.FAIL and "deadline has not passed" in ev.get("G-11").detail
    plan = w.db.scalars(select(MoneyPlan)).first()
    ev = g.evaluate(w.db, plan, now=NOW + timedelta(hours=41), reader=FakeReader(w.db))
    assert status(ev, "G-11") == g.PASS


def test_g11_cannot_call_a_funded_campaign_failed(w):
    w.pledge(15000), w.pledge(15000), w.pledge(10000)
    plan, ev = review(w, pb.build_release_holds(w.db, w.campaign.id, "DEADLINE_MISSED"), by="system",
                      now=NOW + timedelta(hours=41))
    assert status(ev, "G-11") == g.FAIL and "reach the goal" in ev.get("G-11").detail


def test_g11_lead_cancel_is_always_allowed_and_releases_a_funded_campaign(w):
    w.pledge(15000), w.pledge(15000), w.pledge(10000)
    _, ev = review(w, pb.build_release_holds(w.db, w.campaign.id, "LEAD_CANCEL"), by=lead(w))
    assert status(ev, "G-11") == g.PASS


def test_g11_a_hold_voided_after_preview_fails(w):
    plan, _ = release_case(w)
    w.db.scalars(select(Pledge)).first().status = "VOIDED"
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db))
    assert status(ev, "G-11") == g.FAIL


# ---------------- G-12 work and recipient binding ----------------

def test_g12_report_not_verified_or_tampered_fails(w):
    plan, _ = payout_case(w)
    from app.models import VerificationReport
    rep = w.db.scalars(select(VerificationReport)).first()
    rep.sha256 = "f" * 64
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-12") == g.FAIL
    rep.sha256, rep.overall = "d" * 64, "NEEDS_CHANGES"
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-12") == g.FAIL


def test_g12_brd_hash_mismatch_fails(w):
    plan, _ = payout_case(w)
    w.contract.brd_sha256 = "0" * 64
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-12") == g.FAIL


def test_g12_wrong_project_state_fails(w):
    plan, _ = payout_case(w)
    w.project.state = "VERIFYING"
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-12") == g.FAIL


def test_g12_existing_pending_payout_for_the_contract_fails(w):
    plan, _ = payout_case(w)
    earlier = MoneyPlan(project_id=w.project.id, contract_id=w.contract.id, kind="FREELANCER_PAYOUT", plan_json={},
                        plan_hash="e" * 64, state="EXECUTING", proposed_by=lead(w), release_policy="HUMAN")
    w.db.add(earlier)
    w.db.flush()
    w.db.add(PayoutBatch(plan_id=earlier.id, sender_batch_id="b1", status="PENDING"))
    w.db.flush()
    assert status(g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)), "G-12") == g.FAIL


# ---------------- G-13 refund correctness ----------------

def test_g13_must_be_requested_by_the_lead(w):
    _, ev = refund_case(w, by="system")
    assert status(ev, "G-13") == g.FAIL
    w2 = World(w.db, tag="X")
    _, ev = refund_case(w2, by="user:99999")
    assert status(ev, "G-13") == g.FAIL


def test_g13_fails_once_a_payout_has_happened(w):
    plan, _ = refund_case(w)
    ledger.append(w.db, w.project.id, "PAYOUT_SENT", -1, actor="paypal")
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db))
    assert status(ev, "G-13") == g.FAIL


def test_g13_refund_that_does_not_equal_the_pool_fails(w):
    plan, _ = refund_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps.pop()
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-13") == g.FAIL


def test_g13_bad_reason_fails(w):
    plan, _ = refund_case(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json).model_copy(update={"reason": "BECAUSE"})
    assert status(g.evaluate(w.db, plan, spec, now=NOW, reader=FakeReader(w.db)), "G-13") == g.FAIL


# ---------------- soft flags ----------------

def test_s01_freelancer_funding_their_own_job_forces_a_hold(w):
    plan, ev = capture_case(w)
    assert ev.soft_flags == []
    w.db.scalars(select(Pledge)).first().payer_email = "Arjun@Sandbox.com"  # case-insensitive match
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db))
    assert [f["id"] for f in ev.soft_flags] == ["S-01"]
    assert not ev.failed_ids and ev.decision == "HOLD"


def test_s02_one_payer_holding_sixty_percent_forces_a_hold(w):
    plan, _ = capture_case(w)
    for p, mail in zip(w.db.scalars(select(Pledge).order_by(Pledge.id)), ("a@x.com", "a@x.com", "b@x.com")):
        p.payer_email = mail  # a@x.com = 30000 of 40000 = 75%
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db))
    assert [f["id"] for f in ev.soft_flags] == ["S-02"] and ev.decision == "HOLD"


def test_s02_even_split_does_not_flag(w):
    plan, _ = capture_case(w)
    for p, mail in zip(w.db.scalars(select(Pledge).order_by(Pledge.id)), ("a@x.com", "b@x.com", "c@x.com")):
        p.payer_email = mail
    assert g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db)).soft_flags == []


def test_s02_last_minute_surge_forces_a_hold(w):
    plan, _ = capture_case(w)
    pledges = list(w.db.scalars(select(Pledge).order_by(Pledge.id)))
    for p, mail in zip(pledges, ("a@x.com", "b@x.com", "c@x.com")):
        p.payer_email = mail
    for p in pledges[:2]:  # 30000 of 40000 landed in the final 10 minutes
        p.authorized_at = w.campaign.deadline_at - timedelta(minutes=5)
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db))
    assert [f["id"] for f in ev.soft_flags] == ["S-02"] and "10 minutes" in ev.soft_flags[0]["detail"]


# ---------------- tamper simulation: every mutation must BLOCK ----------------

def case_for(w, mutation):
    return {"FREELANCER_PAYOUT": payout_case, "CAPTURE_PLEDGES": capture_case, "RELEASE_HOLDS": release_case}[
        MUTATIONS[mutation][0]](w)


@pytest.mark.parametrize("mutation", list(MUTATIONS))
def test_every_tamper_mutation_is_blocked_by_the_expected_rules(w, mutation):
    plan, clean = case_for(w, mutation)
    assert clean.decision == "ALLOW", "the untampered plan must be clean first"
    tampered = apply_mutation(MoneyPlanSpec.model_validate(plan.plan_json), mutation)
    ev = g.evaluate(w.db, plan, tampered, now=NOW, reader=FakeReader(w.db))
    assert ev.decision == "BLOCK"
    expected = MUTATIONS[mutation][1]
    assert expected <= set(ev.failed_ids), f"expected {expected}, failed {ev.failed_ids}"


def test_swap_recipient_really_changes_who_gets_paid(w):
    plan, _ = payout_case(w)
    t = apply_mutation(MoneyPlanSpec.model_validate(plan.plan_json), "SWAP_RECIPIENT")
    assert t.steps[0].receiver_email == ATTACKER and t.steps[0].amount_cents == GOAL


def test_simulation_never_writes_anything(w):
    plan, _ = payout_case(w)
    before = [w.db.scalar(select(func_count(t))) for t in (MoneyPlan, MoneyPlanStep, LedgerEntry, PayoutBatch)]
    tampered = apply_mutation(MoneyPlanSpec.model_validate(plan.plan_json), "SWAP_RECIPIENT")
    g.evaluate(w.db, plan, tampered, now=NOW, reader=FakeReader(w.db))
    assert [w.db.scalar(select(func_count(t))) for t in (MoneyPlan, MoneyPlanStep, LedgerEntry, PayoutBatch)] == before
    assert w.db.get(MoneyPlan, plan.id).plan_json["steps"][0]["receiver_email"] == "arjun@sandbox.com"


def func_count(model):
    from sqlalchemy import func
    return func.count(model.id)


def test_mutation_on_the_wrong_plan_kind_is_refused(w):
    plan, _ = capture_case(w)
    with pytest.raises(TamperError):
        apply_mutation(MoneyPlanSpec.model_validate(plan.plan_json), "SWAP_RECIPIENT")
    with pytest.raises(TamperError):
        apply_mutation(MoneyPlanSpec.model_validate(plan.plan_json), "NOPE")


# ---------------- safety net ----------------

def test_a_rule_that_crashes_counts_as_a_failure_not_a_pass(w, monkeypatch):
    plan, _ = capture_case(w)

    def boom(c):
        raise RuntimeError("bug")

    monkeypatch.setitem(g.RULES, "G-05", boom)
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db))
    assert status(ev, "G-05") == g.FAIL and "could not be evaluated" in ev.get("G-05").detail
    assert ev.decision == "BLOCK"
