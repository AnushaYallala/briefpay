"""Poll fallback (T-43): ask PayPal about steps still waiting when a webhook never came. Reuses the webhook rules."""
import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import Job, LedgerEntry, MoneyPlan, MoneyPlanStep, PayoutItem, Pledge
from app.main import app
from app.services import jobs, ledger, paypal_io, poll
from app.services import webhook_processing as wp
from app.services.guardian_rules import PayPalObject, PayPalUnavailable
from app.services.jobs import JobRunner
from app.services.money_executor import execute
from tests.factories import GOAL, NOW, FakeReader, FakeWriter, World
from tests.test_money_executor import approved_capture, approved_payout, approved_release, steps_of
from tests.test_plans_api import hdr, lead_user, person
from tests.test_webhooks import NoPayouts, capture_resource, event, sent_capture, sent_refund, sent_payout


@pytest.fixture()
def w(db):
    return World(db)


@pytest.fixture(autouse=True)
def placeholders():
    yield
    paypal_io.reset_to_placeholders()


def completed(step, cents=None):
    return PayPalObject("COMPLETED", cents if cents is not None else step.amount_cents)


def run_poll(w, reader, payout_reader=None, **kw):
    kw.setdefault("force", True)
    return poll.poll(w.db, reader, payout_reader or NoPayouts(), now=NOW, **kw)


class Batches:
    """Stands in for PayPal's payout batch lookup; remembers how often it was asked."""

    def __init__(self, items=None, down=False):
        self.items, self.down, self.asked = items or [], down, []

    def get_payout_batch(self, batch_id):
        self.asked.append(batch_id)
        if self.down:
            raise PayPalUnavailable("down")
        return {"batch_status": "PROCESSING", "items": self.items}


# =============================== captures ===============================

def test_polling_confirms_completed_captures_exactly_like_webhooks_would(w):
    plan, steps, pledges = sent_capture(w)
    reader = FakeReader(w.db, overrides={s.paypal_ref: completed(s) for s in steps})
    out = run_poll(w, reader)
    assert out["checked"] == 3 and out["confirmed"] == 3 and out["failed"] == 0
    assert plan.state == "DONE" and w.campaign.state == "CAPTURED" and w.project.state == "IN_PROGRESS"
    assert ledger.pool_balance(w.db, w.project.id) == GOAL
    assert all(p.status == "CAPTURED" and p.paypal_capture_id for p in pledges)


def test_a_second_poll_finds_nothing_left_to_do(w):
    plan, steps, _ = sent_capture(w)
    reader = FakeReader(w.db, overrides={s.paypal_ref: completed(s) for s in steps})
    run_poll(w, reader)
    before = w.db.query(LedgerEntry).count()
    again = run_poll(w, reader)
    assert again["checked"] == 0 and w.db.query(LedgerEntry).count() == before


def test_a_webhook_and_a_poll_for_the_same_step_do_not_double_count(w):
    plan, steps, pledges = sent_capture(w)
    wp.process(w.db, event("PAYMENT.CAPTURE.COMPLETED", capture_resource(steps[0], pledges[0].paypal_authorization_id)), payout_reader=NoPayouts(), now=NOW)
    reader = FakeReader(w.db, overrides={s.paypal_ref: completed(s) for s in steps})
    out = run_poll(w, reader)
    assert out["checked"] == 2 and out["confirmed"] == 2 and ledger.pool_balance(w.db, w.project.id) == GOAL


@pytest.mark.parametrize("status,bucket", [("PENDING", "pending"), ("PARTIALLY_REFUNDED", "confirmed"), ("REFUNDED", "confirmed"),
                                           ("DECLINED", "failed"), ("FAILED", "failed"), ("SOMETHING_NEW", "pending")])
def test_each_capture_status_is_handled(w, status, bucket):
    plan, steps, _ = sent_capture(w)
    reader = FakeReader(w.db, overrides={steps[0].paypal_ref: PayPalObject(status, steps[0].amount_cents)})
    out = run_poll(w, reader)
    assert out[bucket] == 1 and out["not_found"] == 2          # the other two captures are unknown to the fake PayPal
    assert steps[0].state == {"pending": "SENT", "confirmed": "CONFIRMED", "failed": "FAILED"}[bucket]


