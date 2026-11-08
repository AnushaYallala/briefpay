from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agents.ba_agent import set_ba_agents
from app.agents.brd_generator import set_brd_generator
from app.config import get_settings
from app.models import Campaign, LedgerEntry, Pledge, Project
from tests.test_ba_api import Team, login
from tests.test_contract import accept, contracting, offer


@pytest.fixture()
def t(client, db):
    team = Team(client, db)
    yield team
    set_ba_agents(None)
    set_brd_generator(None)


def signed(t):
    """Contract signed, project in CAMPAIGN_SETUP, all through the real endpoints."""
    contracting(t)
    assert accept(t, offer(t).json()).status_code == 200
    assert t.client.get(f"/api/projects/{t.pid}", headers=t.lakshmi).json()["state"] == "CAMPAIGN_SETUP"


def iso(hours=48, minutes=0):
    return (datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes)).isoformat()


def create(t, who=None, **body):
    body.setdefault("deadline_at", iso(48))
    return t.client.post(f"/api/projects/{t.pid}/campaigns", headers=who or t.lakshmi, json=body)


def view(t, cid, who=None):
    return t.client.get(f"/api/campaigns/{cid}", headers=who or {}).json()


def launch(t, cid, who=None):
    return t.client.post(f"/api/campaigns/{cid}/launch", headers=who or t.lakshmi)


def project_state(t):
    return t.client.get(f"/api/projects/{t.pid}", headers=t.lakshmi).json()["state"]


# ---------------- setup ----------------

def test_the_lead_sets_up_a_campaign_whose_goal_comes_from_the_contract(t, client):
    signed(t)
    r = create(t)
    assert r.status_code == 201
    c = r.json()
    assert (c["number"], c["state"], c["goal_cents"], c["fee_reserve_cents"], c["currency"]) == (1, "SETUP", 40000, 0, "USD")
    assert (c["min_pledge_cents"], c["close_policy"], c["suggested_share_cents"]) == (500, "EARLY_ON_GOAL", None)
    assert c["opens_at"] is None and c["seconds_left"] == 0 and c["pledged_cents"] == 0 and c["pledge_count"] == 0
    assert c["remaining_need_cents"] == 40000 and c["held_not_charged"] is True
    lead = c["lead"]
    assert lead["can_launch"] is True and lead["launch_blockers"] == [] and lead["earliest_honor_until"] is None
    now = datetime.now(timezone.utc)
    assert abs(datetime.fromisoformat(lead["deadline_latest"]) - (now + timedelta(hours=70))) < timedelta(minutes=2)
    assert abs(datetime.fromisoformat(lead["deadline_earliest"]) - (now + timedelta(hours=1))) < timedelta(minutes=2)
    assert project_state(t) == "CAMPAIGN_SETUP", "setting up does not open pledging"


def test_payout_fees_are_added_to_the_goal(t, client, monkeypatch):
    signed(t)
    monkeypatch.setattr(get_settings(), "fee_reserve_per_item_cents", 25)
    c = create(t).json()
    assert (c["goal_cents"], c["fee_reserve_cents"]) == (40025, 25)
    assert c["remaining_need_cents"] == 40025


def test_the_lead_can_choose_the_minimum_pledge_share_and_close_policy(t, client):
    signed(t)
    c = create(t, min_pledge_cents=1000, suggested_share_cents=13400, close_policy="AT_DEADLINE").json()
    assert (c["min_pledge_cents"], c["suggested_share_cents"], c["close_policy"]) == (1000, 13400, "AT_DEADLINE")


@pytest.mark.parametrize("body,code", [
    ({"deadline_at": "past"}, None), ({}, None), ({"close_policy": "WHENEVER"}, None), ({"min_pledge_cents": -1}, None),
    ({"min_pledge_cents": 99}, "BAD_MIN_PLEDGE"), ({"min_pledge_cents": 40001}, "BAD_MIN_PLEDGE"),
    ({"suggested_share_cents": 499}, "BAD_SHARE"), ({"suggested_share_cents": 40001}, "BAD_SHARE"),
])
def test_bad_choices_are_refused_and_nothing_is_created(t, client, db, body, code):
    signed(t)
    payload = {"deadline_at": iso(48), **body}
    if body == {}:
        payload = {}
    r = client.post(f"/api/projects/{t.pid}/campaigns", headers=t.lakshmi, json=payload)
    assert r.status_code == 422
    if code:
        assert r.json()["error"]["code"] == code
    assert db.query(Campaign).count() == 0


@pytest.mark.parametrize("hours,minutes,code", [
    (-5, 0, "DEADLINE_TOO_SOON"), (0, 30, "DEADLINE_TOO_SOON"), (71, 0, "DEADLINE_TOO_LATE"), (72, 0, "DEADLINE_TOO_LATE"), (240, 0, "DEADLINE_TOO_LATE"),
])
def test_the_deadline_must_fit_the_pledge_window(t, client, db, hours, minutes, code):
    signed(t)
    r = create(t, deadline_at=iso(hours, minutes))
    assert r.status_code == 422 and r.json()["error"]["code"] == code
    assert db.query(Campaign).count() == 0
    if code == "DEADLINE_TOO_LATE":
        assert "3 days" in r.json()["error"]["message"] and "70" in r.json()["error"]["message"]


