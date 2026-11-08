import pytest
from sqlalchemy import select

from app.agents.ba_agent import set_ba_agents
from app.agents.brd_generator import set_brd_generator
from app.models import BRD, BAQuestion, BRDApproval, Job, LedgerEntry, Project
from tests.ba_factory import R2, conflict
from tests.brd_factory import draft
from tests.test_ba_api import Team, login
from tests.test_brd_api import generate, ready, script_brd


@pytest.fixture()
def t(client, db):
    team = Team(client, db)
    yield team
    set_ba_agents(None)
    set_brd_generator(None)


def with_brd(t):
    """A BRD v1 awaiting approval, produced through the real endpoints."""
    ready(t)
    script_brd(t, draft(members=t.ids))
    generate(t)
    t.run_job()
    return t.client.get(f"/api/projects/{t.pid}/brd").json()


def decide(t, who, sha, decision="APPROVE", comment=None, version=1):
    body = {"decision": decision, "brd_sha256": sha}
    if comment is not None:
        body["comment"] = comment
    return t.client.post(f"/api/projects/{t.pid}/brd/{version}/decision", headers=who, json=body)


def brd_view(t, **q):
    return t.client.get(f"/api/projects/{t.pid}/brd", params=q).json()


def project_state(t):
    return t.client.get(f"/api/projects/{t.pid}", headers=t.lakshmi).json()["state"]


def ledger_types(t):
    return [e.type for e in t.db.scalars(select(LedgerEntry).order_by(LedgerEntry.seq))]


# ---------------- unanimous approval locks the document ----------------

def test_the_last_approval_locks_the_brd_and_starts_contracting(t, client, db):
    b = with_brd(t)
    sha = b["sha256"]
    r1 = decide(t, t.ravi, sha)
    assert r1.status_code == 200 and r1.json() == {"changed": True, "brd_version": 1, "brd_status": "PENDING_APPROVAL",
                                                   "project_state": "BRD_REVIEW", "approved": 1, "required": 3, "locked": False}
    mid = decide(t, t.meena, sha).json()
    assert mid["approved"] == 2 and not mid["locked"]
    view = brd_view(t)
    assert [a["member_name"] for a in view["awaiting"]] == ["Lakshmi"] and view["status"] == "PENDING_APPROVAL"

    last = decide(t, t.lakshmi, sha).json()                                     # the lead is also a sponsor
    assert last == {"changed": True, "brd_version": 1, "brd_status": "APPROVED", "project_state": "CONTRACTING",
                    "approved": 3, "required": 3, "locked": True}
    view = brd_view(t)
    assert view["status"] == "APPROVED" and view["locked_at"] and view["awaiting"] == []
    assert {(a["member_name"], a["decision"]) for a in view["approvals"]} == {("Lakshmi", "APPROVE"), ("Ravi", "APPROVE"), ("Meena", "APPROVE")}
    assert project_state(t) == "CONTRACTING"
    locked = [e for e in db.scalars(select(LedgerEntry).where(LedgerEntry.type == "BRD_LOCKED"))]
    assert len(locked) == 1 and locked[0].amount_cents == 0 and locked[0].meta_json == {"brd_version": 1, "brd_sha256": sha}
    assert ledger_types(t).count("APPROVAL") == 3


def test_a_locked_brd_can_no_longer_be_decided_or_changed(t, client):
    sha = with_brd(t)["sha256"]
    for who in (t.ravi, t.meena, t.lakshmi):
        decide(t, who, sha)
    for decision in ("APPROVE", "REJECT"):
        r = decide(t, t.ravi, sha, decision, comment="changed my mind")
        assert r.status_code == 409 and r.json()["error"]["code"] == "PROJECT_STATE"
    assert brd_view(t)["status"] == "APPROVED" and project_state(t) == "CONTRACTING"
    assert t.post_run().json()["error"]["code"] in ("PROJECT_STATE", "BA_DONE")        # the BA conversation is closed too


# ---------------- decisions are bound to the exact hash ----------------

def test_a_decision_on_a_different_hash_is_refused_and_stores_nothing(t, client, db):
    b = with_brd(t)
    r = decide(t, t.ravi, "0" * 64)
    assert r.status_code == 409 and r.json()["error"]["code"] == "HASH_MISMATCH"
    assert r.json()["error"]["details"] == {"current_sha256": b["sha256"]}
    assert db.query(BRDApproval).count() == 0 and project_state(t) == "BRD_REVIEW"
    assert client.post(f"/api/projects/{t.pid}/brd/1/decision", headers=t.ravi, json={"decision": "APPROVE", "brd_sha256": "short"}).status_code == 422


def test_approving_the_same_document_twice_is_harmless(t, client, db):
    sha = with_brd(t)["sha256"]
    decide(t, t.ravi, sha)
    again = decide(t, t.ravi, sha)
    assert again.status_code == 200 and again.json()["changed"] is False and again.json()["approved"] == 1
    assert db.query(BRDApproval).count() == 1 and ledger_types(t).count("APPROVAL") == 1


