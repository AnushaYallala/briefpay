"""After a third failed verification (GAP-70): extend the attempts, cancel and refund, or an all-sponsor override."""
import pytest
from sqlalchemy import select

from app.models import LedgerEntry, MoneyPlan, MoneyPlanStep, ProjectMember, Submission, User, VerificationReport
from app.services import failure_decisions as fd
from app.services import plan_builder as pb
from app.services import plan_lifecycle as lc
from app.services import submission_service as svc
from app.services import verify_judge as vj
from tests.factories import FakeReader, NOW, World
from tests.test_plans_api import hdr, lead_user, person
from tests.test_submissions import BODY, freelancer, freelancer_user, w  # noqa: F401
from tests.test_verify_judge import answered, ids_of, out, run_judge, stores  # noqa: F401


def failing(rows):
    return out(rows, ("AC-1", "fail", 0.9, ids_of(rows, "AC-1")), ("AC-3", "fail", 0.9, ids_of(rows, "AC-3")))


def sponsor(w, tag):
    u = person(w, "SPONSOR", tag)
    return w.db.scalars(select(ProjectMember).where(ProjectMember.user_id == u.id, ProjectMember.project_id == w.project.id)).one(), u


def previous_attempts(w, n):
    for i in range(1, n + 1):
        w.db.add(Submission(contract_id=w.contract.id, attempt_no=i, repo_url="r", commit_sha="s", deployed_url="u", state="NEEDS_CHANGES"))
    w.db.flush()


def failed_world(w, funded=True, earlier=2):
    """Attempts 1..earlier were rejected; the next one is judged FAILED. Funds are captured so a refund is possible."""
    if funded:
        for cents in (15000, 15000, 10000):
            w.pledge(cents)
        w.capture_all()
    previous_attempts(w, earlier)
    sub, rows = answered(w)
    assert sub.attempt_no == earlier + 1
    result = run_judge(w, sub, failing(rows))
    return sub, rows, result


def lead_member(w):
    return w.lead


def newer_attempt(w):
    """The freelancer submits again (needs the project IN_PROGRESS), is checked, answers, and the work is judged failing."""
    sub, rows = answered(w)
    return sub, rows, run_judge(w, sub, failing(rows))


# =============================== the situation ===============================

def test_the_third_failed_attempt_waits_for_the_lead_and_the_options_say_what_is_possible(w):
    sponsor(w, "ravi")
    sponsor(w, "meena")
    sub, rows, result = failed_world(w)
    assert result["effect"] == "FAILED" and sub.state == "FAILED" and w.project.state == "VERIFYING"
    o = fd.options(w.db, sub, w.project.id)
    assert (o["open"], o["attempts_used"], o["attempts_allowed"], o["extra_attempts_given"], o["extra_attempts_left"]) == (True, 3, 3, 0, 6)
    assert o["extend"] == {"max_now": 3} and o["override"]["needed"] == 3 and o["override"]["approved"] == 0
    assert [s["vote"] for s in o["override"]["sponsors"]] == ["WAITING"] * 3 and o["override"]["sponsors"][0]["name"] == "Lakshmi"


@pytest.mark.parametrize("state", ["SUBMITTED", "QUESTIONING", "EVIDENCE_RECEIVED", "NEEDS_CHANGES", "VERIFIED", "OVERRIDDEN"])
def test_only_a_failed_submission_can_be_decided_on(w, state):
    sub, rows, _ = failed_world(w)
    sub.state = state
    for call in (lambda: fd.extend(w.db, sub, w.lead, 1, None), lambda: fd.cancel_refund(w.db, sub, w.lead), lambda: fd.vote_override(w.db, sub, w.lead, "APPROVE", None)):
        with pytest.raises(fd.DecisionError) as e:
            call()
        assert e.value.code == "NOT_FAILED"
    assert fd.options(w.db, sub, w.project.id)["open"] is False


def test_only_the_latest_attempt_and_only_while_the_project_waits(w):
    sub, rows, _ = failed_world(w)
    newest = Submission(contract_id=w.contract.id, attempt_no=9, repo_url="r", commit_sha="s", deployed_url="u", state="FAILED")
    w.db.add(newest)
    w.db.flush()
    with pytest.raises(fd.DecisionError) as e:
        fd.extend(w.db, sub, w.lead, 1, None)
    assert e.value.code == "NOT_FAILED"
    w.db.delete(newest)
    w.db.flush()
    w.project.state = "PAYOUT_READY"
    with pytest.raises(fd.DecisionError) as e:
        fd.extend(w.db, sub, w.lead, 1, None)
    assert e.value.code == "PROJECT_STATE"


