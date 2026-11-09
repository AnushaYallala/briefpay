"""Ledger grid, money box, AI audit trail (T-50/T-51 back end) and the reconciliation report I-1 ... I-8."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.main import app
from app.models import AgentRun, LedgerEntry, MoneyPlan, MoneyPlanStep, PayoutItem, Pledge, User
from app.services import ledger, paypal_io, reconcile
from app.services import ledger_views as lv
from app.services.money_executor import execute
from tests.factories import GOAL, NOW, FakeReader, FakeWriter, World
from tests.test_money_executor import approved_capture, approved_payout, approved_release, confirm_all, steps_of
from tests.test_plans_api import hdr, lead_user, person


@pytest.fixture()
def w(db):
    return World(db)


def funded(w):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    w.capture_all()
    w.db.commit()


def raw_row(w, seq, type, amount, bucket=None, **kw):
    """Plant a row the way a bug would: straight into the table, past LedgerService's checks."""
    e = LedgerEntry(project_id=w.project.id, seq=seq, bucket=bucket or ("POOL" if amount else "NONE"), type=type,
                    amount_cents=amount, actor="system", meta_json={}, **kw)
    w.db.add(e)
    w.db.flush()
    return e


def next_seq(w):
    return (w.db.query(LedgerEntry).filter_by(project_id=w.project.id).count()) + 1


def status_of(rep, cid):
    return next(c for c in rep["checks"] if c["id"] == cid)


# =============================== ledger rows ===============================

def test_rows_carry_running_balance_totals_chips_and_names(w):
    plan = approved_payout(w)                 # funds the project itself
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    confirm_all(w, plan)
    out = lv.ledger_rows(w.db, w.project.id, public=False)
    rows = out["rows"]
    assert [r["seq"] for r in rows] == list(range(1, len(rows) + 1))
    captured = [r for r in rows if r["type"] == "PLEDGE_CAPTURED"]
    assert [r["running_balance_cents"] for r in captured] == [15000, 30000, 40000] and {r["status"] for r in captured} == {"Captured"}
    paid = next(r for r in rows if r["type"] == "PAYOUT_SENT")
    assert paid["amount_cents"] == -GOAL and paid["running_balance_cents"] == 0 and paid["status"] == "Paid"
    assert paid["counterparty"] == "Arjun" and paid["actor_name"] == "PayPal" and paid["paypal_ref"]
    assert out["totals"] == {"pool_in_cents": GOAL, "pool_out_cents": -GOAL, "pool_balance_cents": 0, "rows": len(rows)}
    approval = next(r for r in rows if r["type"] == "APPROVAL")
    assert approval["actor_name"] == "Lakshmi" and approval["status"] is None and approval["running_balance_cents"] == GOAL


