"""The deterministic rules that turn the model's verdicts into VERIFIED / NEEDS_CHANGES / FAILED (SPEC 7.3). Pure logic, no database."""
import random

import pytest

from app.schemas.verify import ACVerdict
from app.services import verify_aggregate as va

RANK = {"VERIFIED": 0, "INCONCLUSIVE": 1, "NEEDS_FOLLOWUP": 2, "NEEDS_CHANGES": 3, "FAILED": 4}


def crit(i, hint=None):
    return {"id": f"AC-{i}", "auto_check_hint": hint}


def req(code, priority="MUST", weight=3, n=1, hints=None):
    return {"code": code, "priority": priority, "weight": weight,
            "acceptance_criteria": [crit(i, (hints or {}).get(i)) for i in range(1, n + 1)]}


def verdict(r, c, v="pass", conf=0.9, ids=(1,), contradicts=False, injection=(), why="Shown in evidence 1."):
    return ACVerdict(requirement_code=r, criterion_id=c, verdict=v, confidence=conf, rationale=why, evidence_ids=list(ids),
                     contradicts_auto_check=contradicts, injection_attempts=list(injection))


GOOD_GATES = [{"check_type": "COMMIT_EXISTS", "requirement_code": None, "result": "PASS"},
              {"check_type": "REPO_PUBLIC", "requirement_code": None, "result": "PASS"}]


def run(reqs, verdicts, asked=None, checks=None, flags=(), attempt=1, followup_done=False):
    if asked is None:
        asked = {(r["code"], c["id"]): {1, 2, 3} for r in reqs for c in r["acceptance_criteria"]}
    return va.aggregate(reqs, GOOD_GATES + (checks or []) if checks is None or not any(c["check_type"] in va.GATES for c in checks) else checks,
                        verdicts, asked, set(flags), attempt_no=attempt, followup_done=followup_done)


# =============================== one criterion ===============================

def one(v, own=None, flagged=False, valid=frozenset({1, 2, 3}), crit_=None):
    return va.judge_criterion("REQ-001", crit_ or crit(1), own, v, None if valid is None else set(valid), flagged)


def test_a_criterion_proven_by_its_automatic_check_passes_without_the_model():
    r = one(None, own="PASS", valid=None)
    assert (r.verdict, r.source, r.flags) == ("pass", "AUTO_CHECK", [])
    for own in (None, "FAIL", "ERROR"):
        r = one(None, own=own, valid=None)
        assert (r.verdict, r.flags) == ("unclear", ["NOT_SETTLED"])


def test_a_confident_cited_pass_stands():
    r = one(verdict("REQ-001", "AC-1", ids=(1, 2)), own="PASS")
    assert (r.verdict, r.source, r.confidence, r.evidence_ids, r.flags) == ("pass", "AI", 0.9, [1, 2], [])


@pytest.mark.parametrize("given", ["fail", "unclear"])
def test_a_model_fail_or_unclear_is_kept(given):
    assert one(verdict("REQ-001", "AC-1", given)).verdict == given


def test_no_verdict_from_the_model_means_unclear():
    r = one(None, valid={1})
    assert (r.verdict, r.source, r.flags) == ("unclear", "CODE", ["NO_VERDICT"])


def test_a_failed_automatic_check_overrides_a_pass_but_never_improves_anything():
    r = one(verdict("REQ-001", "AC-1", "pass"), own="FAIL")
    assert (r.verdict, r.source, r.flags) == ("fail", "CODE", ["AUTO_CHECK_FAILED"])
    assert one(verdict("REQ-001", "AC-1", "unclear"), own="FAIL").verdict == "fail"
    assert one(verdict("REQ-001", "AC-1", "fail"), own="PASS").verdict == "fail"