def test_a_declined_capture_ends_the_plan_partial_just_like_the_webhook_path(w):
    plan, steps, _ = sent_capture(w)
    reader = FakeReader(w.db, overrides={steps[0].paypal_ref: PayPalObject("DECLINED", steps[0].amount_cents),
                                         steps[1].paypal_ref: completed(steps[1]), steps[2].paypal_ref: completed(steps[2])})
    out = run_poll(w, reader)
    assert (out["confirmed"], out["failed"]) == (2, 1) and plan.state == "PARTIAL" and w.project.state == "PLEDGING"


def test_a_different_amount_is_flagged_not_booked_and_counted(w):
    plan, steps, _ = sent_capture(w)
    reader = FakeReader(w.db, overrides={steps[0].paypal_ref: completed(steps[0], steps[0].amount_cents + 1)})
    out = run_poll(w, reader)
    assert out["mismatch"] == 1 and steps[0].state == "SENT" and ledger.pool_balance(w.db, w.project.id) == 0
    memos = [e for e in w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "GUARDIAN_DECISION")) if "reconciliation" in e.meta_json]
    assert len(memos) == 1 and memos[0].meta_json["reconciliation"] == "RECONCILIATION_MISMATCH"


def test_when_paypal_cannot_be_reached_nothing_is_guessed(w):
    plan, steps, _ = sent_capture(w)
    out = run_poll(w, FakeReader(w.db, down=True))
    assert out["checked"] == 3 and out["unavailable"] == 3 and all(s.state == "SENT" for s in steps) and plan.state == "EXECUTING"


# =============================== which steps are polled ===============================

def test_a_step_sent_moments_ago_is_left_to_its_webhook_unless_the_user_asks(w):
    plan, steps, _ = sent_capture(w)
    reader = FakeReader(w.db, overrides={s.paypal_ref: completed(s) for s in steps})
    assert poll.poll(w.db, reader, NoPayouts(), force=False)["checked"] == 0             # just sent: real clock, age ~0
    assert poll.poll(w.db, reader, NoPayouts(), force=False, now=poll._now() + timedelta(seconds=poll.MIN_AGE_SECONDS + 5))["checked"] == 3
    assert all(s.state == "CONFIRMED" for s in steps)


def test_the_age_limit_is_applied_per_step(w):
    plan, steps, _ = sent_capture(w)
    old = poll._now() - timedelta(seconds=300)
    steps[0].updated_at = old
    w.db.flush()
    got = poll.waiting_steps(w.db, now=poll._now())
    assert [s.id for s in got] == [steps[0].id]
    steps[1].updated_at = poll._now() - timedelta(seconds=poll.MIN_AGE_SECONDS)             # exactly at the limit counts as old enough
    assert {s.id for s in poll.waiting_steps(w.db, now=poll._now())} == {steps[0].id, steps[1].id}


def test_only_steps_that_were_really_sent_in_a_running_plan_are_polled(w):
    plan, steps, _ = sent_capture(w)
    steps[0].paypal_ref = None                     # a crash between sending and saving the id: the executor's retry handles it, not the poll
    steps[1].state = "CONFIRMED"
    w.db.flush()
    assert [s.id for s in poll.waiting_steps(w.db, force=True)] == [steps[2].id]
    plan.state = "DONE"
    assert poll.waiting_steps(w.db, force=True) == []


def test_polling_can_be_limited_to_one_project_and_is_capped(w, monkeypatch):
    plan, steps, _ = sent_capture(w)
    other = World(w.db, tag="b")
    assert poll.waiting_steps(w.db, project_id=other.project.id, force=True) == []
    assert len(poll.waiting_steps(w.db, project_id=w.project.id, force=True)) == 3
    monkeypatch.setattr(poll, "MAX_STEPS", 2)
    assert len(poll.waiting_steps(w.db, force=True)) == 2


# =============================== voids, refunds, payouts ===============================

