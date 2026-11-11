"""The campaign clock and the lead's buttons: what gets built, who proposes it, and that nothing is ever built twice."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agents.guardian_llm import GuardianLLM, get_guardian_llm
from app.auth import create_token
from app.config import get_settings
from app.main import app
from app.models import Campaign, Job, LedgerEntry, MoneyPlan, Pledge, ProjectMember, User
from app.services import campaign_clock as clock
from app.services import campaign_ops as ops
from app.services import paypal_io
from tests.factories import GOAL, NOW, FakeReader, World, scripted_llm


@pytest.fixture()
def w(db):
    return World(db)


@pytest.fixture()
def llm(db):
    return scripted_llm(db)[0]            # always answers "low risk"


def tick(w, llm, now=NOW):
    return clock.tick(w.db, now=now, reader=FakeReader(w.db), llm=llm)


def plans(w):
    return list(w.db.scalars(select(MoneyPlan).order_by(MoneyPlan.id)))


def fund(w, holds=(15000, 15000, 10000)):
    return [w.pledge(h) for h in holds]


AFTER_DEADLINE = NOW + timedelta(hours=41)


# =============================== the clock ===============================

def test_nothing_to_do_while_the_goal_is_far_and_the_deadline_is_ahead(w, llm):
    w.pledge(10000)
    assert tick(w, llm) == [] and plans(w) == [] and w.campaign.goal_reached_at is None


def test_a_funded_campaign_is_collected_without_anyone_clicking(w, llm):
    fund(w)
    [r] = tick(w, llm)
    assert (r["action"], r["reason"], r["plan_state"]) == ("CAPTURE", "GOAL_REACHED", "APPROVED")
    [plan] = plans(w)
    assert plan.kind == "CAPTURE_PLEDGES" and plan.proposed_by == "system" and plan.release_policy == "AUTO_ON_ALLOW"
    assert w.campaign.goal_reached_at == NOW
    jobs = [j for j in w.db.scalars(select(Job)) if j.type == "EXECUTE_PLAN"]
    assert len(jobs) == 1 and jobs[0].payload_json["plan_id"] == plan.id          # the executor takes it from here
    assert w.db.query(LedgerEntry).filter(LedgerEntry.type == "GUARDIAN_DECISION").count() == 1


def test_a_second_tick_builds_nothing_more(w, llm):
    fund(w)
    tick(w, llm)
    [r] = tick(w, llm, NOW + timedelta(minutes=1))
    assert r == {"campaign_id": w.campaign.id, "action": "SKIPPED", "why": "PLAN_EXISTS"}
    assert len(plans(w)) == 1


def test_a_blocked_plan_is_left_for_a_human_not_rebuilt(w, llm):
    fund(w)
    tick(w, llm)
    plans(w)[0].state = "BLOCKED"
    assert tick(w, llm)[0]["why"] == "PLAN_EXISTS" and len(plans(w)) == 1


def test_at_deadline_campaigns_wait_for_the_deadline_then_collect(w, llm):
    w.campaign.close_policy = "AT_DEADLINE"
    fund(w)
    assert tick(w, llm) == [] and plans(w) == []                      # goal met, but this campaign runs to its deadline
    assert w.campaign.goal_reached_at == NOW                          # the moment is still noted
    [r] = tick(w, llm, NOW + timedelta(hours=40, minutes=1))
    assert (r["action"], r["reason"]) == ("CAPTURE", "DEADLINE_MET")


def test_a_missed_deadline_releases_every_hold(w, llm):
    fund(w, (15000, 10000))
    assert tick(w, llm) == []
    [r] = tick(w, llm, AFTER_DEADLINE)
    assert (r["action"], r["reason"]) == ("RELEASE", "DEADLINE_MISSED")
    [plan] = plans(w)
    assert plan.kind == "RELEASE_HOLDS" and plan.reason == "DEADLINE_MISSED" and plan.proposed_by == "system"
    assert len(plan.plan_json["steps"]) == 2 and all(s["op"] == "VOID_AUTH" for s in plan.plan_json["steps"])


def test_a_hold_past_its_honor_period_does_not_count_toward_the_goal(w, llm):
    fund(w, (15000, 15000))
    w.pledge(10000, honor_hours=-1)                                    # PayPal no longer guarantees this one
    assert tick(w, llm) == [] and plans(w) == [] and w.campaign.goal_reached_at is None


def test_orders_nobody_approved_are_forgotten_after_an_hour(w, llm):
    old = w.pledge(5000, status="CREATED")
    old.created_at = NOW - timedelta(hours=2)
    fresh = w.pledge(5000, status="CREATED")
    fresh.created_at = NOW - timedelta(minutes=5)
    w.db.flush()
    out = tick(w, llm)
    assert out == [{"action": "EXPIRED_ORDERS", "count": 1}] and (old.status, fresh.status) == ("EXPIRED", "CREATED")


def test_only_open_campaigns_are_looked_at(w, llm):
    fund(w)
    w.campaign.state = "SETUP"
    assert tick(w, llm) == [] and plans(w) == []


def test_one_broken_campaign_does_not_stop_the_others(w, llm, monkeypatch):
    other = World(w.db, tag="b")
    fund(w)
    for h in (15000, 15000, 10000):
        other.pledge(h)
    real = clock._tick_campaign

    def flaky(db, c, *a):
        if c.id == w.campaign.id:
            raise RuntimeError("boom")
        return real(db, c, *a)

    monkeypatch.setattr(clock, "_tick_campaign", flaky)
    out = tick(w, llm)
    assert {"campaign_id": w.campaign.id, "action": "ERROR"} in out
    assert any(r.get("campaign_id") == other.campaign.id and r["action"] == "CAPTURE" for r in out)


def test_the_guardian_having_no_ai_holds_the_plan_instead_of_approving_it(w):
    fund(w)
    [r] = clock.tick(w.db, now=NOW, reader=FakeReader(w.db), llm=GuardianLLM(None))
    assert r["action"] == "CAPTURE" and r["plan_state"] == "REVIEWED"        # a HOLD: a human must acknowledge it


# =============================== the lead's buttons ===============================

def lead(w):
    return w.lead


def test_close_now_collects_when_the_goal_is_held(w, llm):
    w.campaign.close_policy = "AT_DEADLINE"
    fund(w)
    plan = clock.close_now(w.db, w.campaign, lead(w), now=NOW, reader=FakeReader(w.db), llm=llm)
    assert plan.kind == "CAPTURE_PLEDGES" and plan.proposed_by == f"user:{w.lead.user_id}" and plan.state == "APPROVED"


def test_close_now_without_the_goal_changes_nothing(w, llm):
    fund(w, (15000,))
    with pytest.raises(ops.CampaignError) as e:
        clock.close_now(w.db, w.campaign, lead(w), now=NOW, reader=FakeReader(w.db), llm=llm)
    assert e.value.code == "GOAL_NOT_REACHED" and plans(w) == [] and w.campaign.state == "OPEN"


def test_cancel_releases_every_hold(w, llm):
    fund(w, (15000, 5000))
    plan = clock.cancel(w.db, w.campaign, lead(w), now=NOW, reader=FakeReader(w.db), llm=llm)
    assert plan.kind == "RELEASE_HOLDS" and plan.reason == "LEAD_CANCEL" and plan.proposed_by == f"user:{w.lead.user_id}"
    assert plan.state == "APPROVED" and len(plan.plan_json["steps"]) == 2


def test_cancel_with_no_pledges_is_allowed(w, llm):
    assert clock.cancel(w.db, w.campaign, lead(w), now=NOW, reader=FakeReader(w.db), llm=llm).plan_json["steps"] == []


def test_a_button_refuses_while_another_plan_is_in_flight(w, llm):
    fund(w)
    tick(w, llm)
    for fn in (clock.close_now, clock.cancel):
        with pytest.raises(ops.CampaignError) as e:
            fn(w.db, w.campaign, lead(w), now=NOW, reader=FakeReader(w.db), llm=llm)
        assert e.value.code == "PLAN_IN_PROGRESS"
    assert len(plans(w)) == 1


def test_a_finished_or_blocked_plan_does_not_stop_the_lead_trying_again(w, llm):
    fund(w, (15000, 5000))
    plan = clock.cancel(w.db, w.campaign, lead(w), now=NOW, reader=FakeReader(w.db), llm=llm)
    plan.state = "BLOCKED"
    again = clock.cancel(w.db, w.campaign, lead(w), now=NOW, reader=FakeReader(w.db), llm=llm)
    assert again.id != plan.id and len(plans(w)) == 2


def test_buttons_only_work_on_an_open_campaign(w, llm):
    w.campaign.state = "CAPTURING"
    for fn in (clock.close_now, clock.cancel):
        with pytest.raises(ops.CampaignError) as e:
            fn(w.db, w.campaign, lead(w), now=NOW, reader=FakeReader(w.db), llm=llm)
        assert e.value.code == "CAMPAIGN_STATE"


def failed_round(w, llm):
    fund(w, (15000, 5000))
    plan = clock.cancel(w.db, w.campaign, lead(w), now=NOW, reader=FakeReader(w.db), llm=llm)
    # stand in for the executor and the webhooks: the plan ran and every step was confirmed
    w.campaign.state, w.project.state, plan.state = "FAILED", "CAMPAIGN_FAILED", "DONE"
    w.db.flush()


def test_another_round_starts_in_setup_with_the_same_terms_and_a_fresh_deadline(w, llm):
    w.campaign.min_pledge_cents, w.campaign.suggested_share_cents, w.campaign.close_policy = 700, 9000, "AT_DEADLINE"
    failed_round(w, llm)
    new = clock.relaunch(w.db, w.campaign, w.project, lead(w), now=NOW)
    assert (new.number, new.state, new.goal_cents, new.currency) == (2, "SETUP", GOAL, "USD")
    assert (new.min_pledge_cents, new.suggested_share_cents, new.close_policy) == (700, 9000, "AT_DEADLINE")
    assert new.deadline_at == NOW + timedelta(hours=48) and w.project.state == "CAMPAIGN_SETUP"
    assert w.campaign.state == "FAILED"                                  # the old round keeps its history
    ops.launch(w.db, w.project, new, now=NOW)
    assert new.state == "OPEN" and w.project.state == "PLEDGING"


def test_another_round_only_after_a_failed_one(w, llm):
    with pytest.raises(ops.CampaignError) as e:
        clock.relaunch(w.db, w.campaign, w.project, lead(w), now=NOW)
    assert e.value.code == "CAMPAIGN_STATE"
    failed_round(w, llm)
    clock.relaunch(w.db, w.campaign, w.project, lead(w), now=NOW)
    with pytest.raises(ops.CampaignError):                               # the old round is no longer the latest
        clock.relaunch(w.db, w.campaign, w.project, lead(w), now=NOW)


def test_another_round_needs_the_project_to_be_in_the_failed_state_too(w, llm):
    failed_round(w, llm)
    w.project.state = "PLEDGING"
    with pytest.raises(ops.CampaignError) as e:
        clock.relaunch(w.db, w.campaign, w.project, lead(w), now=NOW)
    assert e.value.code == "PROJECT_STATE" and w.db.query(Campaign).count() == 1


def test_only_the_latest_round_can_be_restarted(w, llm):
    failed_round(w, llm)
    w.db.add(Campaign(project_id=w.project.id, number=2, proposer_member_id=w.lead.id, goal_cents=GOAL,
                      deadline_at=NOW + timedelta(hours=10), state="SETUP"))
    w.db.flush()
    with pytest.raises(ops.CampaignError) as e:
        clock.relaunch(w.db, w.campaign, w.project, lead(w), now=NOW)
    assert e.value.code == "NOT_LATEST"


def test_the_demo_shortcut_pulls_the_deadline_to_now(w):
    clock.expire_deadline_now(w.db, w.campaign, now=NOW)
    assert w.campaign.deadline_at == NOW
    w.campaign.state = "CAPTURED"
    with pytest.raises(ops.CampaignError):
        clock.expire_deadline_now(w.db, w.campaign, now=NOW)


# =============================== over HTTP ===============================

def hdr(u):
    return {"Authorization": f"Bearer {create_token(u)}"}


@pytest.fixture()
def api(w, llm, client):
    w.campaign.deadline_at = datetime.now(timezone.utc) + timedelta(hours=40)
    w.db.commit()
    app.dependency_overrides[paypal_io.get_reader] = lambda: FakeReader(w.db)
    app.dependency_overrides[get_guardian_llm] = lambda: llm
    yield client
    app.dependency_overrides.pop(paypal_io.get_reader, None)
    app.dependency_overrides.pop(get_guardian_llm, None)


def lead_user(w):
    return w.db.get(User, w.project.lead_user_id)


def live_pledge(w, cents):
    p = w.pledge(cents)
    p.honor_until = datetime.now(timezone.utc) + timedelta(hours=60)
    return p


def test_close_over_http(w, api):
    w.campaign.close_policy = "AT_DEADLINE"
    for h in (15000, 15000, 10000):
        live_pledge(w, h)
    w.db.commit()
    r = api.post(f"/api/campaigns/{w.campaign.id}/close", headers=hdr(lead_user(w)))
    assert r.status_code == 200 and r.json()["plan"]["kind"] == "CAPTURE_PLEDGES" and r.json()["plan"]["decision"] == "ALLOW"
    again = api.post(f"/api/campaigns/{w.campaign.id}/close", headers=hdr(lead_user(w)))
    assert again.status_code == 409 and again.json()["error"]["code"] == "PLAN_IN_PROGRESS"


def test_close_without_the_goal_is_a_409_with_a_reason(w, api):
    live_pledge(w, 5000)
    w.db.commit()
    r = api.post(f"/api/campaigns/{w.campaign.id}/close", headers=hdr(lead_user(w)))
    assert r.status_code == 409 and r.json()["error"]["code"] == "GOAL_NOT_REACHED"
    assert w.db.query(MoneyPlan).count() == 0


def test_cancel_over_http(w, api):
    live_pledge(w, 5000)
    w.db.commit()
    r = api.post(f"/api/campaigns/{w.campaign.id}/cancel", headers=hdr(lead_user(w)))
    assert r.status_code == 200 and r.json()["plan"]["kind"] == "RELEASE_HOLDS" and r.json()["state"] == "OPEN"


def test_only_the_lead_may_use_the_buttons(w, api):
    s = User(email="s@x.com", display_name="S")
    w.db.add(s)
    w.db.flush()
    w.db.add(ProjectMember(project_id=w.project.id, user_id=s.id, role="SPONSOR"))
    w.db.commit()
    for path in ("close", "cancel", "relaunch"):
        assert api.post(f"/api/campaigns/{w.campaign.id}/{path}", headers=hdr(s)).status_code == 403
        assert api.post(f"/api/campaigns/{w.campaign.id}/{path}").status_code == 401
    assert api.post("/api/campaigns/999/cancel", headers=hdr(s)).status_code == 404
    assert w.db.query(MoneyPlan).count() == 0


def test_relaunch_over_http(w, api, llm):
    failed_round(w, llm)
    w.db.commit()
    r = api.post(f"/api/campaigns/{w.campaign.id}/relaunch", headers=hdr(lead_user(w)))
    assert r.status_code == 201 and r.json()["number"] == 2 and r.json()["state"] == "SETUP"
    assert api.post(f"/api/campaigns/{w.campaign.id}/relaunch", headers=hdr(lead_user(w))).status_code == 409


def test_demo_shortcuts_work_in_demo_mode_and_vanish_outside_it(w, api, monkeypatch):
    live_pledge(w, 5000)
    w.db.commit()
    h = hdr(lead_user(w))
    r = api.post(f"/api/demo/campaigns/{w.campaign.id}/expire", headers=h)
    assert r.status_code == 200 and r.json()["seconds_left"] == 0
    out = api.post("/api/demo/clock/tick", headers=h).json()["actions"]
    assert out[0]["action"] == "RELEASE" and out[0]["reason"] == "DEADLINE_MISSED"
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    assert api.post(f"/api/demo/campaigns/{w.campaign.id}/expire", headers=h).status_code == 404
    assert api.post("/api/demo/clock/tick", headers=h).status_code == 404


def test_the_clock_is_part_of_the_apps_recurring_chores(db, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app.main import build_runner
    seen = []
    monkeypatch.setattr(clock, "run_periodic", lambda factory: seen.append(factory))
    monkeypatch.setattr(get_settings(), "clock_interval_seconds", 23)
    factory = sessionmaker(bind=db.get_bind())
    runner = build_runner(get_settings(), factory)
    assert runner.periodic[1][0] == 23
    runner.periodic[1][1]()
    assert seen == [factory]


def test_the_web_apps_types_match_what_the_lead_buttons_answer(w, api):
    from tests.test_frontend_contract import fields_of, read
    types = read("lib/types.ts")
    live_pledge(w, 5000)
    w.db.commit()
    got = api.post(f"/api/campaigns/{w.campaign.id}/cancel", headers=hdr(lead_user(w))).json()
    assert set(got["plan"]) == fields_of(types, "PlanSummary") and "plan" in fields_of(types, "CampaignActionResult")
    assert set(got) - {"plan", "lead"} <= fields_of(types, "CampaignView")
    actions = api.post("/api/demo/clock/tick", headers=hdr(lead_user(w))).json()
    assert set(actions) == {"actions"}
