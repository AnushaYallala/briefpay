"""PayPal webhooks: the receiver (verify, store once, queue) and the processing of every event type we act on."""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.main import app
from app.models import Campaign, Job, LedgerEntry, MoneyPlan, PayoutItem, Pledge, Project, WebhookEvent
from app.services import jobs, ledger, paypal_io
from app.services import plan_builder as pb
from app.services import plan_lifecycle as lc
from app.services import webhook_processing as wp
from app.services.guardian_rules import PayPalUnavailable
from app.services.money_executor import execute
from tests.factories import GOAL, NOW, FakeReader, FakeWriter, World
from tests.test_money_executor import approved_capture, approved_payout, approved_release, steps_of


@pytest.fixture()
def w(db):
    return World(db)


def event(event_type, resource, eid=None, n=[0]):
    n[0] += 1
    return {"id": eid or f"WH-{n[0]}", "event_type": event_type, "resource": resource, "create_time": "2026-11-10T12:00:00Z"}


def capture_resource(step, auth_id, cents=None, capture_id=None):
    c = cents if cents is not None else step.amount_cents
    return {"id": capture_id or step.paypal_ref, "status": "COMPLETED", "amount": {"currency_code": "USD", "value": f"{c // 100}.{c % 100:02d}"},
            "supplementary_data": {"related_ids": {"authorization_id": auth_id}}}


def run(w, ev, payout_reader=None):
    return wp.process(w.db, ev, payout_reader=payout_reader or NoPayouts(), now=NOW)


class NoPayouts:
    def get_payout_batch(self, batch_id):
        raise AssertionError("no batch lookup expected")


def ledger_count(w):
    return w.db.query(LedgerEntry).count()


# =============================== processing ===============================

# ---------------- captures ----------------

