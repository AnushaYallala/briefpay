import hashlib
import json

import pytest
from sqlalchemy import select

from app.agents.ba_agent import set_ba_agents
from app.agents.brd_generator import set_brd_generator
from app.models import BRD, Contract, LedgerEntry, Project, ProjectMember
from app.services import contract_service as svc
from tests.test_ba_api import Team, login
from tests.test_brd_approvals import decide, with_brd


@pytest.fixture()
def t(client, db):
    team = Team(client, db)
    yield team
    set_ba_agents(None)
    set_brd_generator(None)


def contracting(t):
    """An APPROVED BRD and a project in CONTRACTING, reached through the real endpoints."""
    sha = with_brd(t)["sha256"]
    for who in (t.ravi, t.meena, t.lakshmi):
        decide(t, who, sha)
    assert t.client.get(f"/api/projects/{t.pid}", headers=t.lakshmi).json()["state"] == "CONTRACTING"
    return sha


def offer(t, amount=40000, days=5, who=None):
    return t.client.post(f"/api/projects/{t.pid}/contract/offer", headers=who or t.lakshmi,
                         json={"amount_cents": amount, "delivery_days": days})


def accept(t, view, email="arjun.dev@sandbox.example.com", who=None, **over):
    body = {"paypal_email": email, "brd_sha256": view["brd_sha256"], "terms_sha256": view["terms_sha256"], **over}
    return t.client.post(f"/api/projects/{t.pid}/contract/accept", headers=who or t.arjun, json=body)


def state(t):
    return t.client.get(f"/api/projects/{t.pid}", headers=t.lakshmi).json()["state"]


# ---------------- the offer ----------------

def test_the_lead_offers_a_contract_bound_to_the_approved_brd(t, client):
    sha = contracting(t)
    r = offer(t)
    assert r.status_code == 201
    c = r.json()
    assert (c["status"], c["amount_cents"], c["currency"], c["delivery_days"], c["conditional"]) == ("OFFERED", 40000, "USD", 5, True)
    assert c["brd_sha256"] == sha and c["brd_version"] == 1 and c["signed_at"] is None and c["effective_at"] is None
    assert c["freelancer_paypal_email"] is None and len(c["terms_sha256"]) == 64
    md = c["terms_md"]
    assert md.startswith("# Conditional Delivery Agreement") and "not a legally binding contract" in md
    assert "USD 400.00" in md and "Within 5 days" in md and f"`{sha}`" in md and "version 1" in md
    assert "It takes effect only if the funding campaign reaches its goal" in md and "nobody is charged" in md
    assert "- **Sponsors:** Lakshmi, Ravi, Meena" in md and "- **Freelancer:** Arjun" in md and "- **Project:** Velugu Cove website" in md
    assert "escrow" not in md.lower() and "pooled funds are held by the platform until that verified approval" in md
    assert state(t) == "CONTRACTING", "an offer alone does not move the project"


def test_the_terms_hash_covers_the_text_and_every_number_and_can_be_recomputed(t, client, db):
    contracting(t)
    c = offer(t).json()
    row = db.query(Contract).one()
    payload = {"terms_md": row.terms_md, "project_id": t.pid, "brd_sha256": row.brd_sha256, "amount_cents": 40000, "currency": "USD",
               "delivery_days": 5, "freelancer_member_id": t.m["Arjun"], "conditional": True}
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    assert c["terms_sha256"] == expected
    other = offer(t, amount=39900).json()
    assert other["terms_sha256"] != expected, "a different price is a different document"


@pytest.mark.parametrize("amount,days,code", [
    (0, 5, None), (-5, 5, None), (40001, 5, "BAD_AMOUNT"), (100001, 5, "BAD_AMOUNT"), (40000, 0, None), (40000, 91, None),
])
def test_unreasonable_offers_are_refused(t, client, db, amount, days, code):
    contracting(t)
    r = offer(t, amount, days)
    assert r.status_code == 422
    if code:
        assert r.json()["error"]["code"] == code
    assert db.query(Contract).count() == 0


def test_the_price_cannot_exceed_the_sandbox_payout_limit_even_with_a_bigger_budget(t, client, db):
    contracting(t)
    db.get(Project, t.pid).budget_cents = 500000
    db.commit()
    assert offer(t, 100001).json()["error"]["code"] == "BAD_AMOUNT"
    assert offer(t, 100000).status_code == 201


def test_only_the_lead_offers(t, client):
    contracting(t)
    for who in (t.ravi, t.meena, t.arjun, login(client, "stranger@example.com", "S")):
        assert offer(t, who=who).status_code == 403
    assert client.post(f"/api/projects/{t.pid}/contract/offer", json={"amount_cents": 1, "delivery_days": 1}).status_code == 401


def test_no_offer_before_the_brd_is_approved_or_without_a_freelancer(t, client, db):
    r = offer(t)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROJECT_STATE"
    contracting(t)
    db.query(ProjectMember).filter(ProjectMember.role == "FREELANCER").delete()
    db.commit()
    assert offer(t).json()["error"]["code"] == "NO_FREELANCER"


def test_re_offering_replaces_an_unsigned_offer_and_voids_the_old_terms(t, client, db):
    contracting(t)
    first = offer(t, 40000, 5).json()
    second = offer(t, 38000, 7).json()
    assert second["id"] == first["id"] and db.query(Contract).count() == 1
    assert (second["amount_cents"], second["delivery_days"]) == (38000, 7) and "USD 380.00" in second["terms_md"]
    stale = accept(t, first)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "HASH_MISMATCH"
    assert accept(t, second).status_code == 200


# ---------------- reading ----------------

