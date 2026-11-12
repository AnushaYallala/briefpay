from datetime import datetime, timedelta, timezone

import pytest

from app.agents.ba_agent import set_ba_agents
from app.agents.brd_generator import set_brd_generator
from app.models import Campaign, Pledge, ProjectMember, StrategistReport
from tests.test_ba_api import Team, login
from tests.test_campaigns_api import create, iso, launch, signed


@pytest.fixture()
def t(client, db):
    team = Team(client, db)
    yield team
    set_ba_agents(None)
    set_brd_generator(None)


def hopes(t, db, lakshmi=15000, ravi=15000, meena=10000, statuses=("VIEWED", "INVITED", "INVITED")):
    """What each sponsor told the lead they would pledge (private planning data), and whether they have opened the link.
    Statuses are set explicitly so the numbers do not depend on incidental page views: the demo has Lakshmi VIEWED (.55)
    and Ravi and Meena INVITED (.30)."""
    for (name, cents), status in zip((("Lakshmi", lakshmi), ("Ravi", ravi), ("Meena", meena)), statuses):
        member = db.get(ProjectMember, t.m[name])
        member.expected_pledge_cents, member.invite_status = cents, status
    db.commit()


def staged(t, db, hours=48, **hope):
    signed(t)
    hopes(t, db, **hope)
    return create(t, deadline_at=iso(hours)).json()["id"]


def run_report(t, cid, who=None):
    r = t.client.post(f"/api/campaigns/{cid}/strategist/run", headers=who or t.lakshmi)
    assert r.status_code == 202, r.text
    t.run_job()
    return t.client.get(f"/api/campaigns/{cid}/strategist", headers=t.lakshmi).json()


def apply(t, cid, **body):
    return t.client.post(f"/api/campaigns/{cid}/strategist/apply", headers=t.lakshmi, json=body)


def add_pledge(db, cid, pid, *, member=None, supporter=None, cents=10000, hours_ago=1, status="AUTHORIZED", n=[0]):
    n[0] += 1
    when = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    db.add(Pledge(campaign_id=cid, project_id=pid, member_id=member, supporter_user_id=supporter, display_name=f"P{n[0]}", amount_cents=cents,
                  status=status, paypal_order_id=f"SO{n[0]}", paypal_authorization_id=f"SA{n[0]}", authorized_at=when, honor_until=when + timedelta(days=3)))
    db.commit()


# ---------------- the report ----------------

def test_a_report_has_the_forecast_the_deadline_advice_and_ranked_nudges(t, client, db):
    cid = staged(t, db)
    rep = run_report(t, cid)
    f, sug = rep["forecast"], rep["suggestions"]
    assert f["label"] == "estimate (heuristic)" and f["goal_cents"] == 40000 and f["pledged_cents"] == 0 and f["gap_cents"] == 40000
    # Lakshmi is VIEWED (.55 x 15000), Ravi INVITED (.30 x 15000), Meena INVITED (.30 x 10000): 8250 + 4500 + 3000
    assert f["expected_invitees_cents"] == 15750 and f["probability"] == 0.0256
    assert sug["kind"] == "SETUP" and sug["campaign_state"] == "SETUP"
    assert [x["name"] for x in sug["nudge_targets"]] == ["Lakshmi", "Ravi", "Meena"] and sug["nudge_targets"][0]["score"] == 8250
    # no AI is configured in tests, so the wording is the code's template (T-47): honest, numbered from the facts, flagged
    assert rep["narrative"]["source"] == "TEMPLATE" and rep["narrative"]["flags"] == ["AI_UNAVAILABLE"]
    assert rep["narrative"]["headline"] == "About a 3% chance of reaching the goal (estimate (heuristic))"
    assert [n["name"] for n in rep["nudges"]] == ["Lakshmi", "Ravi", "Meena"] and all(n["source"] == "TEMPLATE" and "/campaign?id=" in n["message"] for n in rep["nudges"])


