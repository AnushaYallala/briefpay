"""Ledger vs PayPal (T-48): the 'PayPal match' column. Read-only; PayPal is a scripted fake."""
import pytest
from sqlalchemy import select

from app.main import app
from app.models import LedgerEntry, PayoutItem
from app.services import ledger_match as lm
from app.services import ledger_views, paypal_io
from app.services.guardian_rules import PayPalObject, PayPalUnavailable
from app.services.money_executor import execute
from tests.factories import FakeReader, FakeWriter, NOW, World
from tests.test_money_executor import approved_capture, approved_payout, confirm_all, steps_of
from tests.test_plans_api import hdr, lead_user, person
from tests.test_webhooks import sent_refund


@pytest.fixture()
def w(db):
    return World(db)


class Batches:
    def __init__(self, items=None, down=False):
        self.items, self.down, self.asked = items or [], down, []

    def get_payout_batch(self, batch_id):
        self.asked.append(batch_id)
        if self.down:
            raise PayPalUnavailable("down")
        return {"batch_status": "SUCCESS", "items": self.items}


def captured(w):
    plan = approved_capture(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    confirm_all(w, plan)
    rows = list(w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "PLEDGE_CAPTURED").order_by(LedgerEntry.seq)))
    return plan, rows


def run(w, reader=None, batches=None):
    return lm.match(w.db, w.project.id, reader or FakeReader(w.db), batches or Batches())


def agree(rows):
    return {r.meta_json["capture_id"]: PayPalObject("COMPLETED", r.amount_cents) for r in rows}


# =============================== captures ===============================

def test_captures_that_paypal_confirms_exactly_match(w):
    plan, rows = captured(w)
    out = run(w, FakeReader(w.db, overrides=agree(rows)))
    assert sorted(int(k) for k in out["results"]) == sorted(r.seq for r in rows)
    assert {r["status"] for r in out["results"].values()} == {"MATCH"} and out["all_match"] is True and out["counts"]["MATCH"] == 3
    first = out["results"][str(rows[0].seq)]
    assert first["paypal_ref"] == rows[0].meta_json["capture_id"] and first["paypal_cents"] == rows[0].amount_cents


@pytest.mark.parametrize("paypal,status", [
    (lambda r: PayPalObject("COMPLETED", r.amount_cents + 1), "MISMATCH"), (lambda r: PayPalObject("COMPLETED", r.amount_cents - 1), "MISMATCH"),
    (lambda r: PayPalObject("DECLINED", r.amount_cents), "MISMATCH"), (lambda r: PayPalObject("DENIED", r.amount_cents), "MISMATCH"),
    (lambda r: PayPalObject("PENDING", r.amount_cents), "PENDING"), (lambda r: PayPalObject("SOMETHING_NEW", r.amount_cents), "PENDING"),
    (lambda r: PayPalObject("REFUNDED", r.amount_cents), "MATCH"), (lambda r: PayPalObject("PARTIALLY_REFUNDED", r.amount_cents), "MATCH"),
    (lambda r: None, "NOT_FOUND"),
])
def test_each_paypal_answer_for_a_capture(w, paypal, status):
    plan, rows = captured(w)
    overrides = {r.meta_json["capture_id"]: paypal(r) for r in rows}
    out = run(w, FakeReader(w.db, overrides=overrides))
    assert {r["status"] for r in out["results"].values()} == {status}
    assert out["all_match"] is (status == "MATCH")


def test_one_bad_row_among_good_ones_is_pinpointed(w):
    plan, rows = captured(w)
    overrides = agree(rows)
    overrides[rows[1].meta_json["capture_id"]] = PayPalObject("COMPLETED", rows[1].amount_cents + 100)
    out = run(w, FakeReader(w.db, overrides=overrides))
    assert [out["results"][str(r.seq)]["status"] for r in rows] == ["MATCH", "MISMATCH", "MATCH"]
    assert out["counts"] == {"MATCH": 2, "PENDING": 0, "MISMATCH": 1, "NOT_FOUND": 0, "UNAVAILABLE": 0} and out["all_match"] is False
    detail = out["results"][str(rows[1].seq)]["detail"]
    assert str(rows[1].amount_cents + 100) in detail and str(rows[1].amount_cents) in detail          # both figures are shown