def test_only_project_members_can_read_the_contract(t, client):
    contracting(t)
    assert client.get(f"/api/projects/{t.pid}/contract", headers=t.lakshmi).json()["error"]["code"] == "NO_CONTRACT"
    offer(t)
    for who in (t.lakshmi, t.ravi, t.arjun):
        assert client.get(f"/api/projects/{t.pid}/contract", headers=who).json()["status"] == "OFFERED"
    assert client.get(f"/api/projects/{t.pid}/contract").status_code == 401
    assert client.get(f"/api/projects/{t.pid}/contract", headers=login(client, "stranger@example.com", "S")).status_code == 403


# ---------------- signing ----------------

def test_the_freelancer_signs_locking_their_email_and_starting_the_campaign_stage(t, client, db):
    contracting(t)
    view = offer(t).json()
    r = accept(t, view, email="  Arjun.Dev@Sandbox.Example.com ")
    assert r.status_code == 200
    c = r.json()
    assert c["status"] == "SIGNED" and c["signed_at"] and c["freelancer_paypal_email"] == "arjun.dev@sandbox.example.com"
    assert c["effective_at"] is None and c["conditional"] is True, "it only takes effect when the campaign funds"
    assert state(t) == "CAMPAIGN_SETUP"
    assert db.query(ProjectMember).filter(ProjectMember.role == "FREELANCER").one().paypal_email == "arjun.dev@sandbox.example.com"
    memo = db.scalars(select(LedgerEntry).where(LedgerEntry.type == "CONTRACT_SIGNED")).one()
    assert memo.amount_cents == 0 and memo.actor.startswith("user:")
    assert memo.meta_json == {"amount_cents": 40000, "delivery_days": 5, "brd_sha256": view["brd_sha256"],
                              "terms_sha256": view["terms_sha256"], "conditional": True}
    assert "@" not in json.dumps(memo.meta_json), "the ledger can be shown publicly, so it carries no email"


def test_a_signed_contract_is_final(t, client):
    contracting(t)
    view = offer(t).json()
    accept(t, view)
    again = accept(t, view, email="other@sandbox.example.com")
    assert again.status_code == 409 and again.json()["error"]["code"] == "CONTRACT_SIGNED"
    r = offer(t, 30000)                                                       # the project has moved on to CAMPAIGN_SETUP
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROJECT_STATE"
    assert client.get(f"/api/projects/{t.pid}/contract", headers=t.lakshmi).json()["freelancer_paypal_email"] == "arjun.dev@sandbox.example.com"


def test_even_if_the_project_state_were_rewound_a_signed_contract_cannot_be_replaced(t, client, db):
    """Defence in depth: the contract guards itself, independently of the project state check."""
    contracting(t)
    accept(t, offer(t).json())
    db.get(Project, t.pid).state = "CONTRACTING"                              # simulate a bug or manual edit rewinding the stage
    db.commit()
    r = offer(t, 1000)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONTRACT_SIGNED"
    row = db.query(Contract).one()
    assert (row.amount_cents, row.freelancer_paypal_email) == (40000, "arjun.dev@sandbox.example.com") and row.signed_at is not None


def test_signing_needs_both_hashes_to_match(t, client, db):
    contracting(t)
    view = offer(t).json()
    for over in ({"terms_sha256": "0" * 64}, {"brd_sha256": "0" * 64}):
        r = accept(t, view, **over)
        assert r.status_code == 409 and r.json()["error"]["code"] == "HASH_MISMATCH"
    assert db.query(Contract).one().signed_at is None and state(t) == "CONTRACTING"
    assert accept(t, view, terms_sha256="short").status_code == 422


def test_signing_is_refused_if_the_approved_brd_is_no_longer_the_one_offered(t, client, db):
    contracting(t)
    view = offer(t).json()
    db.query(BRD).one().status = "SUPERSEDED"
    db.commit()
    r = accept(t, view)
    assert r.status_code == 409 and r.json()["error"]["code"] == "BRD_CHANGED"


def test_only_the_invited_freelancer_signs(t, client):
    contracting(t)
    view = offer(t).json()
    for who in (t.lakshmi, t.ravi, t.meena, login(client, "stranger@example.com", "S")):
        assert accept(t, view, who=who).status_code == 403
    assert client.post(f"/api/projects/{t.pid}/contract/accept", json={"paypal_email": "a@b.co", "brd_sha256": "0" * 64, "terms_sha256": "0" * 64}).status_code == 401


def test_nothing_to_sign_before_an_offer(t, client):
    contracting(t)
    r = t.client.post(f"/api/projects/{t.pid}/contract/accept", headers=t.arjun,
                      json={"paypal_email": "arjun.dev@sandbox.example.com", "brd_sha256": "0" * 64, "terms_sha256": "0" * 64})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NO_CONTRACT"


@pytest.mark.parametrize("email", ["lakshmi@example.com", "RAVI@example.com", " meena@example.com"])
def test_the_freelancer_cannot_be_paid_to_a_sponsors_account(t, client, db, email):
    contracting(t)
    view = offer(t).json()
    r = accept(t, view, email=email)
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_CONFLICT"
    assert db.query(Contract).one().signed_at is None


def test_a_bad_email_is_rejected(t, client):
    contracting(t)
    view = offer(t).json()
    assert accept(t, view, email="not-an-email").status_code == 422


def test_a_signed_contract_is_what_the_payout_plan_uses(t, client, db):
    """G-12 and the payout builder read the locked email and the BRD hash from this row."""
    sha = contracting(t)
    view = offer(t).json()
    accept(t, view)
    row = db.query(Contract).one()
    assert (row.freelancer_paypal_email, row.brd_sha256, row.amount_cents, row.conditional) == ("arjun.dev@sandbox.example.com", sha, 40000, True)
    assert row.signed_at is not None and row.effective_at is None
    assert svc.get_contract(db, t.pid).id == row.id
