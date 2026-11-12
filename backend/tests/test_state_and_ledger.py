from datetime import datetime, timedelta, timezone
from itertools import product

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import Campaign, LedgerEntry, Project, ProjectMember, User
from app.services import ledger
from app.services.state_machines import (
    CAMPAIGN_TRANSITIONS,
    PROJECT_TRANSITIONS,
    CampaignService,
    IllegalTransition,
    ProjectService,
)


@pytest.fixture()
def project(db):
    u = User(email="lakshmi@example.com", display_name="Lakshmi")
    db.add(u)
    db.flush()
    p = Project(title="Velugu Cove", lead_user_id=u.id)
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def campaign(db, project):
    m = ProjectMember(project_id=project.id, user_id=project.lead_user_id, role="LEAD")
    db.add(m)
    db.flush()
    c = Campaign(project_id=project.id, number=1, proposer_member_id=m.id, goal_cents=40000,
                 deadline_at=datetime.now(timezone.utc) + timedelta(hours=48))
    db.add(c)
    db.flush()
    return c


# ---------- project state machine ----------

def test_project_happy_path_to_paid(db, project):
    path = ["REQUIREMENTS", "BRD_REVIEW", "CONTRACTING", "CAMPAIGN_SETUP", "PLEDGING", "IN_PROGRESS",
            "VERIFYING", "PAYOUT_READY", "PAYOUT_PENDING", "PAID"]
    for s in path:
        ProjectService.transition(db, project, s, actor="system")
    assert project.state == "PAID"
    assert db.scalar(select(ledger.func.count()).select_from(LedgerEntry)) == len(path)


def test_project_failure_relaunch_and_resubmit_loops(db, project):
    for s in ["REQUIREMENTS", "BRD_REVIEW", "REQUIREMENTS", "BRD_REVIEW", "CONTRACTING", "CAMPAIGN_SETUP",
              "PLEDGING", "CAMPAIGN_FAILED", "CAMPAIGN_SETUP", "PLEDGING", "IN_PROGRESS", "VERIFYING",
              "IN_PROGRESS", "VERIFYING", "REFUNDING", "CANCELLED"]:
        ProjectService.transition(db, project, s, actor="system")
    assert project.state == "CANCELLED"


def test_every_illegal_project_transition_is_rejected(db, project):
    states = list(PROJECT_TRANSITIONS)
    for frm, to in product(states, states):
        if to in PROJECT_TRANSITIONS[frm]:
            continue
        project.state = frm
        with pytest.raises(IllegalTransition):
            ProjectService.transition(db, project, to, actor="system")
        assert project.state == frm  # unchanged on failure


def test_funded_states_from_v1_do_not_exist(db, project):
    assert "FUNDED" not in PROJECT_TRANSITIONS and "FUNDING" not in PROJECT_TRANSITIONS
    with pytest.raises(IllegalTransition):
        ProjectService.transition(db, project, "FUNDED", actor="system")


# ---------- campaign state machine ----------

def test_campaign_success_and_failure_paths(db, campaign):
    for s in ["OPEN", "CAPTURING", "CAPTURED"]:
        CampaignService.transition(db, campaign, s, actor="system")
    assert campaign.state == "CAPTURED"


def test_campaign_failure_needs_a_reason(db, campaign):
    CampaignService.transition(db, campaign, "OPEN", actor="system")
    with pytest.raises(IllegalTransition):
        CampaignService.transition(db, campaign, "FAILING", actor="system")
    CampaignService.transition(db, campaign, "FAILING", actor="user:1", fail_reason="LEAD_CANCEL")
    CampaignService.transition(db, campaign, "FAILED", actor="system")
    assert (campaign.state, campaign.fail_reason) == ("FAILED", "LEAD_CANCEL")


def test_every_illegal_campaign_transition_is_rejected(db, campaign):
    states = list(CAMPAIGN_TRANSITIONS)
    for frm, to in product(states, states):
        if to in CAMPAIGN_TRANSITIONS[frm]:
            continue
        campaign.state = frm
        with pytest.raises(IllegalTransition):
            CampaignService.transition(db, campaign, to, actor="system", fail_reason="LEAD_CANCEL")


