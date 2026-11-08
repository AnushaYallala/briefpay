from app.models import Base, Campaign, LedgerEntry, Pledge, User

SPEC_TABLES = {
    "users", "projects", "project_members", "transcripts", "ba_sessions", "ba_questions",
    "ba_answers", "ba_scores", "brds", "brd_requirements", "brd_approvals", "contracts",
    "campaigns", "pledges", "strategist_reports", "submissions", "auto_checks",
    "verification_questions", "images", "evidence", "verification_reports", "money_plans",
    "money_plan_steps", "guardian_reviews", "plan_approvals", "payout_batches", "payout_items",
    "refunds", "ledger_entries", "webhook_events", "jobs", "agent_runs",
}


def test_all_spec_tables_exist():
    assert set(Base.metadata.tables) == SPEC_TABLES


def test_no_bond_or_bonus_tables():  # D-020
    assert "bonds" not in Base.metadata.tables


def test_roundtrip_money_is_integer_cents(db):
    u = User(email="a@b.c", display_name="A")
    db.add(u)
    db.commit()
    assert u.id == 1
    cols = Pledge.__table__.c
    for name in ("amount_cents", "captured_cents", "refunded_cents"):
        assert "INT" in str(cols[name].type).upper()
    assert "goal_cents" in Campaign.__table__.c
    assert {c.name for c in LedgerEntry.__table__.c} >= {"seq", "bucket", "amount_cents"}