def test_a_capture_row_names_the_pledger_and_carries_the_capture_id(w):
    plan = approved_capture(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    confirm_all(w, plan)
    row = next(r for r in lv.ledger_rows(w.db, w.project.id, public=True)["rows"] if r["type"] == "PLEDGE_CAPTURED")
    assert row["counterparty"] == "P1" and row["paypal_ref"] == steps_of(w, plan)[0].paypal_ref


def test_the_public_view_never_shows_an_email_but_members_see_the_row_as_written(w):
    ledger.append(w.db, w.project.id, "APPROVAL", actor="system",
                  meta={"comment": "ask arjun@sandbox.com, or x.y+z@mail.co.in", "payer_email": "p@x.com",
                        "nested": [{"receiver_email": "r@x.com", "note": "ok"}]})
    public = lv.ledger_rows(w.db, w.project.id, public=True)["rows"][-1]["meta"]
    assert public == {"comment": "ask [hidden], or [hidden]", "nested": [{"note": "ok"}]}
    assert "@" not in str(public)
    assert lv.ledger_rows(w.db, w.project.id, public=False)["rows"][-1]["meta"]["payer_email"] == "p@x.com"


def test_ledger_endpoint_is_public_but_members_get_the_full_view(client, w):
    funded(w)
    ledger.append(w.db, w.project.id, "APPROVAL", actor="system", meta={"comment": "mail me@x.com"})
    w.db.commit()
    anon = client.get(f"/api/projects/{w.project.id}/ledger").json()
    assert anon["public"] is True and anon["rows"][-1]["meta"]["comment"] == "mail [hidden]"
    outsider = person(World(w.db, tag="o"), "LEAD", "outsider")
    assert client.get(f"/api/projects/{w.project.id}/ledger", headers=hdr(outsider)).json()["public"] is True
    member = client.get(f"/api/projects/{w.project.id}/ledger", headers=hdr(lead_user(w))).json()
    assert member["public"] is False and member["rows"][-1]["meta"]["comment"] == "mail me@x.com"
    assert member["totals"]["pool_balance_cents"] == GOAL
    assert client.get("/api/projects/9999/ledger").status_code == 404
    assert client.get(f"/api/projects/{w.project.id}/ledger", headers={"Authorization": "Bearer junk"}).status_code == 401


# =============================== money box ===============================

def test_money_box_shows_pool_holds_and_the_next_honor_deadline(w):
    w.pledge(15000, honor_hours=60)
    w.pledge(10000, honor_hours=30)
    w.pledge(5000, honor_hours=-200)          # its honor period is over: not "next"
    w.pledge(7000, status="VOIDED")           # not held any more
    out = lv.money_summary(w.db, w.project.id, now=NOW)
    assert out["pool_balance_cents"] == 0      # holds are not money (I-8)
    assert out["holds"]["count"] == 3 and out["holds"]["total_cents"] == 30000
    assert out["next_honor_deadline"] == (NOW + timedelta(hours=30)).isoformat()
    assert out["campaign"]["state"] == "OPEN" and out["campaign"]["goal_cents"] == GOAL
    assert out["contract_amount_cents"] == GOAL and out["alerts"] == [] and out["unclaimed_payouts"] == 0


def test_money_box_lists_open_plans_alerts_and_unclaimed_payouts(w):
    plan = approved_payout(w)                 # funds the project itself
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    item = w.db.scalars(select(PayoutItem)).first()
    item.status = "UNCLAIMED"
    ledger.append(w.db, w.project.id, "GUARDIAN_DECISION", actor="agent:guardian",
                  meta={"reconciliation": "RECONCILIATION_MISMATCH", "expected_cents": 1, "paypal_cents": 2})
    out = lv.money_summary(w.db, w.project.id, now=NOW)
    assert out["pool_balance_cents"] == GOAL and out["holds"]["count"] == 0 and out["next_honor_deadline"] is None
    assert out["open_plans"] == [{"id": plan.id, "kind": "FREELANCER_PAYOUT", "state": "EXECUTING"}]
    assert out["unclaimed_payouts"] == 1
    assert len(out["alerts"]) == 1 and out["alerts"][0]["meta"]["paypal_cents"] == 2
    other = World(w.db, tag="b")
    assert lv.money_summary(w.db, other.project.id, now=NOW)["unclaimed_payouts"] == 0  # other projects' payouts don't leak


def test_money_endpoint_is_for_members_only(client, w):
    funded(w)
    assert client.get(f"/api/projects/{w.project.id}/money").status_code == 401
    outsider = person(World(w.db, tag="o"), "LEAD", "outsider")
    assert client.get(f"/api/projects/{w.project.id}/money", headers=hdr(outsider)).status_code == 403
    r = client.get(f"/api/projects/{w.project.id}/money", headers=hdr(lead_user(w)))
    assert r.status_code == 200 and r.json()["pool_balance_cents"] == GOAL
    assert client.get("/api/projects/9999/money", headers=hdr(lead_user(w))).status_code == 404


# =============================== AI audit trail ===============================

def agent_run(w, agent, project_id=None, status="OK"):
    r = AgentRun(project_id=project_id or w.project.id, agent=agent, provider="replay", model="m", prompt_version="v1",
                 input_hash="h" * 64, latency_ms=12, status=status, output_json={"ok": True})
    w.db.add(r)
    w.db.flush()
    return r


def test_agent_runs_are_newest_first_filterable_and_scoped_to_the_project(client, w):
    a = agent_run(w, "BA_SCORE")
    b = agent_run(w, "GUARDIAN_LLM", status="SCHEMA_INVALID")
    other = World(w.db, tag="b")
    agent_run(w, "BA_SCORE", project_id=other.project.id)
    w.db.commit()
    rows = lv.agent_runs(w.db, w.project.id)["rows"]
    assert [r["id"] for r in rows] == [b.id, a.id] and rows[0]["status"] == "SCHEMA_INVALID" and rows[1]["output"] == {"ok": True}
    assert [r["id"] for r in lv.agent_runs(w.db, w.project.id, agent="BA_SCORE")["rows"]] == [a.id]
    assert len(lv.agent_runs(w.db, w.project.id, limit=1)["rows"]) == 1
    assert len(lv.agent_runs(w.db, w.project.id, limit=10**6)["rows"]) == 2   # clamped, not an error
    url = f"/api/projects/{w.project.id}/agent-runs"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=hdr(person(other, "LEAD", "outsider"))).status_code == 403
    assert [r["id"] for r in client.get(url + "?agent=GUARDIAN_LLM", headers=hdr(lead_user(w))).json()["rows"]] == [b.id]
    assert client.get(url + "?limit=0", headers=hdr(lead_user(w))).status_code == 422