def test_the_edges_of_the_window_are_accepted(t, client):
    signed(t)
    assert create(t, deadline_at=iso(1, 5)).status_code == 201
    assert create(t, deadline_at=iso(69, 55)).status_code == 201


def test_a_deadline_in_another_timezone_is_understood(t, client):
    signed(t)
    ist = timezone(timedelta(hours=5, minutes=30))
    local = (datetime.now(timezone.utc) + timedelta(hours=30)).astimezone(ist).isoformat()
    c = create(t, deadline_at=local).json()
    assert abs(datetime.fromisoformat(c["deadline_at"]) - (datetime.now(timezone.utc) + timedelta(hours=30))) < timedelta(minutes=2)


def test_setting_up_again_updates_the_same_campaign(t, client, db):
    signed(t)
    first = create(t).json()
    second = create(t, deadline_at=iso(24), min_pledge_cents=1000).json()
    assert second["id"] == first["id"] and second["number"] == 1 and second["min_pledge_cents"] == 1000
    assert db.query(Campaign).count() == 1


def test_only_the_lead_sets_up_and_only_after_the_contract_is_signed(t, client):
    r = create(t)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROJECT_STATE"          # nothing signed yet
    contracting(t)
    offer(t)
    assert create(t).json()["error"]["code"] == "PROJECT_STATE"                            # offered but not signed
    accept(t, offer(t).json())
    for who in (t.ravi, t.meena, t.arjun, login(client, "stranger@example.com", "S")):
        assert create(t, who=who).status_code == 403
    assert client.post(f"/api/projects/{t.pid}/campaigns", json={"deadline_at": iso(48)}).status_code == 401


def test_defence_in_depth_setup_checks_the_contract_and_live_campaigns_itself(t, client, db):
    """Normal flow makes these unreachable (the project state already prevents them); the rules still guard themselves."""
    from app.models import Contract
    signed(t)
    db.get(Contract, db.query(Contract).one().id).signed_at = None                         # project says CAMPAIGN_SETUP, contract says unsigned
    db.commit()
    r = create(t)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONTRACT_NOT_SIGNED" and db.query(Campaign).count() == 0
    db.get(Contract, db.query(Contract).one().id).signed_at = datetime.now(timezone.utc)
    db.commit()
    cid = create(t).json()["id"]
    for live in ("OPEN", "CAPTURING", "FAILING"):
        db.get(Campaign, cid).state = live                                                  # a live round while the project says SETUP
        db.commit()
        r = create(t, deadline_at=iso(10))
        assert r.status_code == 409 and r.json()["error"]["code"] == "CAMPAIGN_LIVE"
    assert db.query(Campaign).count() == 1


# ---------------- the public view ----------------

def test_anyone_can_see_a_campaign_but_only_the_lead_gets_the_controls(t, client):
    signed(t)
    cid = create(t).json()["id"]
    pub = client.get(f"/api/campaigns/{cid}")
    assert pub.status_code == 200 and "lead" not in pub.json() and "@" not in pub.text
    assert pub.json()["project_title"] == "Velugu Cove website"
    assert "lead" not in view(t, cid, t.ravi) and "lead" not in view(t, cid, t.arjun)
    assert "lead" in view(t, cid, t.lakshmi)
    assert client.get("/api/campaigns/9999").json()["error"]["code"] == "CAMPAIGN_NOT_FOUND"
    assert client.get(f"/api/campaigns/{cid}", headers={"Authorization": "Bearer junk"}).status_code == 401


# ---------------- launch ----------------

def test_launching_opens_pledging_and_starts_the_clock(t, client, db):
    signed(t)
    c = create(t, deadline_at=iso(48)).json()
    r = launch(t, c["id"])
    assert r.status_code == 200
    v = r.json()
    assert v["state"] == "OPEN" and v["opens_at"] is not None
    assert abs(datetime.fromisoformat(v["opens_at"]) - datetime.now(timezone.utc)) < timedelta(minutes=1)
    assert 47 * 3600 < v["seconds_left"] <= 48 * 3600 and v["held_not_charged"] is True
    assert v["lead"]["can_launch"] is False and v["lead"]["launch_blockers"] == []
    assert project_state(t) == "PLEDGING"
    memos = [(e.ref_type, e.meta_json["from"], e.meta_json["to"]) for e in db.scalars(select(LedgerEntry).order_by(LedgerEntry.seq))
             if e.type == "STATE_CHANGE" and e.meta_json.get("to") in ("OPEN", "PLEDGING")]
    assert memos == [("campaign", "SETUP", "OPEN"), ("project", "CAMPAIGN_SETUP", "PLEDGING")]
    card = client.get(f"/api/projects/{t.pid}").json()["campaign"]
    assert (card["state"], card["goal_cents"], card["pledged_cents"], card["pledge_count"]) == ("OPEN", 40000, 0, 0)