def test_voids_are_confirmed_when_paypal_says_the_authorization_is_voided(w):
    plan = approved_release(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    pledges = list(w.db.scalars(select(Pledge).where(Pledge.status == "AUTHORIZED")))
    reader = FakeReader(w.db, overrides={p.paypal_authorization_id: PayPalObject("VOIDED", p.amount_cents) for p in pledges[:2]}
                        | {pledges[2].paypal_authorization_id: PayPalObject("CREATED", pledges[2].amount_cents)})
    out = run_poll(w, reader)
    assert out["confirmed"] == 2 and out["pending"] == 1 and plan.state == "EXECUTING"
    reader.overrides[pledges[2].paypal_authorization_id] = PayPalObject("VOIDED", pledges[2].amount_cents)
    run_poll(w, reader)
    assert plan.state == "DONE" and w.campaign.state == "FAILED" and ledger.pool_balance(w.db, w.project.id) == 0


def test_an_unknown_authorization_is_counted_not_guessed(w):
    plan = approved_release(w)
    execute(w.db, plan.id, FakeWriter(), now=NOW)
    pledges = list(w.db.scalars(select(Pledge).where(Pledge.status == "AUTHORIZED")))
    out = run_poll(w, FakeReader(w.db, overrides={p.paypal_authorization_id: None for p in pledges}))
    assert out["not_found"] == 3 and out["confirmed"] == 0 and out["pending"] == 0


@pytest.mark.parametrize("status,bucket", [("COMPLETED", "confirmed"), ("PENDING", "pending"), ("FAILED", "failed"), ("CANCELLED", "failed")])
def test_refunds(w, status, bucket):
    plan, steps = sent_refund(w)
    reader = FakeReader(w.db, overrides={steps[0].paypal_ref: PayPalObject(status, steps[0].amount_cents)})
    out = run_poll(w, reader)
    assert out[bucket] == 1 and out["not_found"] == 2
    assert steps[0].state == {"confirmed": "CONFIRMED", "pending": "SENT", "failed": "FAILED"}[bucket]
    if bucket == "failed":
        assert steps[0].error_json["reason"] == f"REFUND_{status}"


def test_every_refund_completing_closes_the_project(w):
    plan, steps = sent_refund(w)
    run_poll(w, FakeReader(w.db, overrides={s.paypal_ref: PayPalObject("COMPLETED", s.amount_cents) for s in steps}))
    assert plan.state == "DONE" and w.project.state == "CANCELLED" and ledger.pool_balance(w.db, w.project.id) == 0


def batch_item(item, status):
    return {"payout_item_id": "PI-1", "transaction_status": status, "sender_item_id": item.sender_item_id, "receiver": item.receiver_email,
            "amount_cents": item.amount_cents}


def test_a_payout_batch_is_read_once_and_its_items_applied(w):
    plan, step, item = sent_payout(w)
    batch_id = step.paypal_ref                                  # a confirmed step later carries the payout item id instead
    batches = Batches([batch_item(item, "SUCCESS")])
    out = run_poll(w, FakeReader(w.db), batches)
    assert batches.asked == [batch_id] and out["confirmed"] == 1 and plan.state == "DONE" and w.project.state == "PAID"
    assert ledger.pool_balance(w.db, w.project.id) == 0


@pytest.mark.parametrize("status,state,bucket", [("SUCCESS", "CONFIRMED", "confirmed"), ("FAILED", "FAILED", "failed"), ("BLOCKED", "FAILED", "failed"),
                                                  ("UNCLAIMED", "SENT", "pending"), ("PENDING", "SENT", "pending"), ("HELD", "SENT", "pending")])
def test_payout_item_statuses_follow_the_webhook_rules_including_never_failing_unclaimed(w, status, state, bucket):
    plan, step, item = sent_payout(w)
    out = run_poll(w, FakeReader(w.db), Batches([batch_item(item, status)]))
    assert step.state == state and out[bucket] == 1
    if status == "UNCLAIMED":
        assert plan.state == "EXECUTING"                      # the money left our account: a retry here could pay twice


def test_a_payout_batch_that_cannot_be_read_is_postponed(w):
    plan, step, item = sent_payout(w)
    out = run_poll(w, FakeReader(w.db), Batches(down=True))
    assert out["unavailable"] == 1 and step.state == "SENT"


def test_two_items_of_one_batch_cause_one_lookup(w):
    plan, step, item = sent_payout(w)
    twin = MoneyPlanStep(plan_id=plan.id, seq=2, phase=1, op="PAYOUT_ITEM", target_type="CONTRACT", target_id=step.target_id, amount_cents=1,
                         bucket="POOL", idempotency_key="twin", state="SENT", paypal_ref=step.paypal_ref)
    w.db.add(twin)
    w.db.flush()
    batches = Batches([batch_item(item, "PENDING")])
    out = run_poll(w, FakeReader(w.db), batches)
    assert batches.asked == [step.paypal_ref] and out["checked"] == 1


# =============================== scheduling ===============================

def test_the_periodic_tick_does_nothing_until_paypal_is_configured(db):
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    assert poll.run_periodic(factory) is None


def test_the_periodic_tick_polls_and_saves(w, db):
    plan, steps, _ = sent_capture(w)
    for s in steps:
        s.updated_at = poll._now() - timedelta(minutes=5)
    db.commit()
    paypal_io.configure(reader=FakeReader(db, overrides={s.paypal_ref: completed(s) for s in steps}), payout_reader=NoPayouts())
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    out = poll.run_periodic(factory)
    assert out["confirmed"] == 3
    db.expire_all()
    assert db.get(MoneyPlan, plan.id).state == "DONE"


def test_a_failing_tick_is_rolled_back_and_reported(db):
    class Boom(FakeReader):
        def get_capture(self, capture_id):
            raise RuntimeError("bug")
    w = World(db)
    plan, steps, _ = sent_capture(w)
    for s in steps:
        s.updated_at = poll._now() - timedelta(minutes=5)
    db.commit()
    paypal_io.configure(reader=Boom(db), payout_reader=NoPayouts())
    with pytest.raises(RuntimeError):
        poll.run_periodic(sessionmaker(bind=db.get_bind(), expire_on_commit=False))


def test_the_runner_runs_each_chore_when_it_is_due_and_survives_a_failing_one(db):
    calls = []

    def chore():
        calls.append(1)

    def broken():
        raise RuntimeError("nope")
    runner = JobRunner(sessionmaker(bind=db.get_bind()), periodic=[(0.0, chore), (0.0, broken), (3600.0, lambda: calls.append("never"))])
    asyncio.run(runner._run_due_periodic())
    asyncio.run(runner._run_due_periodic())
    assert calls == [1, 1]                                  # the long-interval chore waits its turn; the broken one did not stop the others


def test_the_chore_does_not_run_before_its_interval_has_passed(db):
    calls = []
    runner = JobRunner(sessionmaker(bind=db.get_bind()), periodic=[(30.0, lambda: calls.append(1))])
    asyncio.run(runner._run_due_periodic())
    assert calls == []
    runner._last[0] -= 31
    asyncio.run(runner._run_due_periodic())
    assert calls == [1]


# =============================== the endpoint and the job ===============================

def clear_other_jobs(db):
    """Approving a plan queued its EXECUTE_PLAN job; these tests are about the poll job only."""
    for j in db.query(Job).all():
        j.state = "DONE"
    db.commit()


def test_refresh_asks_for_a_poll_job_once_and_the_job_confirms_waiting_steps(client, w, db):
    plan, steps, _ = sent_capture(w)
    clear_other_jobs(db)
    url = f"/api/projects/{w.project.id}/money/refresh"
    assert client.post(url).status_code == 401
    assert client.post("/api/projects/9999/money/refresh", headers=hdr(lead_user(w))).status_code == 404
    assert client.post(url, headers=hdr(person(World(w.db, tag="o"), "LEAD", "outsider"))).status_code == 403
    first = client.post(url, headers=hdr(lead_user(w)))
    assert first.status_code == 202 and first.json()["already_running"] is False
    second = client.post(url, headers=hdr(lead_user(w)))
    assert second.json() == {"job_id": first.json()["job_id"], "already_running": True}
    paypal_io.configure(reader=FakeReader(db, overrides={s.paypal_ref: completed(s) for s in steps}), payout_reader=NoPayouts())
    assert jobs.run_one(sessionmaker(bind=db.get_bind(), expire_on_commit=False)) is True
    db.expire_all()
    job = db.get(Job, first.json()["job_id"])
    assert job.state == "DONE" and job.result_json["confirmed"] == 3 and db.get(MoneyPlan, plan.id).state == "DONE"
    third = client.post(url, headers=hdr(lead_user(w)))
    assert third.json()["already_running"] is False and third.json()["job_id"] != first.json()["job_id"]


def test_the_refresh_job_only_touches_its_own_project(client, w, db):
    plan, steps, _ = sent_capture(w)
    other = World(db, tag="b")
    clear_other_jobs(db)
    paypal_io.configure(reader=FakeReader(db, overrides={s.paypal_ref: completed(s) for s in steps}), payout_reader=NoPayouts())
    job = jobs.enqueue(db, "POLL_STEPS", {"project_id": other.project.id, "force": True})
    db.commit()
    jobs.run_one(sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    db.expire_all()
    assert db.get(Job, job.id).result_json["checked"] == 0 and all(db.get(MoneyPlanStep, s.id).state == "SENT" for s in steps)


def test_the_poll_module_cannot_write_to_paypal():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "app" / "services" / "poll.py").read_text(encoding="utf-8")
    for name in ("capture_authorization", "void_authorization", "refund_capture", "create_payout_batch", "get_writer", "httpx"):
        assert name not in text


# ---- gaps found by the mutation check ----

def test_the_agreed_poll_numbers():
    assert poll.MIN_AGE_SECONDS == 20 and poll.MAX_STEPS == 50          # SPEC 9: webhooks get the first chance; at most 50 steps a pass


def test_the_age_limit_boundaries(w):
    plan, steps, _ = sent_capture(w)
    now = poll._now()
    for s, age in zip(steps, (19, 20, 25)):
        s.updated_at = now - timedelta(seconds=age)
    w.db.flush()
    got = {s.id for s in poll.waiting_steps(w.db, now=now)}
    assert got == {steps[1].id, steps[2].id}                            # 19 s: too fresh; exactly 20 s and 25 s: polled


@pytest.mark.parametrize("cents,text", [(0, "0.00"), (5, "0.05"), (10, "0.10"), (100, "1.00"), (1234, "12.34"), (15005, "150.05"), (99, "0.99")])
def test_money_is_written_with_two_decimals(cents, text):
    assert poll.value(cents) == text


def test_a_chore_waits_a_full_interval_after_each_run(db):
    calls = []
    runner = JobRunner(sessionmaker(bind=db.get_bind()), periodic=[(30.0, lambda: calls.append(1))])
    asyncio.run(runner._run_due_periodic())
    runner._last[0] -= 31
    asyncio.run(runner._run_due_periodic())
    asyncio.run(runner._run_due_periodic())                             # straight after: not due again
    assert calls == [1]


def test_the_running_loop_calls_the_chores(db):
    calls = []
    runner = JobRunner(sessionmaker(bind=db.get_bind()), poll_seconds=0.01, periodic=[(0.0, lambda: calls.append(1))])

    async def main():
        runner.start()
        await asyncio.sleep(0.3)
        await runner.stop()
    asyncio.run(main())
    assert len(calls) >= 2


def test_startup_builds_a_runner_that_polls_at_the_configured_interval(db, monkeypatch):
    from app.config import get_settings
    from app.main import build_runner
    seen = []
    monkeypatch.setattr(poll, "run_periodic", lambda factory: seen.append(factory))
    monkeypatch.setattr(get_settings(), "poll_interval_seconds", 17)
    factory = sessionmaker(bind=db.get_bind())
    runner = build_runner(get_settings(), factory)
    assert len(runner.periodic) == 2 and runner.periodic[0][0] == 17      # the poll fallback first, then the campaign clock
    runner.periodic[0][1]()
    assert seen == [factory]


def test_a_poll_job_queued_for_another_project_does_not_stand_in_for_this_one(client, w, db):
    other = World(db, tag="b")
    other_job = jobs.enqueue(db, "POLL_STEPS", {"project_id": other.project.id, "force": True})
    db.commit()
    got = client.post(f"/api/projects/{w.project.id}/money/refresh", headers=hdr(lead_user(w))).json()
    assert got["already_running"] is False and got["job_id"] != other_job.id