def test_a_weak_start_is_advised_to_run_longer_and_a_strong_one_to_keep_the_default(t, client, db):
    cid = staged(t, db, lakshmi=5000, ravi=5000, meena=5000)
    weak = run_report(t, cid)["suggestions"]["deadline"]
    latest = datetime.fromisoformat(weak["deadline_at"])
    assert abs(latest - (datetime.now(timezone.utc) + timedelta(hours=70))) < timedelta(minutes=2) and weak["initial_probability"] < 0.5
    hopes(t, db, lakshmi=30000, ravi=30000, meena=30000, statuses=("VIEWED", "VIEWED", "VIEWED"))    # .55 x 90000 = 49500 > goal
    strong = run_report(t, cid)["suggestions"]["deadline"]
    assert strong["hours"] == 48 and strong["initial_probability"] >= 0.5
    hopes(t, db, lakshmi=30000, ravi=30000, meena=30000)                                              # same hopes, but two have not opened the link
    assert run_report(t, cid)["suggestions"]["deadline"]["hours"] == 70.0


def test_the_report_is_for_the_lead_only(t, client, db):
    cid = staged(t, db)
    for who in (t.ravi, t.meena, t.arjun, login(client, "stranger@example.com", "S")):
        assert client.post(f"/api/campaigns/{cid}/strategist/run", headers=who).status_code == 403
        assert client.get(f"/api/campaigns/{cid}/strategist", headers=who).status_code == 403
        assert client.post(f"/api/campaigns/{cid}/strategist/apply", headers=who, json={}).status_code == 403
    assert client.get(f"/api/campaigns/{cid}/strategist").status_code == 401
    assert client.get("/api/campaigns/9999/strategist", headers=t.lakshmi).json()["error"]["code"] == "CAMPAIGN_NOT_FOUND"


def test_reading_before_running_is_a_clear_404(t, client, db):
    cid = staged(t, db)
    r = client.get(f"/api/campaigns/{cid}/strategist", headers=t.lakshmi)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NO_REPORT"


def test_the_same_data_gives_the_same_forecast(t, client, db):
    cid = staged(t, db)
    a, b = run_report(t, cid)["forecast"], run_report(t, cid)["forecast"]
    assert {k: v for k, v in a.items() if k != "hours_left"} == {k: v for k, v in b.items() if k != "hours_left"}
    assert db.query(StrategistReport).count() == 2, "each run is kept as history"


def test_the_job_reports_the_probability(t, client, db):
    cid = staged(t, db)
    job_id = client.post(f"/api/campaigns/{cid}/strategist/run", headers=t.lakshmi).json()["job_id"]
    t.run_job()
    res = client.get(f"/api/jobs/{job_id}", headers=t.lakshmi).json()
    assert res["state"] == "DONE" and res["result"]["probability"] == client.get(f"/api/campaigns/{cid}/strategist", headers=t.lakshmi).json()["forecast"]["probability"]


@pytest.mark.parametrize("state", ["CAPTURING", "CAPTURED", "FAILING", "FAILED", "CANCELLED"])
def test_there_is_nothing_to_advise_once_the_campaign_has_ended(t, client, db, state):
    cid = staged(t, db)
    db.get(Campaign, cid).state = state
    db.commit()
    r = client.post(f"/api/campaigns/{cid}/strategist/run", headers=t.lakshmi)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CAMPAIGN_STATE"


# ---------------- an open campaign ----------------

def test_who_has_pledged_stops_being_nudged_and_counts_as_pledged(t, client, db):
    cid = staged(t, db)
    launch(t, cid)
    add_pledge(db, cid, t.pid, member=t.m["Lakshmi"], cents=15000)
    rep = run_report(t, cid)
    assert rep["forecast"]["pledged_cents"] == 15000 and rep["forecast"]["gap_cents"] == 25000
    assert [x["name"] for x in rep["suggestions"]["nudge_targets"]] == ["Ravi", "Meena"]
    assert rep["forecast"]["expected_invitees_cents"] == 7500                          # .30 x 15000 (Ravi) + .30 x 10000 (Meena)