def test_captured_campaign_cannot_be_voided(db, campaign):
    for s in ["OPEN", "CAPTURING", "CAPTURED"]:
        CampaignService.transition(db, campaign, s, actor="system")
    with pytest.raises(IllegalTransition):
        CampaignService.transition(db, campaign, "FAILING", actor="system", fail_reason="LEAD_CANCEL")


# ---------- ledger ----------

def test_transitions_write_state_change_rows_with_zero_amount(db, project):
    ProjectService.transition(db, project, "REQUIREMENTS", actor="user:1")
    row = db.scalar(select(LedgerEntry))
    assert (row.type, row.amount_cents, row.bucket, row.actor) == ("STATE_CHANGE", 0, "NONE", "user:1")
    assert row.meta_json["from"] == "DRAFT" and row.meta_json["to"] == "REQUIREMENTS"


def test_seq_is_gapless_per_project(db, project):
    for _ in range(5):
        ledger.append(db, project.id, "APPROVAL", actor="user:1")
    assert [e.seq for e in db.scalars(select(LedgerEntry).order_by(LedgerEntry.seq))] == [1, 2, 3, 4, 5]


def test_pool_balance_follows_capture_payout_refund(db, project):
    pid = project.id
    ledger.append(db, pid, "PLEDGE_AUTHORIZED", actor="paypal")  # a hold is not money (I-8)
    assert ledger.pool_balance(db, pid) == 0
    ledger.append(db, pid, "PLEDGE_CAPTURED", 40000, actor="paypal")
    assert ledger.pool_balance(db, pid) == 40000
    ledger.append(db, pid, "PAYOUT_SENT", -40000, actor="paypal")
    assert ledger.pool_balance(db, pid) == 0


def test_pool_can_never_go_negative(db, project):
    ledger.append(db, project.id, "PLEDGE_CAPTURED", 1000, actor="paypal")
    with pytest.raises(ledger.LedgerError):
        ledger.append(db, project.id, "PAYOUT_SENT", -1001, actor="paypal")
    with pytest.raises(ledger.LedgerError):
        ledger.append(db, project.id, "REFUND", -1001, actor="paypal")
    assert ledger.pool_balance(db, project.id) == 1000


@pytest.mark.parametrize("type_,amount", [
    ("PLEDGE_AUTHORIZED", 100),   # memo rows must be 0
    ("PLEDGE_VOIDED", -5),
    ("PLEDGE_CAPTURED", 0),       # captures must be positive
    ("PLEDGE_CAPTURED", -5),
    ("PAYOUT_SENT", 5),           # payouts must be negative
    ("REFUND", 0),
    ("BONUS_PAID", 5),            # no bonus in this product (D-020)
    ("BOND_AUTHORIZED", 0),
])
def test_ledger_rejects_bad_type_or_sign(db, project, type_, amount):
    with pytest.raises(ledger.LedgerError):
        ledger.append(db, project.id, type_, amount, actor="system")


def test_ledger_is_append_only(db, project):
    row = ledger.append(db, project.id, "APPROVAL", actor="user:1")
    db.commit()
    row.amount_cents = 999
    with pytest.raises(ledger.LedgerError):
        db.flush()
    db.rollback()
    row = db.scalar(select(LedgerEntry))
    db.delete(row)
    with pytest.raises(ledger.LedgerError):
        db.flush()
    db.rollback()

    # Raw SQL mutations are also blocked by DB-level triggers (GAP-08).
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE ledger_entries SET amount_cents = 999 WHERE id = :id"), {"id": row.id})
    db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM ledger_entries WHERE id = :id"), {"id": row.id})
    db.rollback()


def test_projects_have_independent_sequences_and_pools(db, project):
    u2 = User(email="ravi@example.com", display_name="Ravi")
    db.add(u2)
    db.flush()
    p2 = Project(title="Other", lead_user_id=u2.id)
    db.add(p2)
    db.flush()
    ledger.append(db, project.id, "PLEDGE_CAPTURED", 500, actor="paypal")
    e = ledger.append(db, p2.id, "APPROVAL", actor="user:2")
    assert e.seq == 1
    assert ledger.pool_balance(db, p2.id) == 0
    with pytest.raises(ledger.LedgerError):
        ledger.append(db, p2.id, "PAYOUT_SENT", -1, actor="paypal")  # projects never touch each other's money