# =============================== extend ===============================

def test_the_lead_can_extend_and_the_freelancer_gets_exactly_those_attempts(w):
    sub, rows, _ = failed_world(w)
    r = fd.extend(w.db, sub, w.lead, 2, "  one more go, please  ")
    assert r == {"attempts_allowed": 5} and w.project.state == "IN_PROGRESS"
    memo = w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "APPROVAL").order_by(LedgerEntry.seq.desc())).first()
    assert memo.meta_json["kind"] == fd.KIND_EXTEND and memo.meta_json["extra"] == 2 and memo.meta_json["note"] == "one more go, please" and memo.actor.startswith("user:")
    assert fd.allowed_attempts(w.db, w.contract.id) == 5
    fourth, rows4, res4 = newer_attempt(w)
    assert fourth.attempt_no == 4 and res4["effect"] == "NEEDS_CHANGES" and w.project.state == "IN_PROGRESS"        # not FAILED: one attempt left
    fifth, rows5, res5 = newer_attempt(w)
    assert fifth.attempt_no == 5 and res5["effect"] == "FAILED" and w.project.state == "VERIFYING"                  # all five used
    with pytest.raises(svc.SubmissionError) as e:
        svc.create_submission(w.db, w.project, freelancer(w), repo_url=BODY["repo_url"], commit_sha=BODY["commit_sha"], deployed_url=BODY["deployed_url"], notes=None)
    assert e.value.code == "PROJECT_STATE"


def test_without_an_extension_a_fourth_attempt_is_refused(w):
    sub, rows, _ = failed_world(w)
    w.project.state = "IN_PROGRESS"
    with pytest.raises(svc.SubmissionError) as e:
        svc.create_submission(w.db, w.project, freelancer(w), repo_url=BODY["repo_url"], commit_sha=BODY["commit_sha"], deployed_url=BODY["deployed_url"], notes=None)
    assert e.value.code == "MAX_ATTEMPTS" and "3 attempts" in e.value.message


@pytest.mark.parametrize("extra", [0, -1, 4, 10])
def test_an_extension_is_one_to_three_attempts(w, extra):
    sub, rows, _ = failed_world(w)
    with pytest.raises(fd.DecisionError) as e:
        fd.extend(w.db, sub, w.lead, extra, None)
    assert (e.value.code, e.value.status) == ("BAD_EXTRA", 422) and w.project.state == "VERIFYING"


def test_extensions_are_capped_at_six_in_total(w):
    sub, rows, _ = failed_world(w)
    fd.extend(w.db, sub, w.lead, 3, None)
    newer_attempt(w)                                                   # attempt 4: needs changes
    newer_attempt(w)                                                   # attempt 5
    sixth, _, res = newer_attempt(w)                                   # attempt 6 = 3 + 3: all used
    assert res["effect"] == "FAILED"
    fd.extend(w.db, sixth, w.lead, 3, None)
    assert fd.allowed_attempts(w.db, w.contract.id) == 9
    newer_attempt(w)
    newer_attempt(w)
    ninth, _, res = newer_attempt(w)
    assert res["effect"] == "FAILED"
    with pytest.raises(fd.DecisionError) as e:
        fd.extend(w.db, ninth, w.lead, 1, None)
    assert e.value.code == "EXTENSION_LIMIT"
    assert fd.options(w.db, ninth, w.project.id)["extra_attempts_left"] == 0 and fd.options(w.db, ninth, w.project.id)["extend"]["max_now"] == 0


def test_only_the_lead_extends_and_a_note_has_a_length_limit(w):
    sponsor_member, _ = sponsor(w, "ravi")
    sub, rows, _ = failed_world(w)
    for m in (sponsor_member, freelancer(w)):
        with pytest.raises(fd.DecisionError) as e:
            fd.extend(w.db, sub, m, 1, None)
        assert (e.value.code, e.value.status) == ("FORBIDDEN", 403)
    with pytest.raises(fd.DecisionError) as e:
        fd.extend(w.db, sub, w.lead, 1, "x" * 301)
    assert e.value.code == "NOTE_TOO_LONG" and w.project.state == "VERIFYING"


def test_a_second_extension_from_the_same_failure_is_refused(w):
    sub, rows, _ = failed_world(w)
    fd.extend(w.db, sub, w.lead, 1, None)
    with pytest.raises(fd.DecisionError) as e:
        fd.extend(w.db, sub, w.lead, 1, None)
    assert e.value.code == "PROJECT_STATE" and fd.allowed_attempts(w.db, w.contract.id) == 4