def sent_capture(w):
    plan = approved_capture(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    return plan, steps_of(w, plan), list(w.db.scalars(select(Pledge).order_by(Pledge.id)))


def test_capture_completed_events_confirm_the_steps_and_fund_the_project(w):
    plan, steps, pledges = sent_capture(w)
    for s, p in zip(steps, pledges):
        out = run(w, event("PAYMENT.CAPTURE.COMPLETED", capture_resource(s, p.paypal_authorization_id)))
        assert out == {"effect": "STEP_CONFIRMED", "step_id": s.id}
    assert plan.state == "DONE" and w.campaign.state == "CAPTURED" and w.project.state == "IN_PROGRESS"
    assert ledger.pool_balance(w.db, w.project.id) == GOAL


def test_a_repeated_capture_event_changes_nothing(w):
    plan, steps, pledges = sent_capture(w)
    ev = event("PAYMENT.CAPTURE.COMPLETED", capture_resource(steps[0], pledges[0].paypal_authorization_id))
    run(w, ev)
    before = (ledger_count(w), ledger.pool_balance(w.db, w.project.id))
    assert run(w, ev)["effect"] == "ALREADY_APPLIED"
    assert (ledger_count(w), ledger.pool_balance(w.db, w.project.id)) == before


def test_an_event_that_beats_our_own_record_of_the_capture_id_is_matched_by_the_authorization(w):
    """Out of order: PayPal's webhook can arrive before the executor stored the capture id it got back."""
    plan, steps, pledges = sent_capture(w)
    steps[0].paypal_ref = None
    w.db.flush()
    out = run(w, event("PAYMENT.CAPTURE.COMPLETED", capture_resource(steps[0], pledges[0].paypal_authorization_id, capture_id="CAP-REAL")))
    assert out["effect"] == "STEP_CONFIRMED" and steps[0].paypal_ref == "CAP-REAL" and pledges[0].paypal_capture_id == "CAP-REAL"


def test_a_capture_for_a_pledge_whose_step_is_not_recorded_yet_is_retried_later(w):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    p = w.db.scalars(select(Pledge)).first()
    with pytest.raises(wp.NotReady):
        run(w, event("PAYMENT.CAPTURE.COMPLETED", {"id": "CAP-X", "amount": {"value": "150.00"},
                                                   "supplementary_data": {"related_ids": {"authorization_id": p.paypal_authorization_id}}}))


def test_a_capture_that_is_not_ours_is_ignored(w):
    out = run(w, event("PAYMENT.CAPTURE.COMPLETED", {"id": "CAP-STRANGER", "amount": {"value": "1.00"},
                                                     "supplementary_data": {"related_ids": {"authorization_id": "AUTH-STRANGER"}}}))
    assert out == {"effect": "UNKNOWN_OBJECT", "capture_id": "CAP-STRANGER"}


def test_a_capture_amount_different_from_the_approved_plan_is_flagged_not_booked(w):
    plan, steps, pledges = sent_capture(w)
    before = ledger_count(w)
    out = run(w, event("PAYMENT.CAPTURE.COMPLETED", capture_resource(steps[0], pledges[0].paypal_authorization_id, cents=steps[0].amount_cents + 1)))
    assert out["effect"] == "RECONCILIATION_MISMATCH" and out["paypal_cents"] == steps[0].amount_cents + 1
    # not booked: the step waits and the POOL is untouched; one alert memo is written (SPEC 7.6 step 5), and only once
    assert steps[0].state == "SENT" and ledger_count(w) == before + 1 and ledger.pool_balance(w.db, w.project.id) == 0
    memo = w.db.scalars(select(LedgerEntry).order_by(LedgerEntry.seq.desc())).first()
    assert memo.type == "GUARDIAN_DECISION" and memo.amount_cents == 0 and memo.meta_json["reconciliation"] == "RECONCILIATION_MISMATCH"
    run(w, event("PAYMENT.CAPTURE.COMPLETED", capture_resource(steps[0], pledges[0].paypal_authorization_id, cents=steps[0].amount_cents + 1)))
    assert ledger_count(w) == before + 1


def test_a_reversed_capture_leaves_one_alert_memo_and_books_nothing(w):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    w.capture_all()
    p = w.db.scalars(select(Pledge)).first()
    before, pool = ledger_count(w), ledger.pool_balance(w.db, w.project.id)
    for _ in range(2):
        assert run(w, event("PAYMENT.CAPTURE.REVERSED", {"id": p.paypal_capture_id}))["effect"] == "ALERT"
    assert ledger_count(w) == before + 1 and ledger.pool_balance(w.db, w.project.id) == pool
    memo = w.db.scalars(select(LedgerEntry).order_by(LedgerEntry.seq.desc())).first()
    assert (memo.ref_type, memo.ref_id, memo.meta_json["alert"]) == ("pledge", str(p.id), "CAPTURE_REVERSED")


def test_a_declined_capture_fails_its_step_and_the_plan_ends_partial(w):
    plan, steps, pledges = sent_capture(w)
    out = run(w, event("PAYMENT.CAPTURE.DECLINED", capture_resource(steps[0], pledges[0].paypal_authorization_id)))
    assert out["effect"] == "STEP_FAILED" and steps[0].state == "FAILED" and steps[0].error_json["reason"] == "CAPTURE_DECLINED"
    for s, p in zip(steps[1:], pledges[1:]):
        run(w, event("PAYMENT.CAPTURE.COMPLETED", capture_resource(s, p.paypal_authorization_id)))
    assert plan.state == "PARTIAL" and w.campaign.state == "CAPTURING" and w.project.state == "PLEDGING"


def test_a_pending_capture_leaves_the_step_waiting(w):
    plan, steps, pledges = sent_capture(w)
    out = run(w, event("PAYMENT.CAPTURE.PENDING", capture_resource(steps[0], pledges[0].paypal_authorization_id)))
    assert out["effect"] == "STILL_PENDING" and steps[0].state == "SENT"


# ---------------- voids ----------------

def test_planned_voids_are_confirmed_and_the_campaign_fails_with_nobody_charged(w):
    plan = approved_release(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    for p in w.db.scalars(select(Pledge).where(Pledge.status == "AUTHORIZED")).all():
        assert run(w, event("PAYMENT.AUTHORIZATION.VOIDED", {"id": p.paypal_authorization_id, "status": "VOIDED"}))["effect"] == "STEP_CONFIRMED"
    assert plan.state == "DONE" and w.campaign.state == "FAILED" and w.project.state == "CAMPAIGN_FAILED"
    assert ledger.pool_balance(w.db, w.project.id) == 0


def test_an_unplanned_void_stops_the_hold_counting(w):
    """A buyer cancelled the hold in PayPal (we did not ask): it stops counting, with a memo row marked unplanned."""
    p = w.pledge(15000)
    out = run(w, event("PAYMENT.AUTHORIZATION.VOIDED", {"id": p.paypal_authorization_id}))
    assert out == {"effect": "PLEDGE_VOIDED", "pledge_id": p.id} and p.status == "VOIDED"
    memo = w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "PLEDGE_VOIDED")).one()
    assert memo.amount_cents == 0 and memo.meta_json["unplanned"] is True
    assert run(w, event("PAYMENT.AUTHORIZATION.VOIDED", {"id": p.paypal_authorization_id}))["effect"] == "ALREADY_APPLIED"
    assert w.db.query(LedgerEntry).filter(LedgerEntry.type == "PLEDGE_VOIDED").count() == 1


