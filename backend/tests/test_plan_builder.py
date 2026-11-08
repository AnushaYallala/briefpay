from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    BRD, Campaign, Contract, MoneyPlan, MoneyPlanStep, Pledge, Project, ProjectMember, Submission, User,
    VerificationReport,
)
from app.services import ledger
from app.services import plan_builder as pb
from app.services.settlement import plan_hash

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
GOAL = 40000


class World:
    """One Velugu Cove project with a signed contract and an OPEN campaign."""

    def __init__(self, db):
        self.db = db
        lead = User(email="lakshmi@x.com", display_name="Lakshmi")
        db.add(lead)
        db.flush()
        self.project = Project(title="Velugu Cove", lead_user_id=lead.id, state="PLEDGING", currency="USD")
        db.add(self.project)
        db.flush()
        self.lead = ProjectMember(project_id=self.project.id, user_id=lead.id, role="LEAD")
        arjun = User(email="arjun@x.com", display_name="Arjun")
        db.add_all([self.lead, arjun])
        db.flush()
        fm = ProjectMember(project_id=self.project.id, user_id=arjun.id, role="FREELANCER", paypal_email="arjun@sandbox.com")
        db.add(fm)
        db.flush()
        brd = BRD(project_id=self.project.id, version=1, status="APPROVED", content_json={}, content_md="",
                  sha256="b" * 64, score_at_generation=93)
        db.add(brd)
        db.flush()
        self.contract = Contract(project_id=self.project.id, brd_id=brd.id, brd_sha256=brd.sha256,
                                 freelancer_member_id=fm.id, freelancer_paypal_email="arjun@sandbox.com",
                                 amount_cents=GOAL, delivery_days=5, terms_md="t", sha256="c" * 64, signed_at=NOW)
        self.campaign = Campaign(project_id=self.project.id, number=1, proposer_member_id=self.lead.id, goal_cents=GOAL,
                                 deadline_at=NOW + timedelta(hours=40), state="OPEN", opens_at=NOW - timedelta(hours=8))
        db.add_all([self.contract, self.campaign])
        db.flush()
        self.n = 0

    def pledge(self, cents, status="AUTHORIZED", honor_hours=60, campaign=None, **kw) -> Pledge:
        self.n += 1
        c = campaign or self.campaign
        p = Pledge(campaign_id=c.id, project_id=self.project.id, display_name=f"P{self.n}", amount_cents=cents,
                   paypal_order_id=f"ORDER{self.n}", paypal_authorization_id=f"AUTH{self.n}", status=status,
                   authorized_at=NOW, honor_until=NOW + timedelta(hours=honor_hours), **kw)
        self.db.add(p)
        self.db.flush()
        return p

    def capture_all(self):
        """Pretend the capture plan ran: pledges CAPTURED, POOL funded, campaign CAPTURED."""
        for p in self.db.scalars(select(Pledge).where(Pledge.status == "AUTHORIZED")):
            p.status, p.captured_cents, p.paypal_capture_id = "CAPTURED", p.amount_cents, f"CAP{p.id}"
            ledger.append(self.db, self.project.id, "PLEDGE_CAPTURED", p.amount_cents, actor="paypal")
        self.campaign.state = "CAPTURED"
        self.db.flush()

    def verified_report(self, overall="VERIFIED", attempt=1):
        sub = Submission(contract_id=self.contract.id, attempt_no=attempt, repo_url="r", commit_sha="s", deployed_url="u")
        self.db.add(sub)
        self.db.flush()
        rep = VerificationReport(submission_id=sub.id, verdicts_json=[], overall=overall, must_pass_pct=100,
                                 should_pass_pct=100, summary="ok", sha256=("d" if overall == "VERIFIED" else "e") * 64)
        self.db.add(rep)
        self.db.flush()
        return rep


@pytest.fixture()
def w(db):
    return World(db)


def demo_pledges(w):
    return [w.pledge(15000), w.pledge(15000), w.pledge(10000)]


# ---------------- CAPTURE_PLEDGES ----------------