def test_when_paypal_cannot_be_asked_nothing_is_concluded(w):
    plan, rows = captured(w)
    out = run(w, FakeReader(w.db, down=True))
    assert {r["status"] for r in out["results"].values()} == {"UNAVAILABLE"} and out["all_match"] is False and out["counts"]["UNAVAILABLE"] == 3


def test_rows_that_are_not_paypal_objects_are_left_out_and_an_empty_ledger_is_not_all_match(w):
    assert run(w) == {"project_id": w.project.id, "results": {}, "counts": {k: 0 for k in lm.RESULTS}, "limited": False, "all_match": False}
    plan, rows = captured(w)
    kinds = {e.type for e in w.db.scalars(select(LedgerEntry))}
    assert {"STATE_CHANGE", "PLAN_EXECUTED", "GUARDIAN_DECISION"} & kinds                            # the project has many other rows
    assert len(run(w, FakeReader(w.db, overrides=agree(rows)))["results"]) == 3


def test_a_capture_row_without_a_recorded_paypal_id_is_skipped(w):
    w.pledge(100)
    w.capture_all()                                       # a test helper books captures without a capture_id in the memo
    assert run(w)["results"] == {}


def test_only_the_newest_rows_are_checked(w, monkeypatch):
    plan, rows = captured(w)
    monkeypatch.setattr(lm, "MAX_ROWS", 2)
    out = run(w, FakeReader(w.db, overrides=agree(rows)))
    assert out["limited"] is True and sorted(int(k) for k in out["results"]) == sorted(r.seq for r in rows)[-2:]
    monkeypatch.setattr(lm, "MAX_ROWS", 3)
    assert run(w, FakeReader(w.db, overrides=agree(rows)))["limited"] is False


def test_matching_never_writes(w):
    plan, rows = captured(w)
    before = w.db.query(LedgerEntry).count()
    run(w, FakeReader(w.db, overrides={r.meta_json["capture_id"]: PayPalObject("COMPLETED", 1) for r in rows}))
    assert w.db.query(LedgerEntry).count() == before


# =============================== refunds ===============================

def refunded(w):
    plan, steps = sent_refund(w)
    confirm_all(w, plan)
    return list(w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "REFUND").order_by(LedgerEntry.seq)))


@pytest.mark.parametrize("paypal,status", [
    (lambda r: PayPalObject("COMPLETED", -r.amount_cents), "MATCH"), (lambda r: PayPalObject("COMPLETED", -r.amount_cents + 5), "MISMATCH"),
    (lambda r: PayPalObject("FAILED", -r.amount_cents), "MISMATCH"), (lambda r: PayPalObject("CANCELLED", -r.amount_cents), "MISMATCH"),
    (lambda r: PayPalObject("PENDING", -r.amount_cents), "PENDING"), (lambda r: None, "NOT_FOUND"),
])
def test_each_paypal_answer_for_a_refund(w, paypal, status):
    rows = refunded(w)
    assert len(rows) == 3
    out = run(w, FakeReader(w.db, overrides={r.meta_json["refund_id"]: paypal(r) for r in rows}))
    assert {r["status"] for r in out["results"].values()} == {status}


# =============================== payouts ===============================

def paid(w):
    plan = approved_payout(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    item = w.db.scalars(select(PayoutItem)).one()
    row_before = w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "PAYOUT_SENT")).first()
    assert row_before is None
    confirm_all(w, plan)
    row = w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "PAYOUT_SENT")).one()
    return plan, item, row


def entry(item, status="SUCCESS", cents=None):
    return {"payout_item_id": "PI-1", "transaction_status": status, "sender_item_id": item.sender_item_id,
            "amount_cents": item.amount_cents if cents is None else cents}


@pytest.mark.parametrize("make,status", [
    (lambda i: [entry(i)], "MATCH"), (lambda i: [entry(i, "SUCCEEDED")], "MATCH"),
    (lambda i: [entry(i, cents=i.amount_cents + 1)], "MISMATCH"), (lambda i: [entry(i, "FAILED")], "MISMATCH"),
    (lambda i: [entry(i, "RETURNED")], "MISMATCH"), (lambda i: [entry(i, "BLOCKED")], "MISMATCH"),
    (lambda i: [entry(i, "PENDING")], "PENDING"), (lambda i: [entry(i, "UNCLAIMED")], "PENDING"), (lambda i: [entry(i, "HELD")], "PENDING"),
    (lambda i: [], "NOT_FOUND"), (lambda i: [{**entry(i), "sender_item_id": "someone-else"}], "NOT_FOUND"),
])
def test_each_paypal_answer_for_the_payout(w, make, status):
    plan, item, row = paid(w)
    out = run(w, batches=Batches(make(item)))
    assert out["results"][str(row.seq)]["status"] == status