def test_void_events_for_finished_or_unknown_holds(w):
    p = w.pledge(15000, status="VOIDED")
    assert run(w, event("PAYMENT.AUTHORIZATION.VOIDED", {"id": p.paypal_authorization_id}))["effect"] == "ALREADY_APPLIED"
    assert run(w, event("PAYMENT.AUTHORIZATION.VOIDED", {"id": "AUTH-NOT-OURS"}))["effect"] == "UNKNOWN_OBJECT"


# ---------------- refunds ----------------

def sent_refund(w):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    w.capture_all()
    w.project.state = "IN_PROGRESS"
    plan = pb.save_proposed(w.db, pb.build_refund_captured(w.db, w.project.id, "CANCEL_BEFORE_WORK"), proposed_by=f"user:{w.project.lead_user_id}")
    review = lc.review_plan(w.db, plan, reader=FakeReader(w.db), now=NOW)
    lc.approve_plan(w.db, plan, approver=f"user:{w.project.lead_user_id}", plan_hash=plan.plan_hash, guardian_review_id=review.id)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    return plan, steps_of(w, plan)


def refund_resource(step, capture_id, refund_id=None):
    return {"id": refund_id or step.paypal_ref, "status": "COMPLETED",
            "links": [{"rel": "self", "href": "https://api.sandbox.paypal.com/v2/payments/refunds/R"},
                      {"rel": "up", "href": f"https://api.sandbox.paypal.com/v2/payments/captures/{capture_id}"}]}


def test_refund_events_confirm_the_refunds_and_close_the_project(w):
    plan, steps = sent_refund(w)
    for s in steps:
        p = w.db.get(Pledge, s.target_id)
        assert run(w, event("PAYMENT.CAPTURE.REFUNDED", refund_resource(s, p.paypal_capture_id)))["effect"] == "STEP_CONFIRMED"
    assert plan.state == "DONE" and w.project.state == "CANCELLED" and ledger.pool_balance(w.db, w.project.id) == 0


def test_a_refund_event_is_matched_by_the_capture_when_our_refund_id_is_not_stored_yet(w):
    plan, steps = sent_refund(w)
    s = steps[0]
    s.paypal_ref = None
    w.db.flush()
    p = w.db.get(Pledge, s.target_id)
    out = run(w, event("PAYMENT.CAPTURE.REFUNDED", refund_resource(s, p.paypal_capture_id, refund_id="REF-REAL")))
    assert out["effect"] == "STEP_CONFIRMED" and s.paypal_ref == "REF-REAL"
    again = run(w, event("PAYMENT.CAPTURE.REFUNDED", refund_resource(s, p.paypal_capture_id, refund_id="REF-REAL")))
    assert again["effect"] == "ALREADY_APPLIED"