def test_a_launched_campaign_cannot_be_launched_or_set_up_again(t, client):
    signed(t)
    cid = create(t).json()["id"]
    launch(t, cid)
    again = launch(t, cid)
    assert again.status_code == 409 and again.json()["error"]["code"] == "CAMPAIGN_STATE"
    r = create(t)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROJECT_STATE"          # the project is PLEDGING now


def test_only_the_lead_launches(t, client):
    signed(t)
    cid = create(t).json()["id"]
    for who in (t.ravi, t.meena, t.arjun, login(client, "stranger@example.com", "S")):
        assert launch(t, cid, who).status_code == 403
    assert client.post(f"/api/campaigns/{cid}/launch").status_code == 401
    assert view(t, cid)["state"] == "SETUP"


def test_a_deadline_that_passed_while_waiting_blocks_the_launch_and_says_why(t, client, db):
    signed(t)
    c = create(t).json()
    db.get(Campaign, c["id"]).deadline_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    lead = view(t, c["id"], t.lakshmi)["lead"]
    assert lead["can_launch"] is False and any("at least 1 hour" in b for b in lead["launch_blockers"])
    r = launch(t, c["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "DEADLINE_TOO_SOON"
    assert view(t, c["id"])["state"] == "SETUP" and project_state(t) == "CAMPAIGN_SETUP"


def test_a_deadline_beyond_the_honor_window_cannot_be_launched(t, client, db):
    signed(t)
    c = create(t).json()
    db.get(Campaign, c["id"]).deadline_at = datetime.now(timezone.utc) + timedelta(hours=71)
    db.commit()
    r = launch(t, c["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "DEADLINE_TOO_LATE"
    assert view(t, c["id"])["state"] == "SETUP"


def test_the_launch_is_blocked_when_the_project_is_not_at_the_campaign_stage(t, client, db):
    signed(t)
    c = create(t).json()
    db.get(Project, t.pid).state = "CONTRACTING"
    db.commit()
    assert "CONTRACTING" in view(t, c["id"], t.lakshmi)["lead"]["launch_blockers"][0]
    r = launch(t, c["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "CANNOT_LAUNCH" and "CONTRACTING" in r.json()["error"]["message"]


def test_a_late_launch_still_respects_the_window_measured_from_opening(t, client, db):
    signed(t)
    c = create(t, deadline_at=iso(69, 50)).json()                                           # valid when set
    db.get(Campaign, c["id"]).deadline_at = datetime.now(timezone.utc) + timedelta(hours=69, minutes=55)
    db.commit()
    assert launch(t, c["id"]).status_code == 200                                            # still within 70 h of opening


# ---------------- what the public sees while pledging ----------------

def test_progress_counts_holds_not_money_and_the_lead_sees_the_honor_deadline(t, client, db):
    signed(t)
    cid = create(t).json()["id"]
    launch(t, cid)
    honor = datetime.now(timezone.utc) + timedelta(hours=60)
    for n, (status, amount, captured) in enumerate([("AUTHORIZED", 15000, 0), ("AUTHORIZED", 10000, 0), ("CREATED", 5000, 0), ("VOIDED", 7000, 0)]):
        db.add(Pledge(campaign_id=cid, project_id=t.pid, display_name=f"P{n}", amount_cents=amount, status=status, paypal_order_id=f"O{n}",
                      paypal_authorization_id=f"A{n}" if status == "AUTHORIZED" else None, honor_until=honor + timedelta(hours=n),
                      authorized_at=datetime.now(timezone.utc) if status == "AUTHORIZED" else None))
    db.commit()
    v = view(t, cid)
    assert (v["pledged_cents"], v["pledge_count"], v["remaining_need_cents"]) == (25000, 2, 15000)
    assert v["held_not_charged"] is True and "lead" not in v
    assert datetime.fromisoformat(view(t, cid, t.lakshmi)["lead"]["earliest_honor_until"]) == honor.replace(microsecond=honor.microsecond)


def test_after_capture_the_page_stops_saying_held_and_shows_the_captured_amounts(t, client, db):
    signed(t)
    cid = create(t).json()["id"]
    launch(t, cid)
    db.add(Pledge(campaign_id=cid, project_id=t.pid, display_name="P", amount_cents=42000, captured_cents=40000, status="CAPTURED",
                  paypal_order_id="O1", paypal_authorization_id="A1"))
    db.get(Campaign, cid).state = "CAPTURED"
    db.commit()
    v = view(t, cid)
    assert v["pledged_cents"] == 40000 and v["held_not_charged"] is False and v["remaining_need_cents"] == 0 and v["seconds_left"] == 0
