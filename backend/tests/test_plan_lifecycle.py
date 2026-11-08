import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import GuardianReview, Job, LedgerEntry, MoneyPlan, PlanApproval, Pledge, ProjectMember, User
from app.services import jobs, paypal_io, plan_builder as pb, plan_lifecycle as lc
from app.services.guardian_tamper import MUTATIONS
from tests.factories import GOAL, NOW, FakeReader, FakeWriter, World


@pytest.fixture()
def w(db):
    return World(db)


def lead(w):
    return f"user:{w.project.lead_user_id}"


def add_member(w, role, tag):
    u = User(email=f"{tag}@x.com", display_name=tag)
    w.db.add(u)
    w.db.flush()
    w.db.add(ProjectMember(project_id=w.project.id, user_id=u.id, role=role))
    w.db.flush()
    return f"user:{u.id}"


def funded(w):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    w.capture_all()
    w.project.state = "PAYOUT_READY"
    w.verified_report()
    w.db.flush()


def payout(w):
    funded(w)
    plan = pb.save_proposed(w.db, pb.build_freelancer_payout(w.db, w.project.id), proposed_by=lead(w))
    return plan, lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW)


def hold_plan(w):
    """A capture plan whose review is a HOLD: the freelancer funded their own job (S-01)."""
    for h in (15000, 15000, 10000):
        w.pledge(h)
    w.db.scalars(select(Pledge)).first().payer_email = "arjun@sandbox.com"
    w.db.flush()
    plan = pb.save_proposed(w.db, pb.build_capture_pledges(w.db, w.campaign.id, NOW), proposed_by=lead(w))
    return plan, lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW)


# ---------------- review ----------------

def test_review_writes_a_review_row_a_ledger_memo_and_moves_the_plan(w):
    plan, review = payout(w)
    assert plan.state == "REVIEWED" and review.decision == "ALLOW" and not review.simulated
    assert len(review.rule_results_json) == 9 and len(review.sha256) == 64
    memo = w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "GUARDIAN_DECISION")).one()
    assert memo.amount_cents == 0 and memo.meta_json["decision"] == "ALLOW" and memo.actor == "agent:guardian"


def test_a_blocked_plan_is_terminal_and_cannot_be_approved(w):
    plan, _ = payout(w)
    w.contract.freelancer_paypal_email = "attacker@evil.com"                            # data tampered after the preview
    review = lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW)
    assert review.decision == "BLOCK" and plan.state == "BLOCKED"
    with pytest.raises(lc.LifecycleError) as e:
        lc.approve_plan(w.db, plan, approver=lead(w), plan_hash=plan.plan_hash, guardian_review_id=review.id)
    assert e.value.code == "BLOCKED"
    with pytest.raises(lc.LifecycleError):
        lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW)                    # BLOCKED never reviewed again


def test_auto_plans_are_approved_by_the_system_only_when_allowed(w):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    plan = pb.save_proposed(w.db, pb.build_capture_pledges(w.db, w.campaign.id, NOW), proposed_by="system")
    lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW)
    assert plan.state == "APPROVED"
    assert w.db.scalars(select(PlanApproval)).one().approver == "system:AUTO_ON_ALLOW"
    job = w.db.scalars(select(Job)).one()
    assert job.type == "EXECUTE_PLAN" and job.payload_json == {"plan_id": plan.id}


def test_a_hold_is_never_auto_approved(w):
    plan, review = hold_plan(w)
    assert review.decision == "HOLD" and plan.state == "REVIEWED" and plan.release_policy == "AUTO_ON_ALLOW"
    assert w.db.scalars(select(PlanApproval)).first() is None and w.db.scalars(select(Job)).first() is None


def test_human_plans_wait_for_a_human_even_when_allowed(w):
    plan, review = payout(w)
    assert review.decision == "ALLOW" and plan.state == "REVIEWED"
    with pytest.raises(lc.LifecycleError) as e:
        lc.approve_plan(w.db, plan, approver="system:AUTO_ON_ALLOW", plan_hash=plan.plan_hash, guardian_review_id=review.id)
    assert e.value.code == "NOT_AUTOMATIC"