# =============================== reconciliation ===============================

def test_a_full_capture_then_payout_run_passes_every_invariant(w):
    plan = approved_capture(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    confirm_all(w, plan)
    w.project.state = "PAYOUT_READY"
    w.verified_report()
    payout = approved_payout_after_capture(w)
    execute(w.db, payout.id, FakeWriter(), now=NOW)
    confirm_all(w, payout)
    rep = reconcile.report(w.db, reader=FakeReader(w.db))
    assert rep["ok"] is True, [c for c in rep["checks"] if c["status"] != "PASS"]
    assert [c["status"] for c in rep["checks"]] == ["PASS"] * 8


def approved_payout_after_capture(w):
    from app.services import plan_builder as pb
    from app.services import plan_lifecycle as lc
    from tests.test_money_executor import lead, reviewed
    plan, review = reviewed(w, pb.build_freelancer_payout(w.db, w.project.id), by=lead(w))
    lc.approve_plan(w.db, plan, approver=lead(w), plan_hash=plan.plan_hash, guardian_review_id=review.id)
    return plan


def test_a_release_run_passes_and_a_hold_left_behind_fails_i6(w):
    plan = approved_release(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    confirm_all(w, plan)
    assert reconcile.report(w.db, reader=FakeReader(w.db))["ok"] is True
    p = w.db.scalars(select(Pledge)).first()
    p.status = "AUTHORIZED"
    rep = reconcile.report(w.db, reader=FakeReader(w.db))
    assert rep["ok"] is False and status_of(rep, "I-6")["status"] == "FAIL"
    raw_row(w, next_seq(w), "PLEDGE_CAPTURED", 1, ref_type="pledge", ref_id=str(p.id))
    assert any("captured" in x["why"] for x in status_of(reconcile.report(w.db), "I-6")["problems"])


def test_i1_fails_when_the_pool_disagrees_with_the_pledges_or_goes_negative(w):
    funded(w)
    assert status_of(reconcile.report(w.db), "I-1")["status"] == "PASS"
    w.db.scalars(select(Pledge)).first().captured_cents -= 1
    assert status_of(reconcile.report(w.db), "I-1")["status"] == "FAIL"
    w2 = World(w.db, tag="n")
    raw_row(w2, 1, "REFUND", -5)
    probs = status_of(reconcile.report(w.db, project_id=w2.project.id), "I-1")["problems"]
    assert any("negative" in x["why"] for x in probs)


def test_i2_fails_on_an_illegal_pool_movement(w):
    funded(w)
    raw_row(w, next_seq(w), "STATE_CHANGE", 100)          # a memo type carrying money into POOL
    assert status_of(reconcile.report(w.db), "I-2")["status"] == "FAIL"


def test_i2_fails_on_money_outside_the_pool_and_on_unknown_types(w):
    raw_row(w, 1, "PLEDGE_CAPTURED", 100, bucket="NONE")
    raw_row(w, 2, "MYSTERY", 0)
    probs = status_of(reconcile.report(w.db), "I-2")["problems"]
    assert len(probs) == 2


def test_i3_fails_when_captures_do_not_add_up_to_the_goal_or_exceed_a_hold(w):
    plan = approved_capture(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    confirm_all(w, plan)
    assert status_of(reconcile.report(w.db), "I-3")["status"] == "PASS"
    w.campaign.goal_cents += 1
    assert status_of(reconcile.report(w.db), "I-3")["status"] == "FAIL"
    w.campaign.goal_cents -= 1
    s = steps_of(w, plan)[0]
    w.db.get(Pledge, s.target_id).amount_cents = s.amount_cents - 1
    assert any("larger" in x["why"] for x in status_of(reconcile.report(w.db), "I-3")["problems"])


def test_i4_fails_on_a_gap_in_the_sequence(w):
    raw_row(w, 1, "STATE_CHANGE", 0)
    raw_row(w, 3, "STATE_CHANGE", 0)
    assert status_of(reconcile.report(w.db), "I-4")["status"] == "FAIL"


def test_i5_fails_on_a_double_capture_or_a_capture_plus_void(w):
    p = w.pledge(15000)
    raw_row(w, 1, "PLEDGE_CAPTURED", 15000, ref_type="pledge", ref_id=str(p.id))
    assert status_of(reconcile.report(w.db), "I-5")["status"] == "PASS"
    raw_row(w, 2, "PLEDGE_VOIDED", 0, ref_type="pledge", ref_id=str(p.id))
    assert status_of(reconcile.report(w.db), "I-5")["problems"][0]["why"] == "both captured and released"
    raw_row(w, 3, "PLEDGE_CAPTURED", 15000, ref_type="pledge", ref_id=str(p.id))
    assert any("2 times" in x["why"] for x in status_of(reconcile.report(w.db), "I-5")["problems"])


def test_i7_compares_all_pools_with_the_paypal_balance(w):
    funded(w)
    assert status_of(reconcile.report(w.db, reader=FakeReader(w.db, balance=GOAL)), "I-7")["status"] == "PASS"
    assert status_of(reconcile.report(w.db, reader=FakeReader(w.db, balance=GOAL - 1)), "I-7")["status"] == "FAIL"
    assert status_of(reconcile.report(w.db, reader=FakeReader(w.db, down=True)), "I-7")["status"] == "NOT_CHECKED"
    assert status_of(reconcile.report(w.db, reader=None), "I-7")["status"] == "NOT_CHECKED"
    single = reconcile.report(w.db, reader=FakeReader(w.db, balance=0), project_id=w.project.id)
    assert status_of(single, "I-7")["status"] == "NOT_CHECKED" and single["ok"] is True  # not checked is not a failure


def test_i8_fails_when_a_hold_row_carries_money(w):
    raw_row(w, 1, "PLEDGE_AUTHORIZED", 0)
    assert status_of(reconcile.report(w.db), "I-8")["status"] == "PASS"
    raw_row(w, 2, "PLEDGE_AUTHORIZED", 15000)
    assert status_of(reconcile.report(w.db), "I-8")["status"] == "FAIL"


def test_reconcile_endpoint_is_demo_only_and_uses_the_configured_reader(client, w, monkeypatch):
    funded(w)
    app.dependency_overrides[paypal_io.get_reader] = lambda: FakeReader(w.db, balance=1)
    try:
        u = lead_user(w)
        assert client.get("/api/admin/reconcile").status_code == 401
        rep = client.get("/api/admin/reconcile", headers=hdr(u)).json()
        assert rep["ok"] is False and status_of(rep, "I-7")["status"] == "FAIL" and rep["projects"] == 1
        assert client.get(f"/api/admin/reconcile?project_id={w.project.id}", headers=hdr(u)).json()["ok"] is True
        monkeypatch.setattr(get_settings(), "demo_mode", False)
        r = client.get("/api/admin/reconcile", headers=hdr(u))
        assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.pop(paypal_io.get_reader, None)