def test_capture_plan_demo_success(w):
    ps = demo_pledges(w)
    b = pb.build_capture_pledges(w.db, w.campaign.id, NOW)
    s = b.spec
    assert s.kind == "CAPTURE_PLEDGES" and s.reason == "GOAL_REACHED"
    assert [(x.op, x.target_id, x.amount_cents, x.bucket, x.phase) for x in s.steps] == [
        ("CAPTURE_AUTH", p.id, p.amount_cents, "POOL", 1) for p in ps]
    assert [x.seq for x in s.steps] == [1, 2, 3]
    assert sum(x.amount_cents for x in s.steps) == GOAL
    assert s.inputs["brd_sha256"] == "b" * 64 and s.contract_id == w.contract.id


def test_capture_plan_overpledge_race_captures_exactly_the_goal(w):
    holds = [15000, 15000, 10000, 2000]
    for h in holds:
        w.pledge(h)
    s = pb.build_capture_pledges(w.db, w.campaign.id, NOW).spec
    assert [x.amount_cents for x in s.steps] == [14286, 14285, 9524, 1905]
    assert sum(x.amount_cents for x in s.steps) == GOAL
    assert all(x.amount_cents <= h for x, h in zip(s.steps, holds))


def test_capture_plan_is_deterministic_and_keys_derive_from_hash(w):
    demo_pledges(w)
    a = pb.build_capture_pledges(w.db, w.campaign.id, NOW)
    b = pb.build_capture_pledges(w.db, w.campaign.id, NOW + timedelta(minutes=5))
    assert a.plan_hash == b.plan_hash == plan_hash(a.spec)  # keys don't feed the hash
    assert [s.idempotency_key for s in a.spec.steps] == [f"{a.plan_hash[:16]}-{i}" for i in (1, 2, 3)]


def test_below_goal_cannot_be_captured(w):
    w.pledge(15000), w.pledge(10000), w.pledge(5000)  # worked example 2: $300 of $400
    with pytest.raises(pb.PlanBuildError, match="goal not reached"):
        pb.build_capture_pledges(w.db, w.campaign.id, NOW)


def test_lapsed_voided_denied_and_foreign_holds_do_not_count(w):
    w.pledge(15000), w.pledge(15000), w.pledge(5000)
    w.pledge(5000, honor_hours=-1)                       # honor period over
    w.pledge(9000, status="VOIDED")
    w.pledge(9000, status="CREATED")
    other = Campaign(project_id=w.project.id, number=2, proposer_member_id=w.lead.id, goal_cents=1,
                     deadline_at=NOW, state="OPEN")
    w.db.add(other)
    w.db.flush()
    w.pledge(9000, campaign=other)
    with pytest.raises(pb.PlanBuildError):               # only $350 is live in this campaign
        pb.build_capture_pledges(w.db, w.campaign.id, NOW)


def test_a_hold_lapsing_changes_the_plan_hash(w):
    """This is how G-01 catches 'a pledge expired between preview and run'."""
    ps = demo_pledges(w)
    w.pledge(5000, honor_hours=2)
    before = pb.build_capture_pledges(w.db, w.campaign.id, NOW)
    after = pb.build_capture_pledges(w.db, w.campaign.id, NOW + timedelta(hours=3))
    assert before.plan_hash != after.plan_hash
    assert len(after.spec.steps) == len(ps)


def test_hold_without_authorization_id_is_ignored(w):
    demo_pledges(w)
    p = w.pledge(9999)
    p.paypal_authorization_id = None
    w.db.flush()
    s = pb.build_capture_pledges(w.db, w.campaign.id, NOW).spec
    assert p.id not in {x.target_id for x in s.steps}


@pytest.mark.parametrize("state", ["SETUP", "CAPTURING", "CAPTURED", "FAILING", "FAILED"])
def test_capture_only_from_open_campaign(w, state):
    demo_pledges(w)
    w.campaign.state = state
    with pytest.raises(pb.PlanBuildError, match="not OPEN"):
        pb.build_capture_pledges(w.db, w.campaign.id, NOW)


# ---------------- RELEASE_HOLDS ----------------