# ---------------- who may vote ----------------

def test_only_sponsors_and_the_lead_vote(t, client):
    sha = with_brd(t)["sha256"]
    assert decide(t, t.arjun, sha).status_code == 403                           # the freelancer never votes on the brief
    assert decide(t, login(client, "stranger@example.com", "S"), sha).status_code == 403
    assert client.post(f"/api/projects/{t.pid}/brd/1/decision", json={"decision": "APPROVE", "brd_sha256": sha}).status_code == 401
    assert brd_view(t)["approvals"] == []


def test_bad_decision_values_and_missing_versions(t, client):
    sha = with_brd(t)["sha256"]
    r = decide(t, t.ravi, sha, "MAYBE")
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_DECISION"
    assert decide(t, t.ravi, sha, version=7).json()["error"]["code"] == "NO_BRD"


def test_nobody_can_vote_before_a_brd_exists(t, client):
    r = client.post(f"/api/projects/{t.pid}/brd/1/decision", headers=t.ravi, json={"decision": "APPROVE", "brd_sha256": "a" * 64})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NO_BRD"


# ---------------- rejection reopens the conversation ----------------

def test_a_rejection_needs_a_comment(t, client, db):
    sha = with_brd(t)["sha256"]
    for comment in (None, "", "   "):
        r = decide(t, t.meena, sha, "REJECT", comment=comment)
        assert r.status_code == 422 and r.json()["error"]["code"] == "COMMENT_REQUIRED"
    assert decide(t, t.meena, sha, "REJECT", comment="x" * 1001).status_code == 422
    assert db.query(BRDApproval).count() == 0 and project_state(t) == "BRD_REVIEW"


def test_a_rejection_sends_the_project_back_with_the_comment_as_a_question_for_everyone(t, client, db):
    b = with_brd(t)
    decide(t, t.ravi, b["sha256"])                                              # one approval already given
    r = decide(t, t.meena, b["sha256"], "REJECT", comment="Please add the boat safety information as its own page")
    assert r.status_code == 200
    assert r.json() == {"changed": True, "brd_version": 1, "brd_status": "SUPERSEDED", "project_state": "REQUIREMENTS",
                        "approved": 1, "required": 3, "locked": False}
    assert project_state(t) == "REQUIREMENTS"
    ba = t.ba(t.lakshmi)
    assert ba["session"]["state"] == "ACTIVE" and ba["session"]["round"] == 1
    [q] = [q for q in ba["questions"] if q["status"] == "OPEN"]
    assert q["round"] == 1 and q["addressed_to"] == ["ALL"] and q["dimension"] == "BRD" and q["dimension_name"] is None
    assert 'Meena asked for changes to BRD v1: "Please add the boat safety information as its own page"' in q["question"]
    assert q["can_answer"] is True and t.ba(t.arjun)["questions"][-1]["can_answer"] is False
    old = brd_view(t, version=1)
    assert old["status"] == "SUPERSEDED"
    assert {(a["member_name"], a["decision"]) for a in old["approvals"]} == {("Ravi", "APPROVE"), ("Meena", "REJECT")}
    assert [a["comment"] for a in old["approvals"] if a["decision"] == "REJECT"] == ["Please add the boat safety information as its own page"]
    assert "BRD_LOCKED" not in ledger_types(t)
    late = decide(t, t.lakshmi, b["sha256"])
    assert late.status_code == 409 and late.json()["error"]["code"] == "PROJECT_STATE"


def test_an_approver_can_withdraw_by_rejecting(t, client, db):
    sha = with_brd(t)["sha256"]
    decide(t, t.lakshmi, sha)
    r = decide(t, t.lakshmi, sha, "REJECT", comment="On reflection the success measure is too ambitious")
    assert r.status_code == 200 and r.json()["brd_status"] == "SUPERSEDED" and r.json()["approved"] == 0
    assert db.query(BRDApproval).count() == 1 and db.query(BRDApproval).one().decision == "REJECT"