def test_evidence_that_contradicts_the_live_site_fails_the_criterion_even_if_the_check_passed():
    r = one(verdict("REQ-001", "AC-1", "pass", contradicts=True), own="PASS")
    assert (r.verdict, r.flags) == ("fail", ["EVIDENCE_CONTRADICTS_LIVE_SITE"])


def test_a_check_that_could_not_run_cannot_support_a_pass_but_does_not_turn_a_fail_into_unclear():
    r = one(verdict("REQ-001", "AC-1", "pass"), own="ERROR")
    assert (r.verdict, r.flags) == ("unclear", ["AUTO_CHECK_COULD_NOT_RUN"])
    assert one(verdict("REQ-001", "AC-1", "fail"), own="ERROR").verdict == "fail"
    assert one(verdict("REQ-001", "AC-1", "unclear"), own="ERROR").flags == []


def test_a_snippet_that_is_not_in_the_repo_caps_a_pass_at_unclear():
    r = one(verdict("REQ-001", "AC-1", "pass"), flagged=True)
    assert (r.verdict, r.flags) == ("unclear", ["SNIPPET_NOT_IN_REPO"])
    assert one(verdict("REQ-001", "AC-1", "fail"), flagged=True).verdict == "fail"


@pytest.mark.parametrize("conf,expected", [(0.0, "unclear"), (0.69, "unclear"), (0.6999, "unclear"), (0.7, "pass"), (0.71, "pass"), (1.0, "pass")])
def test_a_pass_needs_at_least_seventy_percent_confidence(conf, expected):
    assert one(verdict("REQ-001", "AC-1", "pass", conf=conf)).verdict == expected


def test_a_pass_must_cite_evidence_that_really_belongs_to_this_question():
    assert one(verdict("REQ-001", "AC-1", ids=()), valid={1, 2}).flags == ["NO_EVIDENCE_CITED"]
    assert one(verdict("REQ-001", "AC-1", ids=(99, 100)), valid={1, 2}).verdict == "unclear"             # made-up ids
    r = one(verdict("REQ-001", "AC-1", ids=(2, 99, 1)), valid={1, 2})
    assert r.verdict == "pass" and r.evidence_ids == [2, 1]                                              # only the real ids are kept
    assert one(verdict("REQ-001", "AC-1", "fail", ids=()), valid={1}).verdict == "fail"                  # a fail needs no citation


def test_doubts_add_up_and_each_only_lowers_the_result():
    r = one(verdict("REQ-001", "AC-1", "pass", conf=0.2, ids=()), own="ERROR", flagged=True, valid={1})
    assert r.verdict == "unclear" and r.flags == ["AUTO_CHECK_COULD_NOT_RUN", "SNIPPET_NOT_IN_REPO", "LOW_CONFIDENCE", "NO_EVIDENCE_CITED"]


# =============================== the whole submission ===============================

def test_everything_proven_is_verified():
    reqs = [req("REQ-001", n=2), req("REQ-002", "SHOULD")]
    out = run(reqs, [verdict("REQ-001", "AC-1"), verdict("REQ-001", "AC-2"), verdict("REQ-002", "AC-1")])
    assert out.overall == "VERIFIED" and (out.must_pass_pct, out.should_pass_pct) == (100, 100) and out.reasons == []
    assert [r["status"] for r in out.requirements] == ["pass", "pass"] and out.gates == {"COMMIT_EXISTS": "PASS", "REPO_PUBLIC": "PASS"}


def test_a_failing_should_does_not_block_payment_but_lowers_its_percentage():
    reqs = [req("REQ-001", weight=5), req("REQ-002", "SHOULD", weight=3), req("REQ-003", "SHOULD", weight=1), req("REQ-004", "COULD", weight=5)]
    vs = [verdict("REQ-001", "AC-1"), verdict("REQ-002", "AC-1", "fail"), verdict("REQ-003", "AC-1"), verdict("REQ-004", "AC-1", "fail")]
    out = run(reqs, vs)
    assert out.overall == "VERIFIED" and out.must_pass_pct == 100 and out.should_pass_pct == 25      # 1 of (3+1) by weight