def test_release_plan_voids_every_hold_and_charges_nothing(w):
    ps = [w.pledge(15000), w.pledge(10000), w.pledge(5000)]
    w.pledge(777, status="VOIDED")
    s = pb.build_release_holds(w.db, w.campaign.id, "DEADLINE_MISSED").spec
    assert s.kind == "RELEASE_HOLDS" and s.reason == "DEADLINE_MISSED"
    assert [(x.op, x.target_id, x.bucket) for x in s.steps] == [("VOID_AUTH", p.id, "NONE") for p in ps]
    assert not any(x.op == "CAPTURE_AUTH" for x in s.steps)
    assert all(x.bucket == "NONE" for x in s.steps)   # voids never touch POOL


def test_release_includes_holds_past_honor_period(w):
    old = w.pledge(1000, honor_hours=-5)
    s = pb.build_release_holds(w.db, w.campaign.id, "LEAD_CANCEL").spec
    assert [x.target_id for x in s.steps] == [old.id]


def test_release_with_no_holds_is_an_empty_plan(w):
    assert pb.build_release_holds(w.db, w.campaign.id, "DEADLINE_MISSED").spec.steps == []


def test_release_refuses_when_something_was_captured(w):
    w.pledge(1000)
    w.pledge(500, status="CAPTURED", captured_cents=500)
    with pytest.raises(pb.PlanBuildError, match="already captured"):
        pb.build_release_holds(w.db, w.campaign.id, "LEAD_CANCEL")


def test_release_rejects_bad_reason_and_wrong_campaign_state(w):
    with pytest.raises(pb.PlanBuildError):
        pb.build_release_holds(w.db, w.campaign.id, "BECAUSE")
    w.campaign.state = "CAPTURED"
    with pytest.raises(pb.PlanBuildError):
        pb.build_release_holds(w.db, w.campaign.id, "LEAD_CANCEL")


# ---------------- FREELANCER_PAYOUT ----------------

def funded(w):
    demo_pledges(w)
    w.capture_all()


def test_payout_plan_pays_the_locked_email_the_contract_amount(w):
    funded(w)
    rep = w.verified_report()
    s = pb.build_freelancer_payout(w.db, w.project.id).spec
    [step] = s.steps
    assert (step.op, step.target_type, step.target_id, step.amount_cents, step.bucket, step.receiver_email) == (
        "PAYOUT_ITEM", "CONTRACT", w.contract.id, GOAL, "POOL", "arjun@sandbox.com")
    assert s.inputs["report_sha256"] == rep.sha256 and s.inputs["brd_sha256"] == "b" * 64
    assert s.reason == "VERIFIED"


def test_payout_hash_changes_if_recipient_or_amount_is_tampered(w):
    funded(w)
    w.verified_report()
    base = pb.build_freelancer_payout(w.db, w.project.id).plan_hash
    w.contract.freelancer_paypal_email = "attacker@evil.com"
    assert pb.build_freelancer_payout(w.db, w.project.id).plan_hash != base


@pytest.mark.parametrize("overall", ["NEEDS_CHANGES", "FAILED"])
def test_payout_needs_a_verified_report(w, overall):
    funded(w)
    w.verified_report(overall)
    with pytest.raises(pb.PlanBuildError, match="VERIFIED"):
        pb.build_freelancer_payout(w.db, w.project.id)


def test_payout_uses_only_the_latest_submissions_report(w):
    funded(w)
    w.verified_report("VERIFIED", attempt=1)
    w.verified_report("NEEDS_CHANGES", attempt=2)   # a newer attempt supersedes the old pass
    with pytest.raises(pb.PlanBuildError):
        pb.build_freelancer_payout(w.db, w.project.id)


def test_payout_without_report_contract_funding_or_email(w):
    with pytest.raises(pb.PlanBuildError, match="VERIFIED"):
        pb.build_freelancer_payout(w.db, w.project.id)
    w.verified_report()
    with pytest.raises(pb.PlanBuildError, match="captured campaign"):
        pb.build_freelancer_payout(w.db, w.project.id)
    funded(w)
    w.contract.freelancer_paypal_email = None
    with pytest.raises(pb.PlanBuildError, match="email"):
        pb.build_freelancer_payout(w.db, w.project.id)
    w.contract.signed_at = None
    with pytest.raises(pb.PlanBuildError, match="signed"):
        pb.build_freelancer_payout(w.db, w.project.id)


