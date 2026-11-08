import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import (
    Campaign, GuardianReview, LedgerEntry, MoneyPlan, MoneyPlanStep, PayoutBatch, PayoutItem, PlanApproval, Pledge,
    Project, Refund,
)
from app.schemas.plans import MoneyPlanSpec
from app.services import ledger, plan_builder as pb, plan_lifecycle as lc
from app.services.money_executor import ExecutionRefused, execute
from app.services.settlement import idempotency_key, plan_hash
from tests.factories import GOAL, NOW, FakeReader, FakeWriter, World, rejected, transient


@pytest.fixture()
def w(db):
    return World(db)


def lead(w):
    return f"user:{w.project.lead_user_id}"


def reviewed(w, built, by="system"):
    plan = pb.save_proposed(w.db, built, proposed_by=by)
    review = lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW)
    return plan, review


def approved_capture(w, holds=(15000, 15000, 10000)):
    for h in holds:
        w.pledge(h)
    plan, review = reviewed(w, pb.build_capture_pledges(w.db, w.campaign.id, NOW))
    assert plan.state == "APPROVED" and review.decision == "ALLOW"  # AUTO_ON_ALLOW
    return plan


def approved_release(w, holds=(15000, 10000, 5000), reason="LEAD_CANCEL"):
    for h in holds:
        w.pledge(h)
    plan, _ = reviewed(w, pb.build_release_holds(w.db, w.campaign.id, reason), by=lead(w))
    assert plan.state == "APPROVED"
    return plan


def funded(w):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    w.capture_all()
    w.project.state = "PAYOUT_READY"
    w.verified_report()
    w.db.flush()


def approved_payout(w):
    funded(w)
    plan, review = reviewed(w, pb.build_freelancer_payout(w.db, w.project.id), by=lead(w))
    assert plan.state == "REVIEWED" and plan.release_policy == "HUMAN"  # humans approve payouts
    lc.approve_plan(w.db, plan, approver=lead(w), plan_hash=plan.plan_hash, guardian_review_id=review.id)
    return plan


def steps_of(w, plan):
    return list(w.db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == plan.id).order_by(MoneyPlanStep.seq)))


def ledger_types(w):
    return [e.type for e in w.db.scalars(select(LedgerEntry).order_by(LedgerEntry.seq))]


def confirm_all(w, plan):
    for s in steps_of(w, plan):
        lc.confirm_step(w.db, s, paypal_ref=s.paypal_ref or f"REF-{s.id}", now=NOW)


# ================= capture: the happy path =================

def test_capture_plan_sends_exactly_the_approved_steps_with_their_keys(w):
    plan = approved_capture(w)
    writer = FakeWriter()
    execute(w.db, plan.id, writer, now=NOW)
    assert writer.ops() == ["capture"] * 3
    assert writer.keys() == [s.idempotency_key for s in steps_of(w, plan)]          # PayPal-Request-Id = step key
    assert [c["amount_cents"] for c in writer.calls] == [15000, 15000, 10000]
    assert all(c["final_capture"] is True for c in writer.calls)                     # releases any unused remainder
    assert all(c["currency"] == "USD" for c in writer.calls)
    assert plan.state == "EXECUTING" and w.campaign.state == "CAPTURING"
    assert {s.state for s in steps_of(w, plan)} == {"SENT"}
    assert ledger.pool_balance(w.db, w.project.id) == 0, "sent is not captured: only confirmation moves the ledger"