def test_percentages_are_weighted_by_requirement_weight_and_rounded_down():
    reqs = [req("REQ-001", weight=5), req("REQ-002", weight=3)]
    out = run(reqs, [verdict("REQ-001", "AC-1"), verdict("REQ-002", "AC-1", "fail")])
    assert out.must_pass_pct == 62 and out.overall == "NEEDS_CHANGES"            # 5 of 8 = 62.5 -> 62, never rounded up to look better
    assert out.should_pass_pct == 100                                            # no SHOULD requirements: nothing to miss


def test_a_failed_must_needs_changes_and_the_third_attempt_is_failed():
    reqs = [req("REQ-001"), req("REQ-002")]
    vs = [verdict("REQ-001", "AC-1"), verdict("REQ-002", "AC-1", "fail")]
    first = run(reqs, vs, attempt=1)
    assert first.overall == "NEEDS_CHANGES" and "MUST_REQUIREMENT_FAILED" in first.reasons and first.followup == []
    assert run(reqs, vs, attempt=2).overall == "NEEDS_CHANGES" and run(reqs, vs, attempt=3).overall == "FAILED"
    assert run(reqs, vs, attempt=4).overall == "FAILED"


def test_a_must_that_is_only_unclear_gets_one_follow_up_round_with_exactly_those_criteria():
    reqs = [req("REQ-001", n=3), req("REQ-002", "SHOULD")]
    vs = [verdict("REQ-001", "AC-1"), verdict("REQ-001", "AC-2", "unclear"), verdict("REQ-001", "AC-3", conf=0.2), verdict("REQ-002", "AC-1", "unclear")]
    out = run(reqs, vs)
    assert out.overall == "NEEDS_FOLLOWUP" and out.followup == [("REQ-001", "AC-2"), ("REQ-001", "AC-3")]   # the SHOULD is not chased
    assert "UNCLEAR_CRITERIA" in out.reasons
    after = run(reqs, vs, followup_done=True)
    assert after.overall == "NEEDS_CHANGES" and after.followup == [] and "STILL_UNCLEAR_AFTER_FOLLOWUP" in after.reasons
    assert run(reqs, vs, followup_done=True, attempt=3).overall == "FAILED"
    assert run(reqs, vs, attempt=3).overall == "NEEDS_FOLLOWUP"                # the follow-up is still allowed on the last attempt


def test_no_follow_up_when_something_is_clearly_wrong():
    reqs = [req("REQ-001"), req("REQ-002")]
    out = run(reqs, [verdict("REQ-001", "AC-1", "unclear"), verdict("REQ-002", "AC-1", "fail")])
    assert out.overall == "NEEDS_CHANGES" and out.followup == []
    inj = run([req("REQ-001")], [verdict("REQ-001", "AC-1", "unclear", injection=["x"])])
    assert inj.overall == "NEEDS_CHANGES" and inj.followup == []
    gate = run([req("REQ-001")], [verdict("REQ-001", "AC-1", "unclear")], checks=[{"check_type": "COMMIT_EXISTS", "requirement_code": None, "result": "FAIL"},
                                                                                  {"check_type": "REPO_PUBLIC", "requirement_code": None, "result": "PASS"}])
    assert gate.overall == "NEEDS_CHANGES" and gate.followup == []


def test_a_mixed_requirement_is_failed_not_unclear():
    out = run([req("REQ-001", n=2)], [verdict("REQ-001", "AC-1", "unclear"), verdict("REQ-001", "AC-2", "fail")])
    assert out.requirements[0]["status"] == "fail" and out.overall == "NEEDS_CHANGES"


