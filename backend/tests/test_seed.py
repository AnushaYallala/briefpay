"""The demo seed (T-52): the data must be genuine, consistent and safe, because the demo and the video stand on it."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models import (AutoCheck, BRD, Campaign, Contract, GuardianReview, Job, LedgerEntry, MoneyPlan, MoneyPlanStep, Pledge, Project,
                        Submission, User, VerificationReport)
from app.services import ledger, ledger_views, plan_builder as pb, plan_lifecycle as lc, reconcile, seed_demo as sd
from app.services.brd_render import content_hash
from app.services.verify_judge import report_sha
from tests.factories import NOW, FakeReader
from tests.test_plans_api import hdr

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seed.py"


@pytest.fixture()
def seeded(db):
    out = sd.seed_demo(db, now=NOW)
    db.commit()
    return out


def project(db, pid):
    return db.get(Project, pid)


def types(db, pid):
    return [e.type for e in db.scalars(select(LedgerEntry).where(LedgerEntry.project_id == pid).order_by(LedgerEntry.seq))]


# =============================== the two stories ===============================

def test_the_two_projects_are_in_the_states_the_demo_needs(db, seeded):
    a, b = project(db, seeded["failed_round_project_id"]), project(db, seeded["payout_ready_project_id"])
    assert (a.title, a.state) == (sd.TITLE_A, "CAMPAIGN_FAILED") and (b.title, b.state) == (sd.TITLE_B, "PAYOUT_READY")
    assert seeded["login_emails"]["lakshmi"] == "lakshmi@velugu.example.com"


def test_round_one_failed_with_the_holds_released_and_nothing_charged(db, seeded):
    a = project(db, seeded["failed_round_project_id"])
    c = db.scalars(select(Campaign).where(Campaign.project_id == a.id)).one()
    assert (c.number, c.state, c.fail_reason, c.goal_cents) == (1, "FAILED", "DEADLINE_MISSED", 40000)
    pledges = list(db.scalars(select(Pledge).where(Pledge.project_id == a.id).order_by(Pledge.id)))
    assert [(p.display_name, p.amount_cents, p.status, p.captured_cents) for p in pledges] == [("Lakshmi", 15000, "VOIDED", 0), ("Ravi", 10000, "VOIDED", 0), ("Meena", 5000, "VOIDED", 0)]
    assert sum(p.amount_cents for p in pledges) == 30000 and ledger.pool_balance(db, a.id) == 0
    plan = db.scalars(select(MoneyPlan).where(MoneyPlan.project_id == a.id)).one()
    review = db.scalars(select(GuardianReview).where(GuardianReview.plan_id == plan.id)).one()
    assert (plan.kind, plan.state, review.decision, plan.release_policy) == ("RELEASE_HOLDS", "DONE", "ALLOW", "AUTO_ON_ALLOW")
    assert all(r["status"] != "FAIL" for r in review.rule_results_json)
    t = types(db, a.id)
    assert t.count("PLEDGE_AUTHORIZED") == 3 and t.count("PLEDGE_VOIDED") == 3 and t.count("PLEDGE_CAPTURED") == 0 and "PLAN_EXECUTED" in t


def test_the_build_phase_project_is_funded_and_verified_after_one_rejection(db, seeded):
    b = project(db, seeded["payout_ready_project_id"])
    c = db.scalars(select(Campaign).where(Campaign.project_id == b.id)).one()
    assert (c.state, ledger.pool_balance(db, b.id)) == ("CAPTURED", 40000)
    assert sorted((p.amount_cents, p.status, p.captured_cents) for p in db.scalars(select(Pledge).where(Pledge.project_id == b.id))) == [
        (10000, "CAPTURED", 10000), (15000, "CAPTURED", 15000), (15000, "CAPTURED", 15000)]
    contract = db.scalars(select(Contract).where(Contract.project_id == b.id)).one()
    assert contract.signed_at and contract.effective_at and contract.amount_cents == 40000 and contract.conditional
    assert contract.freelancer_paypal_email == "arjun-sandbox@velugu.example.com"
    subs = list(db.scalars(select(Submission).order_by(Submission.attempt_no)))
    assert [(s.attempt_no, s.state) for s in subs] == [(1, "NEEDS_CHANGES"), (2, "VERIFIED")]
    reports = [db.scalars(select(VerificationReport).where(VerificationReport.submission_id == s.id)).one() for s in subs]
    assert [r.overall for r in reports] == ["NEEDS_CHANGES", "VERIFIED"] and reports[1].must_pass_pct == 100
    assert "REQ-006" in reports[0].summary and "contact page has no form" in str(reports[0].verdicts_json)
    for r in reports:
        assert r.sha256 == report_sha(r.verdicts_json, r.overall, r.must_pass_pct, r.should_pass_pct, r.summary)


def test_the_brd_is_real_nine_requirements_locked_and_hashed(db, seeded):
    brd = db.scalars(select(BRD).where(BRD.project_id == seeded["payout_ready_project_id"])).one()
    reqs = brd.content_json["requirements"]
    assert (brd.status, len(reqs), brd.version) == ("APPROVED", 9, 1) and brd.locked_at
    assert [r["priority"] for r in reqs] == ["MUST"] * 6 + ["SHOULD"] * 3
    assert (reqs[5]["code"], reqs[5]["title"]) == ("REQ-006", "Enquiry form")
    from app.models import ProjectMember
    names = {m.id: db.get(User, m.user_id).display_name for m in db.scalars(select(ProjectMember).where(ProjectMember.project_id == brd.project_id))}
    assert sorted(names[i] for i in reqs[5]["requested_by"]) == ["Lakshmi", "Meena"]            # who asked for the form is kept (traceability)
    assert all(r["requested_by"] and r["acceptance_criteria"] for r in reqs)
    from app.schemas.brd import BRDContent
    assert brd.sha256 == content_hash(BRDContent.model_validate(brd.content_json))
    contract = db.scalars(select(Contract).where(Contract.project_id == brd.project_id)).one()
    assert contract.brd_sha256 == brd.sha256


def test_failed_attempt_one_has_the_failing_enquiry_form_and_attempt_two_is_clean(db, seeded):
    s1, s2 = db.scalars(select(Submission).order_by(Submission.attempt_no)).all()
    failing = [(c.check_type, c.requirement_code) for c in db.scalars(select(AutoCheck).where(AutoCheck.submission_id == s1.id, AutoCheck.result == "FAIL"))]
    assert failing == [("PAGE_CONTAINS", "REQ-006")]
    assert not list(db.scalars(select(AutoCheck).where(AutoCheck.submission_id == s2.id, AutoCheck.result != "PASS")))
    assert s1.commit_sha != s2.commit_sha


# =============================== consistency and safety ===============================

def test_every_money_invariant_holds_on_the_seeded_data(db, seeded):
    rep = reconcile.report(db, reader=FakeReader(db, balance=10 ** 9))
    assert rep["ok"] is True, [c for c in rep["checks"] if c["status"] != "PASS"]
    assert [c["status"] for c in rep["checks"]] == ["PASS"] * 8


def test_the_ledgers_read_like_a_story_and_are_gapless(db, seeded):
    for pid in (seeded["failed_round_project_id"], seeded["payout_ready_project_id"]):
        seqs = [e.seq for e in db.scalars(select(LedgerEntry).where(LedgerEntry.project_id == pid).order_by(LedgerEntry.seq))]
        assert seqs == list(range(1, len(seqs) + 1))
        t = types(db, pid)
        assert t[:2] == ["STATE_CHANGE", "STATE_CHANGE"] and "BRD_LOCKED" in t and "CONTRACT_SIGNED" in t and t.count("APPROVAL") >= 3


def test_the_public_ledger_shows_no_email_addresses(db, seeded):
    for pid in (seeded["failed_round_project_id"], seeded["payout_ready_project_id"]):
        assert "@" not in str(ledger_views.ledger_rows(db, pid, public=True)["rows"])


def test_nothing_is_left_to_run_against_paypal(db, seeded):
    assert db.query(Job).filter(Job.state.in_(("QUEUED", "RUNNING"))).count() == 0
    assert all(j.result_json == {"seeded": True} for j in db.query(Job).filter(Job.type == "EXECUTE_PLAN"))
    for p in db.scalars(select(Pledge)):
        assert p.paypal_order_id.startswith("SEED-") and p.paypal_authorization_id.startswith("SEED-") and (p.paypal_capture_id or "SEED-").startswith("SEED-")
    assert all(s.paypal_ref.startswith("SEED-") for s in db.scalars(select(MoneyPlanStep)))


def test_only_fictional_reserved_addresses_are_used(db, seeded):
    emails = {u.email for u in db.scalars(select(User))} | {c.freelancer_paypal_email for c in db.scalars(select(Contract))}
    assert emails and all(e.endswith("@velugu.example.com") for e in emails)
    assert sd.DEFAULT_SITE.endswith(".example.com")


def test_the_payout_can_now_be_built_and_the_guardian_waits_for_a_human(db, seeded):
    b = project(db, seeded["payout_ready_project_id"])
    plan = pb.save_proposed(db, pb.build_freelancer_payout(db, b.id), proposed_by=f"user:{b.lead_user_id}")
    review = lc.review_plan(db, plan, reader=FakeReader(db, balance=10 ** 9), now=NOW)
    assert (plan.state, review.decision, plan.release_policy) == ("REVIEWED", "ALLOW", "HUMAN")
    steps = list(db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == plan.id)))
    assert [(s.op, s.amount_cents, s.receiver_email) for s in steps] == [("PAYOUT_ITEM", 40000, "arjun-sandbox@velugu.example.com")]
    assert [r["id"] for r in review.rule_results_json if r["status"] == "FAIL"] == []


def test_a_seeded_person_can_log_in_and_see_their_project(client, db, seeded):
    token = client.post("/api/auth/login", json={"email": "lakshmi@velugu.example.com", "display_name": "Lakshmi"}).json()
    assert token["user"]["email"] == "lakshmi@velugu.example.com"
    headers = {"Authorization": f"Bearer {token['token']}"}
    got = client.get("/api/projects", headers=headers).json()
    assert {p["title"] for p in (got["projects"] if isinstance(got, dict) else got)} == {sd.TITLE_A, sd.TITLE_B}
    ledger_rows = client.get(f"/api/projects/{seeded['payout_ready_project_id']}/ledger", headers=headers).json()
    assert ledger_rows["totals"]["pool_balance_cents"] == 40000


# =============================== running it twice, switches, the script ===============================

def test_running_the_seed_twice_changes_nothing(db, seeded):
    counts = {m: db.query(m).count() for m in (User, Project, Pledge, LedgerEntry, MoneyPlan, Submission, Job)}
    again = sd.seed_demo(db, now=NOW)
    assert again["already_seeded"] is True and again["projects"] == [seeded["failed_round_project_id"], seeded["payout_ready_project_id"]]
    assert {m: db.query(m).count() for m in counts} == counts


def test_the_seed_refuses_to_run_outside_demo_mode(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    with pytest.raises(sd.SeedError):
        sd.seed_demo(db, now=NOW)
    assert db.query(User).count() == 0 and db.query(Project).count() == 0


def test_the_real_repo_site_and_commits_are_used_when_given(db):
    out = sd.seed_demo(db, now=NOW, repo_url="https://github.com/real/site", site_url="https://real.example.test", commits=("a" * 40, "b" * 40))
    subs = db.scalars(select(Submission).order_by(Submission.attempt_no)).all()
    assert [(s.repo_url, s.deployed_url, s.commit_sha) for s in subs] == [("https://github.com/real/site", "https://real.example.test", "a" * 40),
                                                                         ("https://github.com/real/site", "https://real.example.test", "b" * 40)]
    assert out["already_seeded"] is False


def script():
    spec = importlib.util.spec_from_file_location("seed_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_command_line_script_seeds_commits_and_reports(db, monkeypatch):
    mod = script()
    monkeypatch.setattr(mod, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    lines = []
    assert mod.main(["--commit-1", "c" * 40, "--commit-2", "d" * 40], out=lines.append) == 0
    assert lines[0] == "Seeded." and "payout_ready_project_id" in lines[1]
    assert db.query(Project).count() == 2
    assert [s.commit_sha for s in db.query(Submission).order_by(Submission.attempt_no)] == ["c" * 40, "d" * 40]       # --commit-1 is attempt 1
    again = []
    assert mod.main([], out=again.append) == 0 and again[0].startswith("Already seeded")
    assert db.query(Project).count() == 2


def test_the_script_explains_a_refusal_and_an_unmigrated_database(db, monkeypatch):
    mod = script()
    monkeypatch.setattr(mod, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    lines = []
    assert mod.main([], out=lines.append) == 1 and "DEMO_MODE" in lines[0]
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    from sqlalchemy import create_engine
    empty = sessionmaker(bind=create_engine("sqlite://"), expire_on_commit=False)       # no tables at all
    monkeypatch.setattr(mod, "SessionLocal", empty)
    lines = []
    assert mod.main([], out=lines.append) == 2 and "alembic upgrade head" in lines[0]


def test_the_real_sandbox_email_for_the_payout_can_be_given(db):
    out = sd.seed_demo(db, now=NOW, freelancer_paypal_email="  Real.Arjun@Sandbox.Example.com ")
    assert out["freelancer_paypal_email"] == "real.arjun@sandbox.example.com"
    assert {c.freelancer_paypal_email for c in db.query(Contract)} == {"real.arjun@sandbox.example.com"}
    b = db.get(Project, out["payout_ready_project_id"])
    plan = pb.save_proposed(db, pb.build_freelancer_payout(db, b.id), proposed_by=f"user:{b.lead_user_id}")
    assert [s.receiver_email for s in db.scalars(select(MoneyPlanStep).where(MoneyPlanStep.plan_id == plan.id))] == ["real.arjun@sandbox.example.com"]


def test_the_script_passes_the_paypal_email_on(db, monkeypatch):
    mod = script()
    monkeypatch.setattr(mod, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    assert mod.main(["--paypal-email", "me@sandbox.example.com"], out=lambda *_: None) == 0
    assert {c.freelancer_paypal_email for c in db.query(Contract)} == {"me@sandbox.example.com"}