def test_the_whole_loop_reject_answer_rescore_new_version_approve_lock(t, client, db):
    v1 = with_brd(t)
    decide(t, t.ravi, v1["sha256"])
    decide(t, t.meena, v1["sha256"], "REJECT", comment="Add a page for boat safety")
    assert db.query(Job).filter(Job.type == "BA_RUN").count() == 1                # only the first BA run so far

    q = next(q for q in t.ba(t.lakshmi)["questions"] if q["status"] == "OPEN")
    ans = client.post(f"/api/ba/questions/{q['id']}/answers", headers=t.lakshmi,
                      json={"answer_text": "Yes: a /safety page with the life-jacket and weather rules"})
    assert ans.json() == {"question_status": "ANSWERED", "round_complete": True}
    t.script(t.out(R2, conflicts=[conflict(True, "Enquiry form only, no payments on the site")]))      # round 2 scoring: still ready
    t.run_job()
    assert t.ba(t.lakshmi)["session"]["state"] == "READY" and t.ba(t.lakshmi)["session"]["round"] == 2

    script_brd(t, draft(members=t.ids, executive_summary="Revised: the site now has a dedicated boat safety page for visitors.",
                        sitemap=[{"path": "/", "purpose": "Welcome"}, {"path": "/safety", "purpose": "Boat safety information"}]))
    assert generate(t).status_code == 202
    t.run_job()
    v2 = brd_view(t)
    assert v2["version"] == 2 and v2["status"] == "PENDING_APPROVAL" and v2["sha256"] != v1["sha256"]
    assert [a["member_name"] for a in v2["awaiting"]] == ["Lakshmi", "Ravi", "Meena"], "earlier approvals do not carry over"
    assert [v["status"] for v in v2["versions"]] == ["SUPERSEDED", "PENDING_APPROVAL"] and "/safety" in v2["markdown"]
    assert project_state(t) == "BRD_REVIEW"

    stale = decide(t, t.ravi, v1["sha256"], version=2)                           # approving what they read before is refused
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "HASH_MISMATCH"
    old = decide(t, t.ravi, v1["sha256"], version=1)
    assert old.status_code == 409 and old.json()["error"]["code"] == "BRD_CLOSED"        # v1 is SUPERSEDED, whatever hash is sent

    for who in (t.ravi, t.meena):
        decide(t, who, v2["sha256"], version=2)
    final = decide(t, t.lakshmi, v2["sha256"], version=2).json()
    assert final["locked"] is True and final["brd_version"] == 2 and final["project_state"] == "CONTRACTING"
    assert brd_view(t)["status"] == "APPROVED" and brd_view(t, version=1)["status"] == "SUPERSEDED"
    assert [e.meta_json["brd_version"] for e in db.scalars(select(LedgerEntry).where(LedgerEntry.type == "BRD_LOCKED"))] == [2]


def test_a_rejection_makes_the_transcript_editable_again(t, client):
    sha = with_brd(t)["sha256"]
    before = client.post(f"/api/projects/{t.pid}/transcripts", headers=t.lakshmi, json={"text": "new text"})
    assert before.status_code == 409
    decide(t, t.ravi, sha, "REJECT", comment="The meeting notes were incomplete")
    after = client.post(f"/api/projects/{t.pid}/transcripts", headers=t.lakshmi, json={"text": "Lakshmi: a fuller set of notes"})
    assert after.status_code == 201


# ---------------- consistency checks ----------------

def test_a_decision_recorded_against_another_hash_never_counts_towards_the_lock(t, client, db):
    """The content of a BRD never changes, but if a row ever disagrees with the hash it must not help lock it."""
    from app.models import ProjectMember
    sha = with_brd(t)["sha256"]
    brd = db.query(BRD).one()
    for name in ("Ravi", "Meena"):
        member = db.query(ProjectMember).filter(ProjectMember.id == t.m[name]).one()
        db.add(BRDApproval(brd_id=brd.id, member_id=member.id, decision="APPROVE", brd_sha256="f" * 64))
    db.commit()
    r = decide(t, t.lakshmi, sha)
    assert r.json()["approved"] == 1 and r.json()["locked"] is False and brd_view(t)["status"] == "PENDING_APPROVAL"
    assert [a["member_name"] for a in brd_view(t)["approvals"]] == ["Lakshmi"]


def test_the_service_itself_refuses_a_freelancer_even_if_the_router_were_bypassed(t, db):
    from app.models import Project, ProjectMember
    from app.services import brd_approvals
    from app.services.brd_service import BRDError
    sha = with_brd(t)["sha256"]
    freelancer = db.query(ProjectMember).filter(ProjectMember.id == t.m["Arjun"]).one()
    with pytest.raises(BRDError) as e:
        brd_approvals.decide(db, db.get(Project, t.pid), db.query(BRD).one(), freelancer, "APPROVE", sha, None)
    assert e.value.code == "FORBIDDEN" and e.value.status == 403 and db.query(BRDApproval).count() == 0



def test_a_voter_added_after_the_review_started_is_impossible(t, client):
    with_brd(t)
    r = client.put(f"/api/projects/{t.pid}/members", headers=t.lakshmi,
                   json={"members": [{"email": "late@example.com", "role": "SPONSOR"}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "PROJECT_STATE"


def test_every_decision_is_in_the_ledger_with_the_hash_and_who(t, client, db):
    sha = with_brd(t)["sha256"]
    decide(t, t.ravi, sha)
    decide(t, t.meena, sha, "REJECT", comment="Needs a safety page")
    memos = [e for e in db.scalars(select(LedgerEntry).where(LedgerEntry.type == "APPROVAL").order_by(LedgerEntry.seq))]
    assert [(m.meta_json["decision"], m.meta_json["brd_sha256"]) for m in memos] == [("APPROVE", sha), ("REJECT", sha)]
    assert all(m.amount_cents == 0 and m.actor.startswith("user:") for m in memos)
    assert memos[1].meta_json["comment"] == "Needs a safety page"
    assert db.get(Project, t.pid).state == "REQUIREMENTS"
    assert db.query(BAQuestion).filter(BAQuestion.dimension == "BRD").count() == 1
