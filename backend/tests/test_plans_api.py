import pytest
from sqlalchemy import select

from app.auth import create_token
from app.config import get_settings
from app.main import app
from app.models import ProjectMember, User
from app.services import paypal_io
from app.agents.guardian_llm import get_guardian_llm
from tests.factories import GOAL, FakeReader, World, scripted_llm


@pytest.fixture()
def w(db):
    return World(db)


@pytest.fixture(autouse=True)
def fake_paypal(db):
    app.dependency_overrides[paypal_io.get_reader] = lambda: FakeReader(db)
    llm, _ = scripted_llm(db)                                   # always answers "low risk"
    app.dependency_overrides[get_guardian_llm] = lambda: llm
    yield
    app.dependency_overrides.pop(paypal_io.get_reader, None)
    app.dependency_overrides.pop(get_guardian_llm, None)


def hdr(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user)}"}


def person(w, role, tag):
    u = User(email=f"{tag}@x.com", display_name=tag)
    w.db.add(u)
    w.db.flush()
    w.db.add(ProjectMember(project_id=w.project.id, user_id=u.id, role=role))
    w.db.flush()
    w.db.commit()
    return u


def lead_user(w):
    return w.db.get(User, w.project.lead_user_id)


def ready_for_payout(w):
    for h in (15000, 15000, 10000):
        w.pledge(h)
    w.capture_all()
    w.project.state = "PAYOUT_READY"
    w.verified_report()
    w.db.commit()


# ---------------- auth ----------------