def test_confirmations_fund_the_pool_and_finish_the_plan(w):
    plan = approved_capture(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    for i, s in enumerate(steps_of(w, plan)):
        lc.confirm_step(w.db, s, paypal_ref=f"CAP-{i}", now=NOW)
        assert plan.state == ("DONE" if i == 2 else "EXECUTING")
    assert ledger.pool_balance(w.db, w.project.id) == GOAL
    assert w.campaign.state == "CAPTURED" and w.project.state == "IN_PROGRESS"
    assert w.contract.effective_at == NOW                                           # contract becomes effective
    assert {p.status for p in w.db.scalars(select(Pledge))} == {"CAPTURED"}
    assert sorted(p.paypal_capture_id for p in w.db.scalars(select(Pledge))) == ["CAP-0", "CAP-1", "CAP-2"]
    assert ledger_types(w).count("PLEDGE_CAPTURED") == 3 and "PLAN_EXECUTED" in ledger_types(w)


def test_overpledge_partial_capture_never_exceeds_a_hold_and_sums_to_goal(w):
    plan = approved_capture(w, holds=(15000, 15000, 10000, 2000))
    writer = FakeWriter()
    execute(w.db, plan.id, writer, now=NOW)
    assert [c["amount_cents"] for c in writer.calls] == [14286, 14285, 9524, 1905] and sum(
        c["amount_cents"] for c in writer.calls) == GOAL


def test_confirming_twice_changes_nothing(w):
    plan = approved_capture(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    [first, *_] = steps_of(w, plan)
    lc.confirm_step(w.db, first, paypal_ref="CAP-A", now=NOW)
    before = (ledger.pool_balance(w.db, w.project.id), w.db.scalar(select(func.count()).select_from(LedgerEntry)))
    lc.confirm_step(w.db, first, paypal_ref="CAP-OTHER", now=NOW)                   # duplicate webhook
    assert (ledger.pool_balance(w.db, w.project.id), w.db.scalar(select(func.count()).select_from(LedgerEntry))) == before
    assert w.db.get(Pledge, first.target_id).paypal_capture_id == "CAP-A"


# ================= refusals: nothing may reach PayPal =================

def refused(w, plan, match):
    writer = FakeWriter()
    with pytest.raises(ExecutionRefused, match=match):
        execute(w.db, plan.id, writer, now=NOW)
    assert writer.calls == [], "a refused plan must send NOTHING to PayPal"


def test_refuses_plans_that_are_not_approved(w):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    plan = pb.save_proposed(w.db, pb.build_capture_pledges(w.db, w.campaign.id, NOW), proposed_by="system")
    refused(w, plan, "PROPOSED")
    lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW)
    plan.state = "REVIEWED"
    refused(w, plan, "REVIEWED")
    for terminal in ("BLOCKED", "DONE", "FAILED"):
        plan.state = terminal
        refused(w, plan, terminal)


def test_refuses_when_data_changed_after_approval(w):
    plan = approved_capture(w)
    w.db.scalars(select(Pledge)).first().status = "VOIDED"                           # a buyer voided their hold
    w.db.flush()
    refused(w, plan, "can no longer be built")
    assert w.campaign.state == "OPEN" and plan.state == "APPROVED"                   # nothing half-started


def test_refuses_when_the_rebuilt_hash_differs(w):
    plan = approved_capture(w)
    w.pledge(5000)                                                                   # extra hold: pro-rata split changes
    refused(w, plan, "plan changed since approval")


def test_refuses_without_an_approval_for_this_hash(w):
    plan = approved_capture(w)
    for a in w.db.scalars(select(PlanApproval)):
        a.plan_hash = "0" * 64
    refused(w, plan, "no approval bound")


def test_refuses_a_simulated_or_foreign_review(w):
    plan = approved_capture(w)
    review = w.db.get(GuardianReview, w.db.scalars(select(PlanApproval)).first().guardian_review_id)
    review.simulated = True
    refused(w, plan, "does not belong")
    review.simulated, review.plan_hash = False, "1" * 64
    refused(w, plan, "does not belong")


def test_refuses_a_blocked_review_and_a_hold_without_acknowledgement(w):
    plan = approved_capture(w)
    review = w.db.get(GuardianReview, w.db.scalars(select(PlanApproval)).first().guardian_review_id)
    review.decision = "BLOCK"
    refused(w, plan, "blocked")
    review.decision = "HOLD"
    refused(w, plan, "acknowledgement")
    w.db.scalars(select(PlanApproval)).first().ack_note = "reviewed, proceed"
    writer = FakeWriter()
    execute(w.db, plan.id, writer, now=NOW)
    assert len(writer.calls) == 3


def test_a_human_plan_cannot_be_approved_by_the_system(w):
    plan = approved_payout(w)
    w.db.scalars(select(PlanApproval)).first().approver = "system:AUTO_ON_ALLOW"
    refused(w, plan, "needs a human")


def test_refuses_a_handcrafted_extra_step(w):
    plan = approved_capture(w)
    w.db.add(MoneyPlanStep(plan_id=plan.id, seq=4, phase=1, op="CAPTURE_AUTH", target_type="PLEDGE",
                           target_id=w.db.scalars(select(Pledge)).first().id, amount_cents=99, bucket="POOL",
                           idempotency_key="handcrafted-1", state="PENDING"))
    w.db.flush()
    refused(w, plan, "differ from the approved plan")


def test_refuses_an_altered_or_missing_step(w):
    plan = approved_capture(w)
    steps = steps_of(w, plan)
    steps[0].amount_cents += 1
    refused(w, plan, "differ from the approved plan")
    steps[0].amount_cents -= 1
    steps[0].receiver_email = "attacker@example.com"
    refused(w, plan, "differ from the approved plan")
    steps[0].receiver_email = None
    w.db.delete(steps[2])
    w.db.flush()
    refused(w, plan, "differ from the approved plan")


def test_refuses_a_plan_json_that_no_longer_matches_its_hash(w):
    plan = approved_payout(w)
    doctored = dict(plan.plan_json)
    doctored["steps"] = [dict(doctored["steps"][0], receiver_email="attacker@example.com")]
    plan.plan_json = doctored
    refused(w, plan, "tampered")


def test_unknown_plan_is_refused(w):
    with pytest.raises(ExecutionRefused):
        execute(w.db, 987654, FakeWriter())


# ================= retries, failures, partial =================

def test_transient_errors_retry_with_the_same_idempotency_key(w):
    plan = approved_capture(w)
    writer = FakeWriter()
    writer.errors["capture"] = [transient(), transient()]
    execute(w.db, plan.id, writer, now=NOW)
    first_three = writer.keys()[:3]
    assert len(set(first_three)) == 1, "all three tries of step 1 must carry one request id"
    assert len(writer.calls) == 5 and steps_of(w, plan)[0].state == "SENT"


def test_transient_errors_stop_after_two_retries_and_fail_the_step(w):
    plan = approved_capture(w)
    writer = FakeWriter()
    writer.errors["capture"] = [transient("t1"), transient("t2"), transient("t3")]
    execute(w.db, plan.id, writer, now=NOW)
    s1 = steps_of(w, plan)[0]
    assert s1.state == "FAILED" and s1.error_json["attempts"] == 3
    assert len(writer.calls) == 3 + 2, "step 1 tried 3 times, steps 2 and 3 once each"


def test_a_rejected_capture_fails_that_step_only_and_the_plan_ends_partial(w):
    plan = approved_capture(w)
    writer = FakeWriter()
    writer.errors["capture"] = [rejected("INSTRUMENT_DECLINED")]
    execute(w.db, plan.id, writer, now=NOW)
    s1, s2, s3 = steps_of(w, plan)
    assert (s1.state, s2.state, s3.state) == ("FAILED", "SENT", "SENT") and len(writer.calls) == 3
    lc.confirm_step(w.db, s2, paypal_ref="CAP-2", now=NOW)
    lc.confirm_step(w.db, s3, paypal_ref="CAP-3", now=NOW)
    assert plan.state == "PARTIAL"
    assert w.campaign.state == "CAPTURING" and w.project.state == "PLEDGING"        # never half-funded IN_PROGRESS
    assert ledger.pool_balance(w.db, w.project.id) == 25000


def test_all_steps_failing_marks_the_plan_failed(w):
    plan = approved_capture(w)
    writer = FakeWriter()
    writer.errors["capture"] = [rejected(), rejected(), rejected()]
    execute(w.db, plan.id, writer, now=NOW)
    assert plan.state == "FAILED" and ledger.pool_balance(w.db, w.project.id) == 0


def test_a_failed_step_is_never_resent_on_resume(w):
    plan = approved_capture(w)
    writer = FakeWriter()
    writer.errors["capture"] = [rejected()]
    execute(w.db, plan.id, writer, now=NOW)
    again = FakeWriter()
    execute(w.db, plan.id, again, now=NOW)
    assert steps_of(w, plan)[0].idempotency_key not in again.keys()


# ================= crash safety / idempotency =================

def test_resuming_after_a_crash_reuses_the_same_keys_and_skips_confirmed_steps(w):
    plan = approved_capture(w)
    keys = [s.idempotency_key for s in steps_of(w, plan)]
    crashing = FakeWriter()
    crashing.crash_on_call = 2                                                       # dies while sending step 2
    with pytest.raises(RuntimeError):
        execute(w.db, plan.id, crashing, now=NOW)
    assert [s.state for s in steps_of(w, plan)] == ["SENT", "SENT", "PENDING"]
    lc.confirm_step(w.db, steps_of(w, plan)[0], paypal_ref="CAP-1", now=NOW)         # webhook for step 1 arrived
    resumed = FakeWriter()
    execute(w.db, plan.id, resumed, now=NOW)
    assert resumed.keys() == keys[1:], "step 1 is confirmed and skipped; steps 2 and 3 re-sent with their ORIGINAL keys"
    assert set(crashing.keys() + resumed.keys()) == set(keys), "no key was ever invented twice"


def test_executing_twice_never_invents_new_keys(w):
    plan = approved_capture(w)
    a, b = FakeWriter(), FakeWriter()
    execute(w.db, plan.id, a, now=NOW)
    execute(w.db, plan.id, b, now=NOW)
    assert a.keys() == b.keys()


def test_a_finished_plan_cannot_run_again(w):
    plan = approved_capture(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    confirm_all(w, plan)
    assert plan.state == "DONE"
    refused(w, plan, "DONE")


def test_phase_two_waits_until_phase_one_is_confirmed(w):
    plan = approved_capture(w)
    spec = MoneyPlanSpec.model_validate(plan.plan_json)
    spec.steps[2].phase = 2                                                          # forge a 2-phase plan
    new_hash = plan_hash(spec)
    for s in spec.steps:
        s.idempotency_key = idempotency_key(new_hash, s.seq)
    plan.plan_json, plan.plan_hash, plan.state = spec.model_dump(mode="json"), new_hash, "EXECUTING"
    for row, s in zip(steps_of(w, plan), spec.steps):
        row.phase, row.idempotency_key = s.phase, s.idempotency_key
    for a in w.db.scalars(select(PlanApproval)):
        a.plan_hash = new_hash
    for r in w.db.scalars(select(GuardianReview)):
        r.plan_hash = new_hash
    w.db.flush()
    writer = FakeWriter()
    execute(w.db, plan.id, writer, now=NOW)
    assert len(writer.calls) == 2, "phase 2 must not start while phase 1 is only SENT"
    s1, s2, s3 = steps_of(w, plan)
    lc.confirm_step(w.db, s1, paypal_ref="A", now=NOW)
    lc.confirm_step(w.db, s2, paypal_ref="B", now=NOW)
    later = FakeWriter()
    execute(w.db, plan.id, later, now=NOW)
    assert later.keys() == [s3.idempotency_key]


# ================= release: nobody is charged =================

def test_release_voids_every_hold_and_charges_nobody(w):
    plan = approved_release(w)
    writer = FakeWriter()
    execute(w.db, plan.id, writer, now=NOW)
    assert writer.ops() == ["void"] * 3 and "capture" not in writer.ops()
    assert w.campaign.state == "FAILING" and w.campaign.fail_reason == "LEAD_CANCEL"
    confirm_all(w, plan)
    assert plan.state == "DONE" and w.campaign.state == "FAILED" and w.project.state == "CAMPAIGN_FAILED"
    assert {p.status for p in w.db.scalars(select(Pledge))} == {"VOIDED"}
    assert ledger.pool_balance(w.db, w.project.id) == 0
    assert "PLEDGE_CAPTURED" not in ledger_types(w) and ledger_types(w).count("PLEDGE_VOIDED") == 3


def test_a_release_with_no_holds_completes_without_calling_paypal(w):
    plan = approved_release(w, holds=())
    writer = FakeWriter()
    execute(w.db, plan.id, writer, now=NOW)
    assert writer.calls == [] and plan.state == "DONE" and w.campaign.state == "FAILED"


def test_release_after_deadline_is_automatic_on_allow(w):
    for h in (15000, 10000, 5000):
        w.pledge(h)
    built = pb.build_release_holds(w.db, w.campaign.id, "DEADLINE_MISSED")
    plan = pb.save_proposed(w.db, built, proposed_by="system")
    from datetime import timedelta
    lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW + timedelta(hours=41))
    assert plan.state == "APPROVED" and w.db.scalars(select(PlanApproval)).first().approver == "system:AUTO_ON_ALLOW"


# ================= freelancer payout =================

def test_payout_sends_one_item_to_the_locked_email_and_pays_after_confirmation(w):
    plan = approved_payout(w)
    writer = FakeWriter()
    execute(w.db, plan.id, writer, now=NOW)
    [call] = writer.calls
    assert call["op"] == "payout" and call["request_id"] == steps_of(w, plan)[0].idempotency_key
    assert call["sender_batch_id"] == f"briefpay-{w.project.id}-{plan.id}-1"
    assert [(i["receiver"], i["amount_cents"]) for i in call["items"]] == [("arjun@sandbox.com", GOAL)]
    assert w.project.state == "PAYOUT_PENDING"
    batch = w.db.scalars(select(PayoutBatch)).one()
    item = w.db.scalars(select(PayoutItem)).one()
    assert batch.paypal_batch_id and item.sender_item_id == str(item.id) and (batch.status, item.status) == ("PENDING", "PENDING")
    assert ledger.pool_balance(w.db, w.project.id) == GOAL, "money has not left the pool until PayPal confirms"
    confirm_all(w, plan)
    assert ledger.pool_balance(w.db, w.project.id) == 0 and "PAYOUT_SENT" in ledger_types(w)
    assert w.project.state == "PAID" and (batch.status, item.status) == ("SUCCESS", "SUCCEEDED")


def test_failed_payout_can_be_retried_as_a_new_plan_with_new_keys(w):
    plan = approved_payout(w)
    writer = FakeWriter()
    writer.errors["payout"] = [rejected("RECEIVER_UNREGISTERED")]
    execute(w.db, plan.id, writer, now=NOW)
    assert plan.state == "FAILED" and w.project.state == "PAYOUT_FAILED"
    assert w.db.scalars(select(PayoutBatch)).one().status == "FAILED"
    assert ledger.pool_balance(w.db, w.project.id) == GOAL                           # nothing left the pool

    retry, review = reviewed(w, pb.build_freelancer_payout(w.db, w.project.id), by=lead(w))
    assert retry.plan_hash != plan.plan_hash and review.decision == "ALLOW", \
        [(r["id"], r["detail"]) for r in review.rule_results_json if r["status"] != "PASS"]
    lc.approve_plan(w.db, retry, approver=lead(w), plan_hash=retry.plan_hash, guardian_review_id=review.id)
    again = FakeWriter()
    execute(w.db, retry.id, again, now=NOW)
    assert again.calls[0]["sender_batch_id"].endswith("-2") and w.project.state == "PAYOUT_PENDING"
    assert again.keys()[0] != writer.keys()[0]
    confirm_all(w, retry)
    assert w.project.state == "PAID"


# ================= refund =================

def test_refund_returns_money_to_the_original_captures(w):
    funded(w)
    w.project.state = "IN_PROGRESS"
    plan, review = reviewed(w, pb.build_refund_captured(w.db, w.project.id, "CANCEL_BEFORE_WORK"), by=lead(w))
    assert plan.state == "REVIEWED" and review.decision == "ALLOW"
    lc.approve_plan(w.db, plan, approver=lead(w), plan_hash=plan.plan_hash, guardian_review_id=review.id)
    writer = FakeWriter()
    execute(w.db, plan.id, writer, now=NOW)
    assert writer.ops() == ["refund"] * 3 and w.project.state == "REFUNDING"
    assert sorted(c["capture_id"] for c in writer.calls) == sorted(p.paypal_capture_id for p in w.db.scalars(select(Pledge)))
    assert {r.status for r in w.db.scalars(select(Refund))} == {"PENDING"}
    confirm_all(w, plan)
    assert ledger.pool_balance(w.db, w.project.id) == 0 and w.project.state == "CANCELLED"
    assert sum(p.refunded_cents for p in w.db.scalars(select(Pledge))) == GOAL
    assert {r.status for r in w.db.scalars(select(Refund))} == {"COMPLETED"}


# ================= stuff the executor will not touch =================

def test_a_step_aimed_at_another_projects_object_fails_without_a_paypal_call(w):
    plan = approved_capture(w)
    other = World(w.db, tag="Z")
    foreign = other.pledge(1000)
    row = steps_of(w, plan)[0]
    row.target_id = foreign.id                                                       # DB row and plan_json now disagree
    refused(w, plan, "differ from the approved plan")


def test_confirm_refuses_an_unsupported_op(w):
    plan = approved_capture(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    s = steps_of(w, plan)[0]
    s.op = "REAUTH_AUTH"
    with pytest.raises(lc.LifecycleError):
        lc.confirm_step(w.db, s)