def test_the_payout_batch_is_read_once_and_a_failed_lookup_is_unavailable(w):
    plan, item, row = paid(w)
    b = Batches([entry(item)])
    run(w, batches=b)
    assert len(b.asked) == 1
    out = run(w, batches=Batches(down=True))
    assert out["results"][str(row.seq)]["status"] == "UNAVAILABLE"


def test_a_payout_row_with_no_batch_of_ours_is_not_found(w):
    from app.services import ledger
    ledger.append(w.db, w.project.id, "PLEDGE_CAPTURED", 40001, actor="paypal")
    ledger.append(w.db, w.project.id, "PAYOUT_SENT", -40000, actor="paypal", meta={"plan_id": 999})
    out = run(w)
    assert out["results"][str(max(int(k) for k in out["results"]))]["status"] == "NOT_FOUND"
    ledger.append(w.db, w.project.id, "PAYOUT_SENT", -1, actor="paypal")                  # no plan id at all: nothing to compare
    assert len(run(w)["results"]) == 1


# =============================== endpoint ===============================

def test_the_endpoint_is_for_members_and_reports_the_match(client, w, db):
    plan, rows = captured(w)
    db.commit()
    url = f"/api/projects/{w.project.id}/ledger/paypal-match"
    app.dependency_overrides[paypal_io.get_reader] = lambda: FakeReader(db, overrides=agree(rows))
    app.dependency_overrides[paypal_io.get_payout_reader] = lambda: Batches()
    try:
        assert client.get(url).status_code == 401
        assert client.get("/api/projects/9999/ledger/paypal-match", headers=hdr(lead_user(w))).status_code == 404
        assert client.get(url, headers=hdr(person(World(w.db, tag="o"), "LEAD", "outsider"))).status_code == 403
        got = client.get(url, headers=hdr(lead_user(w))).json()
        assert got["all_match"] is True and got["counts"]["MATCH"] == 3
        ledger = client.get(f"/api/projects/{w.project.id}/ledger", headers=hdr(lead_user(w))).json()
        assert all(r["paypal_match"] is None for r in ledger["rows"])               # the plain ledger never calls PayPal
    finally:
        app.dependency_overrides.pop(paypal_io.get_reader, None)
        app.dependency_overrides.pop(paypal_io.get_payout_reader, None)


def test_the_endpoint_without_paypal_configured_reports_unavailable_not_an_error(client, w, db):
    plan, rows = captured(w)
    db.commit()
    got = client.get(f"/api/projects/{w.project.id}/ledger/paypal-match", headers=hdr(lead_user(w)))
    assert got.status_code == 200 and got.json()["counts"]["UNAVAILABLE"] == 3


def test_the_match_module_cannot_write_to_paypal():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "app" / "services" / "ledger_match.py").read_text(encoding="utf-8")
    for name in ("capture_authorization", "void_authorization", "refund_capture", "create_payout_batch", "get_writer", "httpx"):
        assert name not in text


# ---- gaps found by the mutation check ----

def test_the_agreed_lookup_limit():
    assert lm.MAX_ROWS == 30                                   # at most 30 PayPal reads per request (free-tier friendly)


def test_two_payout_rows_of_one_batch_cause_one_lookup(w):
    from app.services import ledger
    plan, item, row = paid(w)
    ledger.append(w.db, w.project.id, "PLEDGE_CAPTURED", item.amount_cents, actor="paypal")
    ledger.append(w.db, w.project.id, "PAYOUT_SENT", -item.amount_cents, actor="paypal", meta={"plan_id": plan.id})
    b = Batches([entry(item)])
    out = run(w, batches=b)
    payouts = [v for v in out["results"].values() if v["paypal_ref"] == b.asked[0]]
    assert len(b.asked) == 1 and len(payouts) == 2


def test_a_refund_row_without_a_recorded_refund_id_is_skipped(w):
    from app.services import ledger
    ledger.append(w.db, w.project.id, "PLEDGE_CAPTURED", 500, actor="paypal")
    ledger.append(w.db, w.project.id, "REFUND", -500, actor="paypal")
    assert run(w)["results"] == {}