def test_login_creates_a_user_once_and_returns_a_working_token(client, db):
    r = client.post("/api/auth/login", json={"email": "Lakshmi@Example.com", "display_name": "Lakshmi"})
    assert r.status_code == 200
    token, user = r.json()["token"], r.json()["user"]
    assert user["email"] == "lakshmi@example.com"
    again = client.post("/api/auth/login", json={"email": "lakshmi@example.com", "display_name": "Other"})
    assert again.json()["user"]["id"] == user["id"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["user"]["id"] == user["id"] and me.json()["memberships"] == []


def test_bad_or_missing_tokens_are_rejected_with_the_spec_error_shape(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "BAD_TOKEN"
    assert client.post("/api/auth/login", json={"email": "not-an-email", "display_name": "x"}).status_code == 422


def test_a_token_signed_with_another_secret_is_rejected(client, w, monkeypatch):
    token = create_token(lead_user(w))
    monkeypatch.setattr(get_settings(), "jwt_secret", "a-different-secret")
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ---------------- plans ----------------

def test_member_can_list_plans_outsider_cannot(client, w):
    ready_for_payout(w)
    outsider = User(email="o@x.com", display_name="o")
    w.db.add(outsider)
    w.db.commit()
    assert client.get(f"/api/projects/{w.project.id}/plans", headers=hdr(lead_user(w))).json() == {"plans": []}
    r = client.get(f"/api/projects/{w.project.id}/plans", headers=hdr(outsider))
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_A_MEMBER"
    assert client.get(f"/api/projects/{w.project.id}/plans").status_code == 401


def test_full_payout_flow_over_http(client, w):
    ready_for_payout(w)
    h = hdr(lead_user(w))
    created = client.post(f"/api/projects/{w.project.id}/plans", json={"kind": "FREELANCER_PAYOUT"}, headers=h)
    assert created.status_code == 201
    plan = created.json()
    assert plan["state"] == "PROPOSED" and plan["release_policy"] == "HUMAN" and plan["decision"] is None
    assert [(s["op"], s["amount_cents"], s["receiver_email"]) for s in plan["steps"]] == [("PAYOUT_ITEM", GOAL, "arjun@sandbox.com")]
    pid = plan["id"]

    reviewed = client.post(f"/api/plans/{pid}/review", headers=h).json()
    assert reviewed["state"] == "REVIEWED" and reviewed["decision"] == "ALLOW"
    review = reviewed["reviews"][0]
    assert len(review["rules"]) == 9 and all(r["status"] in ("PASS", "SKIPPED") for r in review["rules"])

    bad = client.post(f"/api/plans/{pid}/approve", headers=h,
                      json={"plan_hash": "0" * 64, "guardian_review_id": review["id"]})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "HASH_MISMATCH"

    ok = client.post(f"/api/plans/{pid}/approve", headers=h,
                     json={"plan_hash": plan["plan_hash"], "guardian_review_id": review["id"]})
    assert ok.status_code == 200 and ok.json()["state"] == "APPROVED"
    assert ok.json()["approvals"][0]["approver"] == f"user:{w.project.lead_user_id}"
    assert client.get(f"/api/plans/{pid}", headers=h).json()["state"] == "APPROVED"
    assert [p["id"] for p in client.get(f"/api/projects/{w.project.id}/plans", headers=h).json()["plans"]] == [pid]


def test_only_payout_and_refund_plans_can_be_requested_by_users(client, w):
    ready_for_payout(w)
    h = hdr(lead_user(w))
    for kind in ("CAPTURE_PLEDGES", "RELEASE_HOLDS", "NONSENSE"):
        r = client.post(f"/api/projects/{w.project.id}/plans", json={"kind": kind}, headers=h)
        assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_KIND"


def test_roles_on_plan_creation_and_approval(client, w):
    ready_for_payout(w)
    sponsor, freelancer, fan = person(w, "SPONSOR", "ravi"), person(w, "FREELANCER", "arjun2"), person(w, "SUPPORTER", "fan")
    url = f"/api/projects/{w.project.id}/plans"
    assert client.post(url, json={"kind": "FREELANCER_PAYOUT"}, headers=hdr(freelancer)).status_code == 403
    assert client.post(url, json={"kind": "FREELANCER_PAYOUT"}, headers=hdr(fan)).status_code == 403
    assert client.post(url, json={"kind": "REFUND_CAPTURED", "reason": "CANCEL_BEFORE_WORK"},
                       headers=hdr(sponsor)).status_code == 403                      # refunds: lead only
    created = client.post(url, json={"kind": "FREELANCER_PAYOUT"}, headers=hdr(sponsor))
    assert created.status_code == 201                                               # a sponsor may request a payout
    pid = created.json()["id"]
    assert client.post(f"/api/plans/{pid}/review", headers=hdr(freelancer)).status_code == 403
    review = client.post(f"/api/plans/{pid}/review", headers=hdr(sponsor)).json()["reviews"][0]
    r = client.post(f"/api/plans/{pid}/approve", headers=hdr(freelancer),
                    json={"plan_hash": created.json()["plan_hash"], "guardian_review_id": review["id"]})
    assert r.status_code == 403, "the freelancer must never approve their own payout"


def test_unbuildable_plan_is_a_clear_409(client, w):
    r = client.post(f"/api/projects/{w.project.id}/plans", json={"kind": "FREELANCER_PAYOUT"}, headers=hdr(lead_user(w)))
    assert r.status_code == 409 and r.json()["error"]["code"] == "CANNOT_BUILD_PLAN"


def test_unknown_plan_is_404_and_foreign_project_plan_is_403(client, w):
    ready_for_payout(w)
    other = World(w.db, tag="Q")
    other_lead = w.db.get(User, other.project.lead_user_id)
    w.db.commit()
    pid = client.post(f"/api/projects/{w.project.id}/plans", json={"kind": "FREELANCER_PAYOUT"},
                      headers=hdr(lead_user(w))).json()["id"]
    assert client.get("/api/plans/99999", headers=hdr(other_lead)).status_code == 404
    assert client.get(f"/api/plans/{pid}", headers=hdr(other_lead)).status_code == 403


# ---------------- demo: simulate tampered plan ----------------

def test_simulate_tamper_returns_a_blocked_labelled_simulation_and_changes_nothing(client, w):
    ready_for_payout(w)
    h = hdr(lead_user(w))
    plan = client.post(f"/api/projects/{w.project.id}/plans", json={"kind": "FREELANCER_PAYOUT"}, headers=h).json()
    client.post(f"/api/plans/{plan['id']}/review", headers=h)
    r = client.post(f"/api/plans/{plan['id']}/simulate-tamper", json={"mutation": "SWAP_RECIPIENT"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["simulation"] is True and body["review"]["simulated"] is True and body["review"]["decision"] == "BLOCK"
    failed = {x["id"] for x in body["review"]["rules"] if x["status"] == "FAIL"}
    assert {"G-12", "G-03"} <= failed
    after = client.get(f"/api/plans/{plan['id']}", headers=h).json()
    assert after["state"] == "REVIEWED" and after["decision"] == "ALLOW"           # the real plan is untouched


def test_simulate_tamper_validates_input_and_is_hidden_outside_demo_mode(client, w, monkeypatch):
    ready_for_payout(w)
    h = hdr(lead_user(w))
    pid = client.post(f"/api/projects/{w.project.id}/plans", json={"kind": "FREELANCER_PAYOUT"}, headers=h).json()["id"]
    r = client.post(f"/api/plans/{pid}/simulate-tamper", json={"mutation": "DROP_TABLES"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_MUTATION"
    r = client.post(f"/api/plans/{pid}/simulate-tamper", json={"mutation": "DOUBLE_CAPTURE"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "CANNOT_TAMPER"   # wrong plan kind
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    r = client.post(f"/api/plans/{pid}/simulate-tamper", json={"mutation": "SWAP_RECIPIENT"}, headers=h)
    assert r.status_code == 404                                                      # SPEC 12: demo endpoints 404


def test_a_payout_review_survives_paypal_being_down_and_bad_refund_reasons_are_refused(client, w, db):
    ready_for_payout(w)
    app.dependency_overrides[paypal_io.get_reader] = lambda: FakeReader(db, down=True)
    h = hdr(lead_user(w))
    plan = client.post(f"/api/projects/{w.project.id}/plans", json={"kind": "FREELANCER_PAYOUT"}, headers=h).json()
    got = client.post(f"/api/plans/{plan['id']}/review", headers=h).json()
    # a payout references no PayPal objects, so only the solvency check is skipped: still allowed
    assert got["decision"] == "ALLOW"
    refund = client.post(f"/api/projects/{w.project.id}/plans", json={"kind": "REFUND_CAPTURED", "reason": "X"}, headers=h)
    assert refund.status_code == 409                                                 # bad reason is refused up front