def test_payout_blocked_when_pool_is_short(w):
    funded(w)
    w.verified_report()
    ledger.append(w.db, w.project.id, "REFUND", -1, actor="paypal")
    with pytest.raises(pb.PlanBuildError, match="Pool does not cover"):
        pb.build_freelancer_payout(w.db, w.project.id)


def test_payout_fee_reserve_must_be_covered(w):
    funded(w)
    w.verified_report()
    w.campaign.fee_reserve_cents = 25
    with pytest.raises(pb.PlanBuildError):
        pb.build_freelancer_payout(w.db, w.project.id)


# ---------------- REFUND_CAPTURED ----------------

def test_refund_plan_returns_each_capture_in_full(w):
    funded(w)
    s = pb.build_refund_captured(w.db, w.project.id, "CANCEL_BEFORE_WORK").spec
    assert [(x.op, x.target_type, x.amount_cents, x.bucket) for x in s.steps] == [("REFUND_CAPTURE", "CAPTURE", a, "POOL") for a in (15000, 15000, 10000)]
    assert sum(x.amount_cents for x in s.steps) == ledger.pool_balance(w.db, w.project.id)
    assert all(c["capture_id"] for c in s.inputs["captures"])


def test_refund_accounts_for_prior_partial_refunds(w):
    funded(w)
    first = w.db.scalars(select(Pledge).order_by(Pledge.id)).first()
    first.refunded_cents = 5000
    ledger.append(w.db, w.project.id, "REFUND", -5000, actor="paypal")
    s = pb.build_refund_captured(w.db, w.project.id, "VERIFICATION_FAILED_FINAL").spec
    assert [x.amount_cents for x in s.steps] == [10000, 15000, 10000]


def test_refund_refused_after_payout_or_with_bad_reason_or_nothing_to_refund(w):
    funded(w)
    with pytest.raises(pb.PlanBuildError):
        pb.build_refund_captured(w.db, w.project.id, "I_CHANGED_MY_MIND")
    ledger.append(w.db, w.project.id, "PAYOUT_SENT", -GOAL, actor="paypal")
    with pytest.raises(pb.PlanBuildError, match="POOL"):
        pb.build_refund_captured(w.db, w.project.id, "CANCEL_BEFORE_WORK")


def test_refund_with_nothing_captured(w):
    demo_pledges(w)
    with pytest.raises(pb.PlanBuildError, match="nothing"):
        pb.build_refund_captured(w.db, w.project.id, "CANCEL_BEFORE_WORK")


# ---------------- persistence, rebuild, policy ----------------

def test_save_proposed_stores_plan_and_steps_and_is_idempotent(w):
    demo_pledges(w)
    built = pb.build_capture_pledges(w.db, w.campaign.id, NOW)
    p1 = pb.save_proposed(w.db, built, proposed_by="system")
    p2 = pb.save_proposed(w.db, built, proposed_by="system")
    assert p1.id == p2.id
    assert (p1.state, p1.plan_hash, p1.release_policy, p1.kind) == ("PROPOSED", built.plan_hash, "AUTO_ON_ALLOW", "CAPTURE_PLEDGES")
    steps = list(w.db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == p1.id).order_by(MoneyPlanStep.seq)))
    assert [s.idempotency_key for s in steps] == [s.idempotency_key for s in built.spec.steps]
    assert all(s.state == "PENDING" for s in steps)
    assert p1.plan_json["steps"][0]["op"] == "CAPTURE_AUTH"