def test_a_refund_that_is_not_ours_is_ignored(w):
    out = run(w, event("PAYMENT.CAPTURE.REFUNDED", {"id": "REF-X", "links": [{"rel": "up", "href": "https://x/v2/payments/captures/CAP-NOT-OURS"}]}))
    assert out["effect"] == "UNKNOWN_OBJECT"


# ---------------- payouts ----------------

def sent_payout(w):
    plan = approved_payout(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    return plan, steps_of(w, plan)[0], w.db.scalars(select(PayoutItem)).one()


def item_event(item, status, eid=None):
    return event(f"PAYMENT.PAYOUTS-ITEM.{status}", {"payout_item_id": "PI-1", "transaction_status": status, "payout_batch_id": "B1",
                                                    "payout_item": {"sender_item_id": item.sender_item_id, "receiver": item.receiver_email}}, eid)


def test_a_succeeded_payout_pays_the_project_and_empties_the_pool(w):
    plan, step, item = sent_payout(w)
    out = run(w, item_event(item, "SUCCEEDED"))
    assert out["effect"] == "STEP_CONFIRMED" and plan.state == "DONE" and w.project.state == "PAID"
    assert ledger.pool_balance(w.db, w.project.id) == 0 and item.status == "SUCCEEDED" and item.paypal_item_id == "PI-1"
    assert run(w, item_event(item, "SUCCEEDED"))["effect"] == "ALREADY_APPLIED"


@pytest.mark.parametrize("status", ["FAILED", "BLOCKED", "CANCELED", "DENIED", "RETURNED"])
def test_a_payout_that_fails_before_succeeding_fails_the_plan_and_keeps_the_money(w, status):
    plan, step, item = sent_payout(w)
    out = run(w, item_event(item, status))
    assert out["effect"] == "STEP_FAILED" and plan.state == "FAILED" and w.project.state == "PAYOUT_FAILED"
    assert ledger.pool_balance(w.db, w.project.id) == GOAL


def test_unclaimed_is_not_a_failure_so_the_freelancer_can_never_be_paid_twice(w):
    """PayPal has already taken the money for an UNCLAIMED item. Failing the step would invite a retry: a double payout."""
    plan, step, item = sent_payout(w)
    out = run(w, item_event(item, "UNCLAIMED"))
    assert out["effect"] == "STILL_PENDING" and step.state == "SENT" and plan.state == "EXECUTING"
    assert w.project.state == "PAYOUT_PENDING" and item.status == "UNCLAIMED"
    # and a second payout cannot start: an identical plan is the SAME plan, and the Guardian would refuse a new one
    again = pb.save_proposed(w.db, pb.build_freelancer_payout(w.db, w.project.id), proposed_by=f"user:{w.project.lead_user_id}")
    assert again.id == plan.id
    from app.services import guardian_rules as g
    ev = g.evaluate(w.db, plan, now=NOW, reader=FakeReader(w.db))
    assert "G-12" in ev.failed_ids and "PAYOUT_READY" in ev.get("G-12").detail


def test_held_items_wait(w):
    plan, step, item = sent_payout(w)
    assert run(w, item_event(item, "HELD"))["effect"] == "STILL_PENDING" and step.state == "SENT" and item.status == "HELD"


def test_a_payout_that_succeeded_and_then_came_back_returns_the_money_to_the_pool_once(w):
    plan, step, item = sent_payout(w)
    run(w, item_event(item, "SUCCEEDED"))
    out = run(w, item_event(item, "RETURNED"))
    assert out["effect"] == "PAYOUT_RETURNED" and ledger.pool_balance(w.db, w.project.id) == GOAL
    assert run(w, item_event(item, "RETURNED"))["effect"] == "ALREADY_APPLIED" and ledger.pool_balance(w.db, w.project.id) == GOAL
    returned = w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "PAYOUT_RETURNED")).one()
    assert returned.amount_cents == GOAL and returned.bucket == "POOL"