def test_recent_supporter_pledges_raise_the_forecast_but_sponsor_pledges_do_not_count_as_momentum(t, client, db):
    cid = staged(t, db)
    launch(t, cid)
    stranger = login(client, "fan@example.com", "Fan")
    from app.models import User
    fan_id = db.query(User).filter(User.email == "fan@example.com").one().id
    base = run_report(t, cid)["forecast"]
    add_pledge(db, cid, t.pid, member=t.m["Ravi"], cents=6000, hours_ago=1)
    assert run_report(t, cid)["forecast"]["expected_open_cents"] == 0
    add_pledge(db, cid, t.pid, supporter=fan_id, cents=6000, hours_ago=1)
    after = run_report(t, cid)["forecast"]
    assert after["expected_open_cents"] > 0 and after["probability"] > base["probability"]
    assert stranger is not None


def test_a_failing_campaign_with_under_a_day_left_is_offered_one_extension(t, client, db):
    cid = staged(t, db, hours=10, lakshmi=0, ravi=0, meena=0)
    launch(t, cid)
    sug = run_report(t, cid)["suggestions"]
    assert sug["kind"] == "EXTEND"
    opens = datetime.fromisoformat(client.get(f"/api/campaigns/{cid}").json()["opens_at"])
    assert datetime.fromisoformat(sug["deadline"]["deadline_at"]) == opens + timedelta(hours=70)


def test_no_extension_is_offered_with_plenty_of_time_or_a_healthy_forecast(t, client, db):
    cid = staged(t, db, hours=48, lakshmi=0, ravi=0, meena=0)
    launch(t, cid)
    assert run_report(t, cid)["suggestions"]["kind"] is None                          # 48 h left
    add_pledge(db, cid, t.pid, member=t.m["Lakshmi"], cents=39000)
    db.get(Campaign, cid).deadline_at = datetime.now(timezone.utc) + timedelta(hours=5)
    db.commit()
    # 39000 of 40000 on its own is still at risk (p = .46), so with 5 h left the right advice IS to extend ...
    assert run_report(t, cid)["suggestions"]["kind"] == "EXTEND"
    # ... but with Ravi expected to give 15000 more (.30 x 15000), the projection passes the goal (p = .63): no extension
    hopes(t, db, lakshmi=0, ravi=15000, meena=0)
    healthy = run_report(t, cid)
    assert healthy["forecast"]["probability"] >= 0.6 and healthy["suggestions"]["kind"] is None


# ---------------- applying advice ----------------

def test_in_setup_the_lead_can_apply_any_deadline_the_window_allows(t, client, db):
    cid = staged(t, db)
    r = apply(t, cid, deadline_at=iso(60))
    assert r.status_code == 200
    got = datetime.fromisoformat(r.json()["deadline_at"])
    assert abs(got - (datetime.now(timezone.utc) + timedelta(hours=60))) < timedelta(minutes=2) and r.json()["state"] == "SETUP"
    assert apply(t, cid, deadline_at=iso(71)).json()["error"]["code"] == "DEADLINE_TOO_LATE"
    assert apply(t, cid, deadline_at=iso(0, 30)).json()["error"]["code"] == "DEADLINE_TOO_SOON"


def test_applying_without_a_deadline_uses_the_latest_suggestion_or_explains_there_is_none(t, client, db):
    cid = staged(t, db, lakshmi=5000, ravi=5000, meena=5000)
    none = apply(t, cid)
    assert none.status_code == 409 and none.json()["error"]["code"] == "NO_SUGGESTION"
    run_report(t, cid)
    r = apply(t, cid)
    assert r.status_code == 200
    assert abs(datetime.fromisoformat(r.json()["deadline_at"]) - (datetime.now(timezone.utc) + timedelta(hours=70))) < timedelta(minutes=2)