# =============================== cancel and refund ===============================

def test_cancel_and_refund_builds_the_refund_plan_once_and_leaves_approval_to_the_normal_path(w):
    sub, rows, _ = failed_world(w)
    plan = fd.cancel_refund(w.db, sub, w.lead)
    assert (plan.kind, plan.state, plan.reason) == ("REFUND_CAPTURED", "PROPOSED", "VERIFICATION_FAILED_FINAL") and plan.proposed_by == f"user:{w.project.lead_user_id}"
    steps = list(w.db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == plan.id)))
    assert sorted(s.amount_cents for s in steps) == [10000, 15000, 15000] and w.project.state == "VERIFYING"
    again = fd.cancel_refund(w.db, sub, w.lead)
    assert again.id == plan.id
    memos = [e for e in w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "APPROVAL")) if e.meta_json.get("kind") == fd.KIND_REFUND]
    assert len(memos) == 1 and memos[0].meta_json["plan_id"] == plan.id
    review = lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW)
    assert review.decision in ("ALLOW", "HOLD") and plan.state == "REVIEWED"                 # a human approves it like any refund


def test_nothing_to_refund_is_a_clear_error(w):
    sub, rows, _ = failed_world(w, funded=False)
    with pytest.raises(fd.DecisionError) as e:
        fd.cancel_refund(w.db, sub, w.lead)
    assert e.value.code == "NOTHING_TO_REFUND" and w.db.query(MoneyPlan).count() == 0


def test_only_the_lead_can_cancel_and_refund(w):
    sponsor_member, _ = sponsor(w, "ravi")
    sub, rows, _ = failed_world(w)
    with pytest.raises(fd.DecisionError) as e:
        fd.cancel_refund(w.db, sub, sponsor_member)
    assert e.value.code == "FORBIDDEN" and w.db.query(MoneyPlan).count() == 0


# =============================== override ===============================

def test_an_override_needs_every_sponsor_and_each_can_change_their_mind(w):
    ravi, _ = sponsor(w, "ravi")
    meena, _ = sponsor(w, "meena")
    sub, rows, _ = failed_world(w)
    assert fd.vote_override(w.db, sub, w.lead, "APPROVE", "the site is fine for our needs") == {"applied": False, "approved": 1, "needed": 3}
    assert fd.vote_override(w.db, sub, ravi, "APPROVE", None) == {"applied": False, "approved": 2, "needed": 3}
    assert fd.vote_override(w.db, sub, meena, "REJECT", "the form is essential") == {"applied": False, "approved": 2, "needed": 3}
    assert fd.vote_override(w.db, sub, ravi, "REJECT", None)["approved"] == 1                      # a withdrawn approval no longer counts
    assert w.project.state == "VERIFYING" and sub.state == "FAILED" and w.db.query(VerificationReport).count() == 1
    fd.vote_override(w.db, sub, ravi, "APPROVE", None)
    done = fd.vote_override(w.db, sub, meena, "APPROVE", None)
    assert done == {"applied": True, "project_state": "PAYOUT_READY"}
    assert sub.state == "OVERRIDDEN"


def test_the_override_report_is_verified_hash_bound_and_openly_an_override(w):
    ravi, _ = sponsor(w, "ravi")
    sub, rows, _ = failed_world(w)
    failed = w.db.scalars(select(VerificationReport).where(VerificationReport.submission_id == sub.id)).one()
    fd.vote_override(w.db, sub, w.lead, "APPROVE", "agreed with Ravi")
    fd.vote_override(w.db, sub, ravi, "APPROVE", None)
    reports = list(w.db.scalars(select(VerificationReport).where(VerificationReport.submission_id == sub.id).order_by(VerificationReport.id)))
    assert [r.overall for r in reports] == ["FAILED", "VERIFIED"]
    rep = reports[1]
    o = rep.verdicts_json["override"]
    assert o["approved_by"] == ["Lakshmi", "ravi"] and len(o["member_ids"]) == 2 and o["notes"] == ["agreed with Ravi"]
    assert o["failed_report_sha256"] == failed.sha256 and o["failed_overall"] == "FAILED" and "SPONSOR_OVERRIDE" in rep.verdicts_json["reasons"]
    assert rep.summary.startswith("Override: verification FAILED on attempt 3") and (rep.must_pass_pct, rep.should_pass_pct) == (failed.must_pass_pct, failed.should_pass_pct)
    assert rep.sha256 == vj.report_sha(rep.verdicts_json, rep.overall, rep.must_pass_pct, rep.should_pass_pct, rep.summary) and rep.sha256 != failed.sha256
    assert rep.verdicts_json["criteria"] == failed.verdicts_json["criteria"]                       # the real findings stay visible