def test_a_payout_item_that_is_not_ours_is_ignored(w):
    out = run(w, event("PAYMENT.PAYOUTS-ITEM.SUCCEEDED", {"transaction_status": "SUCCESS", "payout_item": {"sender_item_id": "999999"}}))
    assert out["effect"] == "UNKNOWN_OBJECT"


class Batch:
    def __init__(self, items=None, down=False):
        self.items, self.down, self.asked = items or [], down, []

    def get_payout_batch(self, batch_id):
        self.asked.append(batch_id)
        if self.down:
            raise PayPalUnavailable("down")
        return {"batch_status": "SUCCESS", "items": self.items}


def test_batch_events_fetch_the_items_and_apply_each_status(w):
    plan, step, item = sent_payout(w)
    reader = Batch([{"payout_item_id": "PI-9", "transaction_status": "SUCCESS", "sender_item_id": item.sender_item_id}])
    out = run(w, event("PAYMENT.PAYOUTSBATCH.SUCCESS", {"batch_header": {"payout_batch_id": "BATCH-77", "batch_status": "SUCCESS"}}), payout_reader=reader)
    assert reader.asked == ["BATCH-77"] and out["effect"] == "BATCH_APPLIED" and out["items"][0]["effect"] == "STEP_CONFIRMED"
    assert w.project.state == "PAID"


def test_a_batch_event_while_paypal_is_unreachable_is_retried_later(w):
    sent_payout(w)
    with pytest.raises(wp.NotReady):
        run(w, event("PAYMENT.PAYOUTSBATCH.PROCESSING", {"batch_header": {"payout_batch_id": "B"}}), payout_reader=Batch(down=True))


# ---------------- the rest ----------------

def waiting(w, cents):
    """A pledge whose order exists but whose hold has not been recorded yet."""
    p = w.pledge(cents, status="CREATED")
    p.paypal_authorization_id = None
    w.db.flush()
    return p


def created_resource(p, auth_id="AUTH-NEW", cents=None, **kw):
    c = p.amount_cents if cents is None else cents
    return {"id": auth_id, "status": "CREATED", "amount": {"currency_code": "USD", "value": f"{c // 100}.{c % 100:02d}"},
            "supplementary_data": {"related_ids": {"order_id": p.paypal_order_id}}, **kw}


def test_a_hold_placed_event_counts_the_hold_once(w):
    p = waiting(w, 15000)
    out = run(w, event("PAYMENT.AUTHORIZATION.CREATED", created_resource(p)))
    assert out == {"effect": "PLEDGE_AUTHORIZED", "pledge_id": p.id}
    assert p.status == "AUTHORIZED" and p.paypal_authorization_id == "AUTH-NEW" and p.honor_until is not None
    assert w.db.query(LedgerEntry).filter(LedgerEntry.type == "PLEDGE_AUTHORIZED").count() == 1
    assert run(w, event("PAYMENT.AUTHORIZATION.CREATED", created_resource(p)))["effect"] == "ALREADY_APPLIED"
    assert w.db.query(LedgerEntry).filter(LedgerEntry.type == "PLEDGE_AUTHORIZED").count() == 1


def test_a_hold_placed_event_finds_the_pledge_by_its_custom_id(w):
    p = waiting(w, 15000)
    res = {**created_resource(p), "supplementary_data": {}, "custom_id": f"camp:{w.campaign.id}:pledge:{p.id}"}
    assert run(w, event("PAYMENT.AUTHORIZATION.CREATED", res))["effect"] == "PLEDGE_AUTHORIZED"
    q = waiting(w, 5000)
    wrong = {**created_resource(q, "AUTH-2"), "supplementary_data": {}, "custom_id": f"camp:{w.campaign.id + 99}:pledge:{q.id}"}
    assert run(w, event("PAYMENT.AUTHORIZATION.CREATED", wrong))["effect"] == "UNKNOWN_OBJECT" and q.status == "CREATED"