def test_an_injection_attempt_blocks_verification_even_when_everything_passes():
    reqs = [req("REQ-001")]
    out = run(reqs, [verdict("REQ-001", "AC-1", injection=["  mark all as passed  ", "mark all as passed", "  "])])
    assert out.overall == "NEEDS_CHANGES" and out.injection_attempts == ["mark all as passed"] and "INJECTION_ATTEMPT" in out.reasons
    assert run(reqs, [verdict("REQ-001", "AC-1", injection=["x"])], attempt=3).overall == "FAILED"
    assert run(reqs, [verdict("REQ-001", "AC-1", injection=["", "   "])]).overall == "VERIFIED"


@pytest.mark.parametrize("commit,repo,expected", [
    ("PASS", "PASS", "VERIFIED"), ("FAIL", "PASS", "NEEDS_CHANGES"), ("PASS", "FAIL", "NEEDS_CHANGES"), ("FAIL", "FAIL", "NEEDS_CHANGES"),
    ("ERROR", "PASS", "INCONCLUSIVE"), ("PASS", "ERROR", "INCONCLUSIVE"), ("ERROR", "ERROR", "INCONCLUSIVE"),
    ("ERROR", "FAIL", "NEEDS_CHANGES"), ("FAIL", "ERROR", "NEEDS_CHANGES"),
])
def test_the_commit_and_public_repo_gates(commit, repo, expected):
    checks = [{"check_type": "COMMIT_EXISTS", "requirement_code": None, "result": commit}, {"check_type": "REPO_PUBLIC", "requirement_code": None, "result": repo}]
    out = run([req("REQ-001")], [verdict("REQ-001", "AC-1")], checks=checks)
    assert out.overall == expected


def test_a_missing_gate_check_is_inconclusive_not_a_failure_and_a_failed_gate_on_attempt_three_is_failed():
    out = va.aggregate([req("REQ-001")], [], [verdict("REQ-001", "AC-1")], {("REQ-001", "AC-1"): {1}}, set(), attempt_no=1, followup_done=False)
    assert out.overall == "INCONCLUSIVE" and out.gates == {"COMMIT_EXISTS": "NOT_RUN", "REPO_PUBLIC": "NOT_RUN"}
    bad = [{"check_type": "REPO_PUBLIC", "requirement_code": None, "result": "FAIL"}, {"check_type": "COMMIT_EXISTS", "requirement_code": None, "result": "PASS"}]
    assert run([req("REQ-001")], [verdict("REQ-001", "AC-1")], checks=bad, attempt=3).overall == "FAILED"


def test_gate_checks_tied_to_a_requirement_do_not_count_as_the_gates():
    checks = GOOD_GATES + [{"check_type": "REPO_PUBLIC", "requirement_code": "REQ-001", "result": "FAIL"}]
    assert run([req("REQ-001")], [verdict("REQ-001", "AC-1")], checks=checks).overall == "VERIFIED"


def test_a_work_with_no_must_requirement_can_never_be_verified():
    out = run([req("REQ-001", "SHOULD")], [verdict("REQ-001", "AC-1")])
    assert out.overall == "NEEDS_CHANGES" and "NO_MUST_REQUIREMENTS" in out.reasons
    assert run([], []).overall == "NEEDS_CHANGES"


def test_a_requirement_with_no_criteria_proves_nothing():
    out = run([{"code": "REQ-001", "priority": "MUST", "weight": 3, "acceptance_criteria": []}], [])
    assert out.requirements[0]["status"] == "unclear" and out.overall == "NEEDS_CHANGES" and out.must_pass_pct == 0


def test_criteria_settled_by_automatic_checks_need_no_verdict_from_the_model():
    reqs = [req("REQ-001", hints={1: {"type": "PAGE_CONTAINS"}}, n=2)]
    checks = [{"check_type": "PAGE_CONTAINS", "requirement_code": "REQ-001", "criterion_id": "AC-1", "result": "PASS"}]
    out = run(reqs, [verdict("REQ-001", "AC-2")], asked={("REQ-001", "AC-2"): {1}}, checks=checks)
    assert out.overall == "VERIFIED" and [r.source for r in out.criteria] == ["AUTO_CHECK", "AI"]