def test_every_vote_and_the_result_are_in_the_public_ledger(w):
    ravi, _ = sponsor(w, "ravi")
    sub, rows, _ = failed_world(w)
    fd.vote_override(w.db, sub, w.lead, "APPROVE", None)
    fd.vote_override(w.db, sub, ravi, "APPROVE", None)
    entries = list(w.db.scalars(select(LedgerEntry).where(LedgerEntry.project_id == w.project.id).order_by(LedgerEntry.seq)))
    votes = [e for e in entries if e.type == "APPROVAL" and e.meta_json.get("kind") == fd.KIND_OVERRIDE]
    assert [(e.meta_json["decision"], e.actor.startswith("user:")) for e in votes] == [("APPROVE", True), ("APPROVE", True)]
    assert entries[-1].type == "STATE_CHANGE" and entries[-1].meta_json["to"] == "PAYOUT_READY" and entries[-1].actor == "sponsors"


def test_a_repeated_approval_applies_the_override_only_once(w):
    sub, rows, _ = failed_world(w)
    assert fd.vote_override(w.db, sub, w.lead, "APPROVE", None)["applied"] is True                  # the lead is the only sponsor here
    with pytest.raises(fd.DecisionError) as e:
        fd.vote_override(w.db, sub, w.lead, "APPROVE", None)
    assert e.value.code == "NOT_FAILED" and w.db.query(VerificationReport).filter(VerificationReport.overall == "VERIFIED").count() == 1


def test_only_sponsors_vote_and_the_decision_must_be_valid(w):
    sub, rows, _ = failed_world(w)
    with pytest.raises(fd.DecisionError) as e:
        fd.vote_override(w.db, sub, freelancer(w), "APPROVE", None)
    assert (e.value.code, e.value.status) == ("FORBIDDEN", 403)
    with pytest.raises(fd.DecisionError) as e:
        fd.vote_override(w.db, sub, w.lead, "MAYBE", None)
    assert (e.value.code, e.value.status) == ("BAD_DECISION", 422) and w.db.query(LedgerEntry).filter(LedgerEntry.type == "APPROVAL").count() == 0


def test_the_guardian_holds_an_overridden_payout_and_asks_for_an_acknowledgement(w):
    sub, rows, _ = failed_world(w)
    fd.vote_override(w.db, sub, w.lead, "APPROVE", None)
    plan = pb.save_proposed(w.db, pb.build_freelancer_payout(w.db, w.project.id), proposed_by=f"user:{w.project.lead_user_id}")
    assert plan.plan_json["inputs"]["verification_override"] is True
    review = lc.review_plan(w.db, plan, reader=FakeReader(w.db, balance=10 ** 9), now=NOW)
    assert review.decision == "HOLD" and [f["id"] for f in review.soft_flags_json] == ["S-04"]
    assert [r["id"] for r in review.rule_results_json if r["status"] == "FAIL"] == []                 # G-12 accepts the override report
    with pytest.raises(lc.LifecycleError) as e:
        lc.approve_plan(w.db, plan, approver=f"user:{w.project.lead_user_id}", plan_hash=plan.plan_hash, guardian_review_id=review.id)
    assert e.value.code == "ACK_REQUIRED"
    lc.approve_plan(w.db, plan, approver=f"user:{w.project.lead_user_id}", plan_hash=plan.plan_hash, guardian_review_id=review.id, ack_note="all sponsors agreed")
    assert plan.state == "APPROVED"


def test_a_normally_verified_payout_has_no_override_flag(w):
    from tests.test_money_executor import approved_payout
    plan = approved_payout(w)
    assert "verification_override" not in plan.plan_json["inputs"]


# =============================== API ===============================