def test_a_hold_that_does_not_match_is_never_counted(w):
    p = waiting(w, 15000)
    assert run(w, event("PAYMENT.AUTHORIZATION.CREATED", created_resource(p, cents=14000)))["effect"] == "HOLD_MISMATCH"
    assert run(w, event("PAYMENT.AUTHORIZATION.CREATED", created_resource(p, status="DENIED")))["effect"] == "HOLD_MISMATCH"
    assert p.status == "CREATED" and p.paypal_authorization_id is None


def test_a_hold_that_arrives_after_the_campaign_closed_is_not_counted(w):
    p = waiting(w, 15000)
    w.campaign.state = "FAILED"
    assert run(w, event("PAYMENT.AUTHORIZATION.CREATED", created_resource(p)))["effect"] == "LATE_HOLD_IGNORED"
    assert p.status == "CREATED"


def test_a_hold_event_for_something_we_never_started(w):
    assert run(w, event("PAYMENT.AUTHORIZATION.CREATED", {"id": "AUTH-X", "status": "CREATED"}))["effect"] == "UNKNOWN_OBJECT"


def test_informational_alerts_and_unknown_types(w):
    assert run(w, event("CHECKOUT.ORDER.APPROVED", {"id": "O1"}))["effect"] == "INFORMATIONAL"
    assert run(w, event("PAYMENT.CAPTURE.REVERSED", {"id": "C1"}))["effect"] == "ALERT"
    assert run(w, event("BILLING.SUBSCRIPTION.CREATED", {"id": "S"}))["effect"] == "IGNORED"
    assert run(w, {"id": "x", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": "not a dict"})["effect"] == "UNKNOWN_OBJECT"


def test_processing_never_writes_to_paypal(w):
    """Handlers update steps and ledger only (SPEC 9.5 rule 5): the executor's writer is never touched."""
    plan, steps, pledges = sent_capture(w)
    paypal_io.configure(writer=Exploding())
    try:
        for s, p in zip(steps, pledges):
            run(w, event("PAYMENT.CAPTURE.COMPLETED", capture_resource(s, p.paypal_authorization_id)))
    finally:
        paypal_io.reset_to_placeholders()
    assert plan.state == "DONE"


class Exploding:
    def __getattr__(self, name):
        raise AssertionError(f"webhook processing tried to call PayPal: {name}")


# =============================== the receiver ===============================

class Verifier:
    def __init__(self, answer=True, down=False):
        self.answer, self.down, self.calls = answer, down, []

    def verify_webhook_signature(self, headers, raw_body, webhook_id):
        self.calls.append((headers, raw_body, webhook_id))
        if self.down:
            raise PayPalUnavailable("down")
        return self.answer


@pytest.fixture()
def receiver(db, monkeypatch):
    v = Verifier()
    app.dependency_overrides[paypal_io.get_verifier] = lambda: v
    monkeypatch.setattr(get_settings(), "paypal_webhook_id", "WEBHOOK-ID-1")
    yield v
    app.dependency_overrides.pop(paypal_io.get_verifier, None)


def post(client, body, headers=None):
    raw = body if isinstance(body, (bytes, str)) else json.dumps(body)
    return client.post("/api/webhooks/paypal", content=raw, headers={"Content-Type": "application/json", "PayPal-Transmission-Id": "t1", **(headers or {})})


def test_a_verified_event_is_stored_once_and_queued(client, db, receiver):
    ev = event("PAYMENT.CAPTURE.COMPLETED", {"id": "CAP-1"}, eid="WH-ABC")
    r = post(client, ev)
    assert r.status_code == 200 and r.json() == {"status": "accepted"}
    row = db.scalars(select(WebhookEvent)).one()
    assert (row.paypal_event_id, row.event_type, row.resource_id, row.verified, row.processed_at) == ("WH-ABC", "PAYMENT.CAPTURE.COMPLETED", "CAP-1", True, None)
    job = db.scalars(select(Job).where(Job.type == "PROCESS_WEBHOOK")).one()
    assert job.payload_json == {"webhook_event_id": row.id}
    headers, raw, wid = receiver.calls[0]
    assert wid == "WEBHOOK-ID-1" and json.loads(raw) == ev and headers.get("paypal-transmission-id") == "t1"


def test_a_repeated_event_is_a_harmless_200_and_is_not_verified_or_queued_again(client, db, receiver):
    ev = event("PAYMENT.CAPTURE.COMPLETED", {"id": "CAP-1"}, eid="WH-DUP")
    post(client, ev)
    r = post(client, ev)
    assert r.status_code == 200 and r.json() == {"status": "duplicate"}
    assert db.query(WebhookEvent).count() == 1 and db.query(Job).count() == 1 and len(receiver.calls) == 1


def test_a_forged_event_is_recorded_as_unverified_rejected_and_never_processed(client, db, receiver):
    receiver.answer = False
    r = post(client, event("PAYMENT.CAPTURE.COMPLETED", {"id": "CAP-FAKE"}, eid="WH-FORGED"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_SIGNATURE"
    row = db.scalars(select(WebhookEvent)).one()
    assert row.verified is False and db.query(Job).count() == 0


def test_when_paypal_cannot_verify_nothing_is_stored_so_paypal_redelivers(client, db, receiver):
    receiver.down = True
    r = post(client, event("PAYMENT.CAPTURE.COMPLETED", {"id": "C"}))
    assert r.status_code == 503 and r.json()["error"]["code"] == "PAYPAL_UNAVAILABLE"
    assert db.query(WebhookEvent).count() == 0 and db.query(Job).count() == 0


def test_without_a_webhook_id_events_cannot_be_verified_and_are_not_stored(client, db, receiver, monkeypatch):
    monkeypatch.setattr(get_settings(), "paypal_webhook_id", "")
    r = post(client, event("PAYMENT.CAPTURE.COMPLETED", {"id": "C"}))
    assert r.status_code == 503 and r.json()["error"]["code"] == "WEBHOOK_NOT_CONFIGURED" and db.query(WebhookEvent).count() == 0


@pytest.mark.parametrize("body", ["not json", "[]", "{}", json.dumps({"id": "x"}), json.dumps({"event_type": "X"}),
                                  json.dumps({"id": 5, "event_type": "X"}), json.dumps({"id": "x" * 65, "event_type": "X"}),
                                  json.dumps({"id": "", "event_type": "X"})])
def test_malformed_bodies_are_rejected_before_anything_else(client, db, receiver, body):
    r = post(client, body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_EVENT"
    assert receiver.calls == [] and db.query(WebhookEvent).count() == 0


def test_an_oversized_body_is_refused(client, db, receiver):
    big = json.dumps({"id": "big", "event_type": "X", "resource": {"pad": "x" * 300_000}})
    assert post(client, big).status_code == 413 and receiver.calls == []


def test_two_deliveries_racing_each_other_store_one_row(client, db, receiver):
    """Simulate the second delivery landing between our duplicate check and our insert."""
    class Racing(Verifier):
        def verify_webhook_signature(self, headers, raw_body, webhook_id):
            db.add(WebhookEvent(paypal_event_id="WH-RACE", event_type="X", payload_json={}, verified=True))
            db.commit()
            return True
    app.dependency_overrides[paypal_io.get_verifier] = lambda: Racing()
    r = post(client, event("PAYMENT.CAPTURE.COMPLETED", {"id": "C"}, eid="WH-RACE"))
    assert r.status_code == 200 and r.json() == {"status": "duplicate"}
    assert db.query(WebhookEvent).filter(WebhookEvent.paypal_event_id == "WH-RACE").count() == 1


# =============================== end to end through the job ===============================

def test_receiver_job_and_processing_together_fund_the_project(client, db, receiver, w):
    """The real path: approval queued the executor job; the job sends the captures; PayPal's webhooks confirm them."""
    plan = approved_capture(w)
    w.db.commit()
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    writer = FakeWriter()
    paypal_io.configure(writer=writer)
    try:
        while jobs.run_one(factory):                                   # EXECUTE_PLAN: three captures sent
            pass
        db.expire_all()
        assert writer.ops() == ["capture"] * 3 and db.get(MoneyPlan, plan.id).state == "EXECUTING"
        steps = steps_of(w, plan)
        pledges = list(db.scalars(select(Pledge).order_by(Pledge.id)))
        for s, p in zip(steps, pledges):
            assert post(client, event("PAYMENT.CAPTURE.COMPLETED", capture_resource(s, p.paypal_authorization_id))).status_code == 200
        while jobs.run_one(factory):                                   # PROCESS_WEBHOOK x3
            pass
    finally:
        paypal_io.reset_to_placeholders()
    db.expire_all()
    assert len(writer.calls) == 3, "processing the webhooks sent nothing to PayPal"
    assert db.get(MoneyPlan, plan.id).state == "DONE" and db.get(Campaign, w.campaign.id).state == "CAPTURED"
    assert db.get(Project, w.project.id).state == "IN_PROGRESS"
    assert all(r.processed_at is not None for r in db.scalars(select(WebhookEvent)))
    done = [j.result_json for j in db.scalars(select(Job).where(Job.type == "PROCESS_WEBHOOK"))]
    assert {r["effect"] for r in done} == {"STEP_CONFIRMED"}


def test_an_event_that_is_not_ready_is_retried_and_succeeds_once_our_record_exists(client, db, receiver, w):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    p = w.db.scalars(select(Pledge)).first()
    w.db.commit()
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    post(client, event("PAYMENT.CAPTURE.COMPLETED", {"id": "CAP-EARLY", "amount": {"value": "150.00"},
                                                     "supplementary_data": {"related_ids": {"authorization_id": p.paypal_authorization_id}}}))
    jobs.run_one(factory)
    db.expire_all()
    job = db.scalars(select(Job).where(Job.type == "PROCESS_WEBHOOK")).one()
    assert job.state == "QUEUED" and "NotReady" in job.last_error and job.attempts == 1
    assert db.scalars(select(WebhookEvent)).one().processed_at is None


def test_a_processed_event_is_not_processed_twice_even_if_its_job_runs_again(client, db, receiver, w):
    post(client, event("CHECKOUT.ORDER.APPROVED", {"id": "O1"}, eid="WH-ONCE"))
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    jobs.run_one(factory)
    row = db.scalars(select(WebhookEvent)).one()
    jobs.enqueue(db, "PROCESS_WEBHOOK", {"webhook_event_id": row.id})
    db.commit()
    jobs.run_one(factory)
    db.expire_all()
    results = [j.result_json for j in db.scalars(select(Job).order_by(Job.id))]
    assert results == [{"effect": "INFORMATIONAL"}, {"effect": "ALREADY_PROCESSED"}]


def test_an_unverified_row_is_never_processed_even_if_a_job_points_at_it(db, w):
    row = WebhookEvent(paypal_event_id="WH-BAD", event_type="PAYMENT.CAPTURE.COMPLETED", payload_json={}, verified=False)
    db.add(row)
    db.flush()
    jobs.enqueue(db, "PROCESS_WEBHOOK", {"webhook_event_id": row.id})
    db.commit()
    jobs.run_one(sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    db.expire_all()
    assert db.scalars(select(Job)).one().result_json == {"effect": "SKIPPED", "why": "unknown or unverified event"}