@pytest.mark.parametrize("failed_state", ["FAILED", "PARTIAL", "BLOCKED"])
def test_retry_after_a_bad_plan_gets_a_new_hash_and_new_keys(w, failed_state):
    funded(w)
    w.verified_report()
    first = pb.save_proposed(w.db, pb.build_freelancer_payout(w.db, w.project.id), proposed_by="user:1")
    assert "attempt" not in first.plan_json["inputs"]            # first attempts keep their original hash
    first.state = failed_state                                    # e.g. PAYOUT_FAILED
    w.db.flush()
    retry_built = pb.build_freelancer_payout(w.db, w.project.id)
    assert retry_built.spec.inputs["attempt"] == 1
    assert retry_built.plan_hash != first.plan_hash
    retry = pb.save_proposed(w.db, retry_built, proposed_by="user:1")   # no idempotency-key collision
    w.db.flush()
    assert retry.id != first.id
    first_keys = {s.idempotency_key for s in w.db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == first.id))}
    retry_keys = {s.idempotency_key for s in w.db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == retry.id))}
    assert first_keys.isdisjoint(retry_keys)


def test_a_plan_does_not_count_itself_when_rebuilt_after_it_failed(w):
    demo_pledges(w)
    plan = pb.save_proposed(w.db, pb.build_capture_pledges(w.db, w.campaign.id, NOW), proposed_by="system")
    plan.state = "PARTIAL"
    w.db.flush()
    assert pb.rebuild(w.db, plan, NOW).plan_hash == plan.plan_hash


def test_done_plans_do_not_bump_the_attempt(w):
    funded(w)
    w.verified_report()
    p = pb.save_proposed(w.db, pb.build_freelancer_payout(w.db, w.project.id), proposed_by="user:1")
    p.state = "DONE"
    w.db.flush()
    assert "attempt" not in pb.build_freelancer_payout(w.db, w.project.id).spec.inputs


def test_rebuild_matches_stored_plan_until_state_changes(w):
    demo_pledges(w)
    built = pb.build_capture_pledges(w.db, w.campaign.id, NOW)
    plan = pb.save_proposed(w.db, built, proposed_by="system")
    assert pb.rebuild(w.db, plan, NOW).plan_hash == plan.plan_hash
    w.db.scalars(select(Pledge)).first().status = "VOIDED"   # a buyer voided their hold
    w.db.flush()
    w.pledge(1000)                                            # a replacement keeps the goal reachable
    w.pledge(14000)
    assert pb.rebuild(w.db, plan, NOW).plan_hash != plan.plan_hash


def test_rebuild_for_release_and_refund_uses_stored_reason(w):
    w.pledge(1000)
    rel = pb.save_proposed(w.db, pb.build_release_holds(w.db, w.campaign.id, "LEAD_CANCEL"), proposed_by="user:1")
    assert pb.rebuild(w.db, rel).plan_hash == rel.plan_hash


def test_release_policies_follow_the_spec(w):
    assert pb.release_policy_for(w.db, "CAPTURE_PLEDGES", w.project.id) == "AUTO_ON_ALLOW"
    assert pb.release_policy_for(w.db, "RELEASE_HOLDS", w.project.id) == "AUTO_ON_ALLOW"
    assert pb.release_policy_for(w.db, "REFUND_CAPTURED", w.project.id) == "HUMAN"
    assert pb.release_policy_for(w.db, "FREELANCER_PAYOUT", w.project.id) == "HUMAN"
    w.project.payout_release_policy = "AUTO_ON_GUARDIAN_ALLOW"
    assert pb.release_policy_for(w.db, "FREELANCER_PAYOUT", w.project.id) == "AUTO_ON_ALLOW"
    w.project.payout_release_policy = "AUTO_ON_GUARDIAN_ALLOW"
    assert pb.release_policy_for(w.db, "REFUND_CAPTURED", w.project.id) == "HUMAN"  # refunds never automatic


def test_build_dispatch_and_unknown_kind(w):
    demo_pledges(w)
    assert pb.build(w.db, "CAPTURE_PLEDGES", project_id=w.project.id, campaign_id=w.campaign.id, now=NOW).spec.kind == "CAPTURE_PLEDGES"
    with pytest.raises(pb.PlanBuildError):
        pb.build(w.db, "REAUTH_PLEDGES", project_id=w.project.id)
    assert w.db.scalar(select(MoneyPlan.id)) is None  # building never stores anything