# ---------------- approval ----------------

def approve(w, plan, review, approver=None, **kw):
    return lc.approve_plan(w.db, plan, approver=approver or lead(w), plan_hash=kw.pop("plan_hash", plan.plan_hash),
                           guardian_review_id=kw.pop("review_id", review.id), **kw)


def code(excinfo):
    return excinfo.value.code


def test_human_approval_creates_a_hash_bound_approval_and_queues_execution(w):
    plan, review = payout(w)
    a = approve(w, plan, review)
    assert plan.state == "APPROVED" and a.plan_hash == plan.plan_hash and a.guardian_review_id == review.id
    assert w.db.scalars(select(Job)).one().payload_json == {"plan_id": plan.id}
    assert w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "APPROVAL")).one().actor == lead(w)


def test_approval_must_carry_the_current_hash(w):
    plan, review = payout(w)
    with pytest.raises(lc.LifecycleError) as e:
        approve(w, plan, review, plan_hash="0" * 64)
    assert code(e) == "HASH_MISMATCH" and plan.state == "REVIEWED"


def test_approval_needs_a_reviewed_plan(w):
    funded(w)
    plan = pb.save_proposed(w.db, pb.build_freelancer_payout(w.db, w.project.id), proposed_by=lead(w))
    with pytest.raises(lc.LifecycleError) as e:
        lc.approve_plan(w.db, plan, approver=lead(w), plan_hash=plan.plan_hash, guardian_review_id=1)
    assert code(e) == "PLAN_STATE"


def test_a_stale_review_cannot_be_used(w):
    plan, old = payout(w)
    new = lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW)                  # reviewed again
    assert new.id != old.id
    with pytest.raises(lc.LifecycleError) as e:
        approve(w, plan, old)
    assert code(e) == "STALE_REVIEW"
    approve(w, plan, new)


def test_a_simulated_review_can_never_approve_anything(w):
    plan, review = payout(w)
    sim = lc.simulate_tamper(w.db, plan, "SWAP_RECIPIENT", reader=FakeReader(w.db), now=NOW)
    assert sim.simulated and sim.decision == "BLOCK"
    with pytest.raises(lc.LifecycleError) as e:
        approve(w, plan, sim)
    assert code(e) == "BAD_REVIEW"
    assert lc.latest_review(w.db, plan.id).id == review.id, "simulations must not shadow the real review"
    approve(w, plan, review)


def test_a_review_of_another_plan_is_rejected(w):
    plan, _ = payout(w)
    other = World(w.db, tag="O")
    funded(other)
    p2 = pb.save_proposed(w.db, pb.build_freelancer_payout(w.db, other.project.id), proposed_by=f"user:{other.project.lead_user_id}")
    r2 = lc.review_plan(w.db, p2, reader=FakeReader(w.db), now=NOW)
    with pytest.raises(lc.LifecycleError) as e:
        approve(w, plan, r2)
    assert code(e) == "BAD_REVIEW"


def test_hold_needs_a_human_acknowledgement_note(w):
    plan, review = hold_plan(w)
    for note in (None, "", "   "):
        with pytest.raises(lc.LifecycleError) as e:
            approve(w, plan, review, ack_note=note)
        assert code(e) == "ACK_REQUIRED"
    a = approve(w, plan, review, ack_note="Arjun's sister pledged from the same account; fine.")
    assert a.ack_note.startswith("Arjun") and plan.state == "APPROVED"


def test_hold_on_capture_or_release_needs_the_lead_not_just_a_sponsor(w):
    plan, review = hold_plan(w)
    sponsor = add_member(w, "SPONSOR", "ravi")
    with pytest.raises(lc.LifecycleError) as e:
        approve(w, plan, review, approver=sponsor, ack_note="ok")
    assert code(e) == "FORBIDDEN"
    approve(w, plan, review, approver=lead(w), ack_note="ok")


