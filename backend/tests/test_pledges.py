"""Taking a pledge: the service (gate -> PayPal order -> hold), the board, and the endpoints. PayPal is a fake that records calls."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.auth import create_token
from app.main import app
from app.models import LedgerEntry, Pledge, ProjectMember, User
from app.services import paypal_io
from app.services import pledge_service as svc
from app.services import pledge_state
from app.services.paypal_io import PayPalWriteError
from tests.factories import GOAL, NOW, World


class FakeOrders:
    """Records every call. `hold` can be changed to make PayPal answer differently."""

    def __init__(self):
        self.created, self.authorized, self.amounts = [], [], {}
        self.hold = {}                 # overrides for the authorization PayPal reports: status / amount_cents / currency
        self.create_error = self.authorize_error = None
        self.no_authorization = False

    def create_authorize_order(self, amount_cents, currency, custom_id, description, request_id):
        if self.create_error:
            raise self.create_error
        order_id = f"ORDER-{len(self.created) + 1}"
        self.created.append({"amount_cents": amount_cents, "currency": currency, "custom_id": custom_id,
                             "description": description, "request_id": request_id, "id": order_id})
        self.amounts[order_id] = amount_cents
        return {"id": order_id, "status": "CREATED"}

    def authorize_order(self, order_id, request_id):
        if self.authorize_error:
            raise self.authorize_error
        self.authorized.append({"order_id": order_id, "request_id": request_id})
        auth = None if self.no_authorization else {"id": f"AUTH-{order_id}", "status": "CREATED", "amount_cents": self.amounts[order_id],
                                                  "currency": "USD", "expiration_time": None, **self.hold}
        return {"order_id": order_id, "status": "COMPLETED", "authorization": auth, "payer_email": "buyer@sandbox.example", "payer_id": "PAYER1"}


@pytest.fixture()
def w(db):
    return World(db)


@pytest.fixture()
def orders():
    return FakeOrders()


def supporter(w, name="Meena", role=None):
    u = User(email=f"{name.lower()}@x.com", display_name=name)
    w.db.add(u)
    w.db.flush()
    if role:
        w.db.add(ProjectMember(project_id=w.project.id, user_id=u.id, role=role))
        w.db.flush()
    return u


def start(w, orders, u, cents=5000, name=None, now=NOW):
    return svc.start_pledge(w.db, w.campaign, u, amount_cents=cents, display_name=name, orders=orders, now=now)


def refused(fn, code):
    with pytest.raises(svc.PledgeError) as e:
        fn()
    assert e.value.code == code
    return e.value


# =============================== starting ===============================

def test_a_pledge_starts_as_created_with_the_order_paypal_returned(w, orders):
    u = supporter(w)
    p = start(w, orders, u, 5000, "  Meena   K ")
    assert (p.status, p.amount_cents, p.display_name, p.paypal_order_id) == ("CREATED", 5000, "Meena K", "ORDER-1")
    assert p.supporter_user_id == u.id and p.member_id is None and p.paypal_authorization_id is None
    [o] = orders.created
    assert o["custom_id"] == f"camp:{w.campaign.id}:pledge:{p.id}" and o["request_id"] == f"order-{p.id}" and o["currency"] == "USD"
    assert "held, not charged" in o["description"]
    assert svc.facts(w.db, w.campaign).held_cents == 0       # nothing is counted until the hold exists


def test_the_display_name_defaults_to_the_users_name(w, orders):
    assert start(w, orders, supporter(w, "Ravi"), 5000).display_name == "Ravi"


def test_the_gate_refuses_before_paypal_is_asked(w, orders):
    u = supporter(w)
    refused(lambda: start(w, orders, supporter(w, "Arjun2", "FREELANCER"), 5000), "FREELANCER_CANNOT_PLEDGE")
    refused(lambda: start(w, orders, u, 100), "BELOW_MINIMUM")
    refused(lambda: start(w, orders, u, GOAL + 100), "ABOVE_NEED")
    refused(lambda: start(w, orders, u, 5000, "\x07"), "BAD_NAME")
    refused(lambda: start(w, orders, u, 5000, "x" * 81), "BAD_NAME")
    refused(lambda: start(w, orders, u, 5000, now=NOW + timedelta(hours=41)), "DEADLINE_PASSED")
    w.campaign.state = "SETUP"
    refused(lambda: start(w, orders, u, 5000), "CAMPAIGN_NOT_OPEN")
    assert orders.created == [] and w.db.query(Pledge).count() == 0


def test_a_goal_that_is_already_held_takes_no_more_pledges(w, orders):
    w.pledge(GOAL)
    refused(lambda: start(w, orders, supporter(w), 5000), "GOAL_REACHED")


def test_ten_attempts_an_hour_then_a_pause(w, orders):
    u = supporter(w)
    for _ in range(10):
        start(w, orders, u, 500)
    e = refused(lambda: start(w, orders, u, 500), "RATE_LIMITED")
    assert e.status == 429 and len(orders.created) == 10
    start(w, orders, supporter(w, "Someone"), 500)            # the limit is per person


def test_a_paypal_failure_is_remembered_as_denied_and_asks_to_be_kept(w, orders):
    orders.create_error = PayPalWriteError("down", transient=True)
    e = refused(lambda: start(w, orders, supporter(w), 5000), "PAYPAL_UNAVAILABLE")
    assert e.keep and e.status == 502
    [p] = w.db.scalars(select(Pledge)).all()
    assert p.status == "DENIED"


def test_a_sponsor_pledge_is_tied_to_their_membership(w, orders):
    u = supporter(w, "Ravi", "SPONSOR")
    m = w.db.scalars(select(ProjectMember).where(ProjectMember.user_id == u.id)).one()
    assert start(w, orders, u).member_id == m.id


# =============================== placing the hold ===============================

def test_authorizing_places_the_hold_and_counts_it(w, orders):
    u = supporter(w)
    p = start(w, orders, u, 5000)
    out = svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW)
    assert out is p and p.status == "AUTHORIZED" and p.paypal_authorization_id == "AUTH-ORDER-1"
    assert (p.payer_email, p.payer_id) == ("buyer@sandbox.example", "PAYER1")
    assert p.authorized_at == NOW and p.honor_until == NOW + timedelta(days=3) and p.valid_until == NOW + timedelta(days=29)
    assert orders.authorized == [{"order_id": "ORDER-1", "request_id": f"authz-{p.id}"}]
    memo = w.db.scalars(select(LedgerEntry).where(LedgerEntry.type == "PLEDGE_AUTHORIZED")).one()
    assert memo.amount_cents == 0 and memo.ref_id == str(p.id)
    assert svc.facts(w.db, w.campaign).held_cents == 5000
    assert w.campaign.goal_reached_at is None


def test_the_hold_that_reaches_the_goal_marks_the_moment(w, orders):
    w.pledge(GOAL - 5000)
    u = supporter(w)
    p = start(w, orders, u, 5000)
    svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW)
    assert w.campaign.goal_reached_at == NOW


def test_a_sponsors_hold_marks_them_as_pledged(w, orders):
    u = supporter(w, "Ravi", "SPONSOR")
    p = start(w, orders, u)
    svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW)
    assert w.db.get(ProjectMember, p.member_id).invite_status == "PLEDGED"


def test_authorizing_twice_asks_paypal_once(w, orders):
    u = supporter(w)
    p = start(w, orders, u)
    svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW)
    svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW)
    assert len(orders.authorized) == 1
    assert w.db.query(LedgerEntry).filter(LedgerEntry.type == "PLEDGE_AUTHORIZED").count() == 1


def test_only_the_owner_can_authorize_and_only_on_that_campaign(w, orders):
    u = supporter(w)
    p = start(w, orders, u)
    refused(lambda: svc.authorize_pledge(w.db, w.campaign, supporter(w, "Other"), order_id=p.paypal_order_id, orders=orders, now=NOW), "FORBIDDEN")
    refused(lambda: svc.authorize_pledge(w.db, w.campaign, u, order_id="NOPE", orders=orders, now=NOW), "PLEDGE_NOT_FOUND")
    assert orders.authorized == [] and p.status == "CREATED"


def test_a_campaign_that_closed_meanwhile_places_no_hold(w, orders):
    u = supporter(w)
    p = start(w, orders, u)
    refused(lambda: svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW + timedelta(hours=41)), "CAMPAIGN_CLOSED")
    w.campaign.state = "FAILING"
    refused(lambda: svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW), "CAMPAIGN_CLOSED")
    assert orders.authorized == [] and p.status == "CREATED"


@pytest.mark.parametrize("hold, code, status", [
    ({"status": "DENIED"}, "PLEDGE_DECLINED", 402),
    ({"status": "PENDING"}, "PLEDGE_DECLINED", 402),
    ({"amount_cents": 4000}, "HOLD_MISMATCH", 409),
    ({"currency": "EUR"}, "HOLD_MISMATCH", 409),
])
def test_a_hold_that_is_not_exactly_what_we_asked_for_is_not_counted(w, orders, hold, code, status):
    u = supporter(w)
    p = start(w, orders, u)
    orders.hold = hold
    e = refused(lambda: svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW), code)
    assert e.status == status and e.keep and p.status == "DENIED" and p.paypal_authorization_id is None
    assert svc.facts(w.db, w.campaign).held_cents == 0
    assert w.db.query(LedgerEntry).filter(LedgerEntry.type == "PLEDGE_AUTHORIZED").count() == 0


def test_no_authorization_in_the_answer_is_a_decline(w, orders):
    u = supporter(w)
    p = start(w, orders, u)
    orders.no_authorization = True
    refused(lambda: svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW), "PLEDGE_DECLINED")
    assert p.status == "DENIED"


def test_a_temporary_paypal_failure_lets_the_supporter_try_again(w, orders):
    u = supporter(w)
    p = start(w, orders, u)
    orders.authorize_error = PayPalWriteError("timeout", transient=True)
    e = refused(lambda: svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW), "PAYPAL_UNAVAILABLE")
    assert not e.keep and p.status == "CREATED"
    orders.authorize_error = None
    assert svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW).status == "AUTHORIZED"


def test_a_refusal_from_paypal_is_a_decline(w, orders):
    u = supporter(w)
    p = start(w, orders, u)
    orders.authorize_error = PayPalWriteError("INSTRUMENT_DECLINED", transient=False)
    e = refused(lambda: svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW), "PLEDGE_DECLINED")
    assert e.keep and e.status == 402 and p.status == "DENIED"


def test_a_denied_or_ended_pledge_cannot_be_authorized_again(w, orders):
    u = supporter(w)
    p = start(w, orders, u)
    p.status = "DENIED"
    refused(lambda: svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW), "PLEDGE_STATE")
    assert orders.authorized == []


# =============================== the board ===============================

def test_the_public_board_hides_emails_and_unfinished_rows(w, orders):
    u = supporter(w)
    p = start(w, orders, u)
    svc.authorize_pledge(w.db, w.campaign, u, order_id=p.paypal_order_id, orders=orders, now=NOW)
    start(w, orders, supporter(w, "Ravi"), 700)                                  # CREATED: never public
    denied = w.pledge(900, status="DENIED")
    pub = svc.board(w.db, w.campaign, lead=False)
    assert [r["display_name"] for r in pub] == ["Meena"] and pub[0]["amount_cents"] == 5000 and pub[0]["status"] == "AUTHORIZED"
    assert "payer_email" not in pub[0] and "honor_until" not in pub[0] and denied.id not in [r["id"] for r in pub]
    lead = svc.board(w.db, w.campaign, lead=True)
    assert [r["status"] for r in lead] == ["AUTHORIZED", "CREATED"] and lead[0]["payer_email"] == "buyer@sandbox.example"
    assert lead[0]["honor_until"].startswith("2026-11-13T12:00")


# =============================== over HTTP ===============================

def hdr(u):
    return {"Authorization": f"Bearer {create_token(u)}"}


@pytest.fixture()
def api(w, orders, client):
    w.campaign.deadline_at = datetime.now(timezone.utc) + timedelta(hours=40)       # the endpoints use the real clock
    w.db.commit()
    app.dependency_overrides[paypal_io.get_orders] = lambda: orders
    yield client
    app.dependency_overrides.pop(paypal_io.get_orders, None)


def test_pledge_over_http_end_to_end(w, orders, api):
    u = supporter(w)
    w.db.commit()
    r = api.post(f"/api/campaigns/{w.campaign.id}/pledges/order", json={"amount_cents": 5000, "display_name": "Meena"}, headers=hdr(u))
    assert r.status_code == 201
    order = r.json()
    assert order["order_id"] == "ORDER-1" and order["status"] == "CREATED" and order["currency"] == "USD"
    r = api.post(f"/api/campaigns/{w.campaign.id}/pledges/authorize", json={"order_id": order["order_id"]}, headers=hdr(u))
    assert r.status_code == 200 and r.json()["status"] == "AUTHORIZED" and r.json()["honor_until"]
    board = api.get(f"/api/campaigns/{w.campaign.id}/pledges").json()
    assert [(p["display_name"], p["amount_cents"], p["status"]) for p in board["pledges"]] == [("Meena", 5000, "AUTHORIZED")]
    assert "@" not in str(board)
    view = api.get(f"/api/campaigns/{w.campaign.id}").json()
    assert view["pledged_cents"] == 5000 and view["pledge_count"] == 1 and view["remaining_need_cents"] == GOAL - 5000
    # a supporter is not a project member: they cannot see the members' details
    assert w.db.scalars(select(ProjectMember).where(ProjectMember.user_id == u.id)).first() is None


def test_the_lead_sees_more_on_the_board(w, orders, api):
    u = supporter(w)
    w.db.commit()
    o = api.post(f"/api/campaigns/{w.campaign.id}/pledges/order", json={"amount_cents": 5000}, headers=hdr(u)).json()
    api.post(f"/api/campaigns/{w.campaign.id}/pledges/authorize", json={"order_id": o["order_id"]}, headers=hdr(u))
    lead = w.db.get(User, w.project.lead_user_id)
    row = api.get(f"/api/campaigns/{w.campaign.id}/pledges", headers=hdr(lead)).json()["pledges"][0]
    assert row["payer_email"] == "buyer@sandbox.example" and row["honor_until"]
    other = api.get(f"/api/campaigns/{w.campaign.id}/pledges", headers=hdr(u)).json()["pledges"][0]
    assert "payer_email" not in other


def test_pledging_needs_a_login_and_a_real_campaign(w, api):
    assert api.post(f"/api/campaigns/{w.campaign.id}/pledges/order", json={"amount_cents": 5000}).status_code == 401
    assert api.post(f"/api/campaigns/{w.campaign.id}/pledges/authorize", json={"order_id": "x"}).status_code == 401
    u = supporter(w)
    w.db.commit()
    r = api.post("/api/campaigns/9999/pledges/order", json={"amount_cents": 5000}, headers=hdr(u))
    assert r.status_code == 404 and r.json()["error"]["code"] == "CAMPAIGN_NOT_FOUND"
    assert api.get("/api/campaigns/9999/pledges").status_code == 404


def test_gate_refusals_use_the_error_shape_and_leave_nothing_behind(w, orders, api):
    u = supporter(w)
    w.db.commit()
    r = api.post(f"/api/campaigns/{w.campaign.id}/pledges/order", json={"amount_cents": 100}, headers=hdr(u))
    assert r.status_code == 422 and r.json()["error"]["code"] == "BELOW_MINIMUM"
    f = supporter(w, "Arjun2", "FREELANCER")
    w.db.commit()
    r = api.post(f"/api/campaigns/{w.campaign.id}/pledges/order", json={"amount_cents": 5000}, headers=hdr(f))
    assert r.status_code == 403 and r.json()["error"]["code"] == "FREELANCER_CANNOT_PLEDGE"
    assert orders.created == [] and w.db.query(Pledge).count() == 0


def test_a_declined_hold_is_remembered_and_answers_402(w, orders, api):
    u = supporter(w)
    w.db.commit()
    o = api.post(f"/api/campaigns/{w.campaign.id}/pledges/order", json={"amount_cents": 5000}, headers=hdr(u)).json()
    orders.hold = {"status": "DENIED"}
    r = api.post(f"/api/campaigns/{w.campaign.id}/pledges/authorize", json={"order_id": o["order_id"]}, headers=hdr(u))
    assert r.status_code == 402 and r.json()["error"]["code"] == "PLEDGE_DECLINED"
    w.db.expire_all()
    assert w.db.scalars(select(Pledge)).one().status == "DENIED"
    assert api.get(f"/api/campaigns/{w.campaign.id}/pledges").json()["pledges"] == []


def test_unconfigured_paypal_says_so_instead_of_pretending(w, client):
    w.campaign.deadline_at = datetime.now(timezone.utc) + timedelta(hours=40)
    u = supporter(w)
    w.db.commit()
    paypal_io.reset_to_placeholders()
    r = client.post(f"/api/campaigns/{w.campaign.id}/pledges/order", json={"amount_cents": 5000}, headers=hdr(u))
    assert r.status_code == 502 and r.json()["error"]["code"] == "PAYPAL_UNAVAILABLE" and "not configured" in r.json()["error"]["message"]


# =============================== the shared helpers only ever move forward ===============================

def test_a_hold_is_recorded_only_from_created_and_only_once(w):
    p = w.pledge(5000, status="CREATED")
    p.paypal_authorization_id = None
    assert pledge_state.mark_authorized(w.db, p, "AUTH-1", NOW, payer_email="a@x.com", payer_id="P") is True
    assert (p.status, p.paypal_authorization_id, p.payer_email, p.payer_id) == ("AUTHORIZED", "AUTH-1", "a@x.com", "P")
    assert pledge_state.mark_authorized(w.db, p, "AUTH-2", NOW) is False and p.paypal_authorization_id == "AUTH-1"
    for status in ("VOIDED", "EXPIRED", "CAPTURED", "DENIED"):                      # an ended pledge is never revived
        q = w.pledge(5000, status=status)
        assert pledge_state.mark_authorized(w.db, q, "AUTH-X", NOW) is False and q.status == status
    assert w.db.query(LedgerEntry).filter(LedgerEntry.type == "PLEDGE_AUTHORIZED").count() == 1


def test_a_hold_ends_only_from_authorized(w):
    p = w.pledge(5000)
    assert pledge_state.mark_hold_ended(w.db, p, "EXPIRED") is True and p.status == "EXPIRED"
    assert pledge_state.mark_hold_ended(w.db, p, "VOIDED") is False and p.status == "EXPIRED"
    for status in ("CREATED", "CAPTURED", "DENIED"):
        q = w.pledge(5000, status=status)
        assert pledge_state.mark_hold_ended(w.db, q, "VOIDED") is False and q.status == status
    assert w.db.query(LedgerEntry).filter(LedgerEntry.type == "PLEDGE_EXPIRED").count() == 1
    assert w.db.query(LedgerEntry).filter(LedgerEntry.type == "PLEDGE_VOIDED").count() == 0
    with pytest.raises(ValueError):
        pledge_state.mark_hold_ended(w.db, w.pledge(5000), "CAPTURED")


def test_the_web_apps_types_match_the_real_pledge_responses(w, orders, api):
    from tests.test_frontend_contract import fields_of, read
    types = read("lib/types.ts")
    u = supporter(w)
    w.db.commit()
    order = api.post(f"/api/campaigns/{w.campaign.id}/pledges/order", json={"amount_cents": 5000}, headers=hdr(u)).json()
    assert set(order) == fields_of(types, "PledgeResult")                           # the order answer carries the currency too
    held = api.post(f"/api/campaigns/{w.campaign.id}/pledges/authorize", json={"order_id": order["order_id"]}, headers=hdr(u)).json()
    assert set(held) == fields_of(types, "PledgeResult") - {"currency"}
    lead = w.db.get(User, w.project.lead_user_id)
    [row] = api.get(f"/api/campaigns/{w.campaign.id}/pledges", headers=hdr(lead)).json()["pledges"]
    assert set(row) == fields_of(types, "PledgeListRow")
    [pub] = api.get(f"/api/campaigns/{w.campaign.id}/pledges").json()["pledges"]
    assert set(pub) == fields_of(types, "PledgeListRow") - {"payer_email", "honor_until"}