def test_an_open_campaign_can_be_extended_exactly_once_and_never_shortened(t, client, db):
    cid = staged(t, db, hours=10)
    launch(t, cid)
    before = datetime.fromisoformat(client.get(f"/api/campaigns/{cid}").json()["deadline_at"])
    shorter = apply(t, cid, deadline_at=iso(5))
    assert shorter.status_code == 409 and shorter.json()["error"]["code"] == "NOT_AN_EXTENSION"
    too_far = apply(t, cid, deadline_at=iso(71))
    assert too_far.status_code == 422 and too_far.json()["error"]["code"] == "DEADLINE_TOO_LATE"
    ok = apply(t, cid, deadline_at=iso(30))
    assert ok.status_code == 200 and datetime.fromisoformat(ok.json()["deadline_at"]) > before
    again = apply(t, cid, deadline_at=iso(40))
    assert again.status_code == 409 and again.json()["error"]["code"] == "EXTENSION_USED"
    marker = db.query(StrategistReport).order_by(StrategistReport.id.desc()).first().suggestions_json["applied_extension"]
    assert set(marker) == {"from", "to", "at"}


def test_the_honor_limit_is_counted_from_when_the_campaign_opened_not_from_now(t, client, db):
    """PayPal's 3-day guarantee runs from the first possible hold, i.e. from opening. A campaign that opened 30 h ago can
    run until opens + 70 h = 40 h from now, not 70 h from now."""
    cid = staged(t, db, hours=10)
    launch(t, cid)
    c = db.get(Campaign, cid)
    now = datetime.now(timezone.utc)
    c.opens_at, c.deadline_at = now - timedelta(hours=30), now + timedelta(hours=10)
    db.commit()
    too_far = apply(t, cid, deadline_at=iso(50))                       # = opens + 80 h
    assert too_far.status_code == 422 and too_far.json()["error"]["code"] == "DEADLINE_TOO_LATE"
    assert apply(t, cid, deadline_at=iso(39)).status_code == 200       # = opens + 69 h
    sug = run_report(t, cid)["suggestions"]
    assert sug["kind"] is None, "after using the one extension nothing more is suggested"


def test_a_report_job_that_runs_after_the_campaign_ended_fails_cleanly(t, client, db):
    """The service guards itself: a job queued while OPEN may run after the campaign has ended."""
    cid = staged(t, db)
    launch(t, cid)
    job_id = client.post(f"/api/campaigns/{cid}/strategist/run", headers=t.lakshmi).json()["job_id"]
    db.get(Campaign, cid).state = "FAILED"
    db.commit()
    t.run_job()
    job = client.get(f"/api/jobs/{job_id}", headers=t.lakshmi).json()
    assert job["state"] == "QUEUED" and "StrategistError" in job["error"] and "FAILED" in job["error"]      # queued for a retry
    assert db.query(StrategistReport).count() == 0
    from app.services import strategist_service as svc
    with pytest.raises(svc.StrategistError) as e:
        svc.compute(db, db.get(Campaign, cid), datetime.now(timezone.utc))
    assert e.value.code == "CAMPAIGN_STATE"


def test_after_an_extension_the_strategist_stops_suggesting_another(t, client, db):
    cid = staged(t, db, hours=10, lakshmi=0, ravi=0, meena=0)
    launch(t, cid)
    assert run_report(t, cid)["suggestions"]["kind"] == "EXTEND"
    assert apply(t, cid).status_code == 200                                              # applies the suggestion
    db.get(Campaign, cid).deadline_at = datetime.now(timezone.utc) + timedelta(hours=5)
    db.commit()
    assert run_report(t, cid)["suggestions"]["kind"] is None


def test_the_deadline_cannot_be_changed_once_the_campaign_has_ended(t, client, db):
    cid = staged(t, db)
    db.get(Campaign, cid).state = "FAILED"
    db.commit()
    r = apply(t, cid, deadline_at=iso(20))
    assert r.status_code == 409 and r.json()["error"]["code"] == "CAMPAIGN_STATE"