def test_roles_for_payout_approval(w):
    plan, review = payout(w)
    for approver in (add_member(w, "FREELANCER", "arjun2"), add_member(w, "SUPPORTER", "fan"), "user:99999", "bob"):
        with pytest.raises(lc.LifecycleError) as e:
            approve(w, plan, review, approver=approver)
        assert code(e) in ("FORBIDDEN", "BAD_APPROVER")
    approve(w, plan, review, approver=add_member(w, "SPONSOR", "meena"))                # a sponsor may approve a payout


def test_refunds_are_approved_by_the_lead_only(w):
    funded(w)
    w.project.state = "IN_PROGRESS"
    plan = pb.save_proposed(w.db, pb.build_refund_captured(w.db, w.project.id, "CANCEL_BEFORE_WORK"), proposed_by=lead(w))
    review = lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW)
    assert review.decision == "ALLOW"
    with pytest.raises(lc.LifecycleError) as e:
        approve(w, plan, review, approver=add_member(w, "SPONSOR", "ravi"))
    assert code(e) == "FORBIDDEN"
    approve(w, plan, review)


def test_an_approved_plan_cannot_be_approved_twice(w):
    plan, review = payout(w)
    approve(w, plan, review)
    with pytest.raises(lc.LifecycleError) as e:
        approve(w, plan, review)
    assert code(e) == "PLAN_STATE"
    assert len(list(w.db.scalars(select(Job)))) == 1


# ---------------- tamper simulation ----------------

@pytest.mark.parametrize("mutation", ["SWAP_RECIPIENT", "INFLATE_AMOUNT", "EXTRA_RECIPIENT"])
def test_simulated_payout_tampering_is_stored_labelled_and_blocked(w, mutation):
    plan, _ = payout(w)
    sim = lc.simulate_tamper(w.db, plan, mutation, reader=FakeReader(w.db), now=NOW)
    assert sim.simulated and sim.decision == "BLOCK" and sim.llm_review_json == {"simulated_mutation": mutation}
    assert MUTATIONS[mutation][1] <= {r["id"] for r in sim.rule_results_json if r["status"] == "FAIL"}
    memo = w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "GUARDIAN_DECISION")).all()[-1]
    assert memo.meta_json["simulated"] is True
    assert plan.state == "REVIEWED", "a simulation never changes the real plan"


# ---------------- end to end through the job runner ----------------

def test_approval_queues_a_job_that_executes_with_the_configured_writer(w, db):
    writer = FakeWriter()
    paypal_io.configure(writer=writer)
    try:
        plan, review = payout(w)
        approve(w, plan, review)
        w.db.commit()
        factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
        assert jobs.run_one(factory) is True
        w.db.expire_all()
        assert w.db.get(MoneyPlan, plan.id).state == "EXECUTING"
        assert writer.ops() == ["payout"]
        job = w.db.scalars(select(Job)).one()
        assert job.state == "DONE" and job.result_json == {"plan_id": plan.id, "state": "EXECUTING"}
    finally:
        paypal_io.configure(writer=paypal_io.UnconfiguredWriter())


def test_without_paypal_credentials_execution_fails_safely_and_moves_no_money(w, db):
    paypal_io.configure(writer=paypal_io.UnconfiguredWriter())
    plan, review = payout(w)
    approve(w, plan, review)
    w.db.commit()
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    jobs.run_one(factory)
    w.db.expire_all()
    assert w.db.get(MoneyPlan, plan.id).state == "FAILED"
    from app.models import MoneyPlanStep
    from app.services import ledger
    step = w.db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == plan.id)).one()
    assert step.state == "FAILED" and "not configured" in step.error_json["message"]
    assert w.project.state == "PAYOUT_FAILED"
    assert ledger.pool_balance(w.db, w.project.id) == GOAL