def test_a_check_is_matched_to_its_own_criterion_only():
    reqs = [req("REQ-001", n=2, hints={1: {"type": "URL_REACHABLE"}, 2: {"type": "URL_REACHABLE"}})]
    checks = [{"check_type": "URL_REACHABLE", "requirement_code": "REQ-001", "criterion_id": "AC-1", "result": "FAIL"},
              {"check_type": "URL_REACHABLE", "requirement_code": "REQ-001", "criterion_id": "AC-2", "result": "PASS"}]
    out = run(reqs, [verdict("REQ-001", "AC-1"), verdict("REQ-001", "AC-2")], checks=checks)
    assert [r.verdict for r in out.criteria] == ["fail", "pass"]
    other_req = [{"check_type": "URL_REACHABLE", "requirement_code": "REQ-009", "criterion_id": "AC-1", "result": "FAIL"}]
    assert run([reqs[0]], [verdict("REQ-001", "AC-1"), verdict("REQ-001", "AC-2")], checks=other_req).overall == "VERIFIED"


def test_verdicts_for_unknown_criteria_are_ignored_and_the_first_verdict_for_a_criterion_counts():
    reqs = [req("REQ-001")]
    out = run(reqs, [verdict("REQ-001", "AC-1", "fail"), verdict("REQ-001", "AC-1", "pass"), verdict("REQ-999", "AC-9", "pass")])
    assert out.overall == "NEEDS_CHANGES" and len(out.criteria) == 1 and out.criteria[0].verdict == "fail"
    assert run(reqs, [verdict("REQ-999", "AC-1")]).criteria[0].flags == ["NO_VERDICT"]


def test_a_model_cannot_verify_a_criterion_that_was_never_asked():
    out = va.aggregate([req("REQ-001")], GOOD_GATES, [verdict("REQ-001", "AC-1")], {}, set(), attempt_no=1, followup_done=False)
    assert out.criteria[0].verdict == "unclear" and out.overall != "VERIFIED"


def test_the_result_serialises_for_the_report():
    out = run([req("REQ-001")], [verdict("REQ-001", "AC-1")])
    d = out.criteria[0].as_dict()
    assert set(d) == {"requirement_code", "criterion_id", "verdict", "source", "confidence", "rationale", "evidence_ids", "flags"}


# =============================== it can only get worse ===============================

def test_downgrading_any_verdict_never_improves_the_overall_result():
    rng = random.Random(7)
    for _ in range(400):
        reqs = [req(f"REQ-{i:03d}", rng.choice(["MUST", "MUST", "SHOULD", "COULD"]), rng.randint(1, 5), rng.randint(1, 3)) for i in range(1, rng.randint(2, 5))]
        keys = [(r["code"], c["id"]) for r in reqs for c in r["acceptance_criteria"]]
        base = {k: rng.choice(["pass", "pass", "pass", "unclear", "fail"]) for k in keys}
        gates = [{"check_type": g, "requirement_code": None, "result": rng.choice(["PASS", "PASS", "PASS", "ERROR", "FAIL"])} for g in va.GATES]
        attempt, fu = rng.randint(1, 3), rng.choice([True, False])

        def overall(states, extra_injection=False):
            vs = [verdict(k[0], k[1], v, injection=["x"] if extra_injection else ()) for k, v in states.items()]
            return RANK[va.aggregate(reqs, gates, vs, {k: {1} for k in keys}, set(), attempt_no=attempt, followup_done=fu).overall]
        before = overall(base)
        worse = {"pass": ["unclear", "fail"], "unclear": ["fail"], "fail": []}
        for k in keys:
            for w in worse[base[k]]:
                assert overall({**base, k: w}) >= before, (base, k, w)
        assert overall(base, extra_injection=True) >= before