def test_the_decisions_over_http(client, w, db):
    sponsor(w, "ravi")
    sub, rows, _ = failed_world(w)
    db.commit()
    lead = hdr(lead_user(w))
    base = f"/api/submissions/{sub.id}"
    assert client.get(f"{base}/failure-options").status_code == 401
    assert client.get("/api/submissions/9999/failure-options", headers=lead).status_code == 404
    outsider = hdr(person(World(w.db, tag="o"), "LEAD", "outsider"))
    assert client.get(f"{base}/failure-options", headers=outsider).status_code == 403
    opts = client.get(f"{base}/failure-options", headers=hdr(freelancer_user(w))).json()
    assert opts["open"] is True and opts["override"]["needed"] == 2                                    # the freelancer may read the options

    assert client.post(f"{base}/extend", json={"extra_attempts": 1}, headers=hdr(freelancer_user(w))).status_code == 403
    assert client.post(f"{base}/extend", json={"extra_attempts": 0}, headers=lead).status_code == 422
    assert client.post(f"{base}/cancel-refund", headers=hdr(freelancer_user(w))).status_code == 403
    assert client.post(f"{base}/override", json={"decision": "APPROVE"}, headers=hdr(freelancer_user(w))).status_code == 403
    bad = client.post(f"{base}/override", json={"decision": "MAYBE"}, headers=lead)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "BAD_DECISION"

    refund = client.post(f"{base}/cancel-refund", headers=lead)
    assert refund.status_code == 201 and refund.json()["kind"] == "REFUND_CAPTURED"
    ext = client.post(f"{base}/extend", json={"extra_attempts": 2, "note": "last chance"}, headers=lead)
    assert ext.status_code == 200 and ext.json() == {"attempts_allowed": 5}
    again = client.post(f"{base}/extend", json={"extra_attempts": 1}, headers=lead)
    assert again.status_code == 409 and again.json()["error"]["code"] == "PROJECT_STATE"
    assert client.get(f"{base}/failure-options", headers=lead).json()["open"] is False


def test_an_override_over_http_needs_every_sponsor(client, w, db):
    _, ravi_user = sponsor(w, "ravi")
    sub, rows, _ = failed_world(w)
    db.commit()
    url = f"/api/submissions/{sub.id}/override"
    first = client.post(url, json={"decision": "APPROVE", "note": "fine by me"}, headers=hdr(lead_user(w)))
    assert first.status_code == 200 and first.json() == {"applied": False, "approved": 1, "needed": 2}
    second = client.post(url, json={"decision": "APPROVE"}, headers=hdr(ravi_user))
    assert second.json() == {"applied": True, "project_state": "PAYOUT_READY"}
    shown = client.get(f"/api/submissions/{sub.id}", headers=hdr(lead_user(w))).json()
    assert shown["state"] == "OVERRIDDEN" and shown["report"]["overall"] == "VERIFIED" and shown["report"]["details"]["override"]["approved_by"]
    ledger = client.get(f"/api/projects/{w.project.id}/ledger").json()                          # the public ledger shows the votes
    assert any(r["type"] == "APPROVAL" and r["meta"].get("kind") == fd.KIND_OVERRIDE for r in ledger["rows"])


# ---- gaps found by the mutation check ----

def test_the_extension_memo_records_the_new_total(w):
    sub, rows, _ = failed_world(w)
    fd.extend(w.db, sub, w.lead, 2, None)
    memo = [e for e in w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "APPROVAL")) if e.meta_json.get("kind") == fd.KIND_EXTEND][0]
    assert memo.meta_json["attempts_allowed"] == 5 and memo.meta_json["submission_id"] == sub.id


def test_a_vote_on_an_earlier_failed_submission_does_not_count_for_a_later_one(w):
    from app.services import ledger
    sub, rows, _ = failed_world(w)
    ledger.append(w.db, w.project.id, "APPROVAL", actor="user:1", ref_type="submission", ref_id=sub.id + 100,
                  meta={"kind": fd.KIND_OVERRIDE, "submission_id": sub.id + 100, "member_id": w.lead.id, "decision": "APPROVE", "note": None})
    assert fd.override_votes(w.db, sub, w.project.id) == {}
    assert fd.options(w.db, sub, w.project.id)["override"]["approved"] == 0
    assert fd.vote_override(w.db, sub, w.lead, "REJECT", None) == {"applied": False, "approved": 0, "needed": 1}


def test_the_options_come_from_the_submissions_own_project(client, w, db):
    from app.models import BRD
    from tests.test_submissions import content
    other = World(db, tag="b")
    other.project.state = "IN_PROGRESS"
    db.get(BRD, other.contract.brd_id).content_json = content()
    person(other, "SPONSOR", "zed")
    person(other, "SPONSOR", "yan")
    sub, rows, _ = failed_world(other)
    db.commit()
    assert other.project.id != w.project.id
    got = client.get(f"/api/submissions/{sub.id}/failure-options", headers=hdr(lead_user(other))).json()
    assert got["override"]["needed"] == 3 and [s["name"] for s in got["override"]["sponsors"]][1:] == ["zed", "yan"]
