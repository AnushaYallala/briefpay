import pytest

from app.agents.ba_agent import set_ba_agents
from app.agents.brd_generator import BRDGenerator, set_brd_generator
from tests.ba_factory import R2, conflict
from tests.brd_factory import draft
from tests.factories import scripted_adapter
from tests.test_ba_api import Team, login


@pytest.fixture()
def t(client, db):
    team = Team(client, db)
    yield team
    set_ba_agents(None)
    set_brd_generator(None)


def ready(t):
    """Drive the BA analysis to a clean READY (93) through the real endpoints."""
    t.script(t.out(R2, conflicts=[conflict(True, "Enquiry form only, no payments on the site")]))
    assert t.post_run().status_code == 202
    t.run_job()
    assert t.ba(t.lakshmi)["session"]["state"] == "READY"


def script_brd(t, *outputs):
    adapter, backend = scripted_adapter(t.db, *outputs)
    set_brd_generator(BRDGenerator(adapter))
    return backend


def generate(t, who=None):
    return t.client.post(f"/api/projects/{t.pid}/brd/generate", headers=who or t.lakshmi)


# ---------------- the happy path, as a stranger would see it ----------------

def test_generate_then_anyone_can_read_and_download_the_brd(t, client):
    ready(t)
    script_brd(t, draft(members=t.ids))
    r = generate(t)
    assert r.status_code == 202
    t.run_job()
    job = client.get(f"/api/jobs/{r.json()['job_id']}").json()
    assert job["state"] == "DONE" and job["result"]["version"] == 1 and job["result"]["already_generated"] is False

    pub = client.get(f"/api/projects/{t.pid}/brd")                                       # no token at all
    assert pub.status_code == 200
    b = pub.json()
    assert (b["version"], b["status"], b["score_at_generation"]) == (1, "PENDING_APPROVAL", 93)
    assert b["sha256"] == job["result"]["sha256"] and len(b["sha256"]) == 64
    assert [r["code"] for r in b["content"]["requirements"]] == ["REQ-001", "REQ-002"]
    assert b["content"]["constraints"] == {"budget_cents": 40000, "currency": "USD", "delivery_days": 5, "hosting": None, "domain": None}
    assert b["markdown"].startswith("# Velugu Cove tourism website") and "### REQ-001 · Enquiry form" in b["markdown"]
    assert "@" not in pub.text, "a public document must never contain an email"
    assert [a["member_name"] for a in b["awaiting"]] == ["Lakshmi", "Ravi", "Meena"] and b["approvals"] == []
    assert b["versions"] == [{"version": 1, "status": "PENDING_APPROVAL", "sha256": b["sha256"]}] and b["locked_at"] is None

    assert client.get(f"/api/projects/{t.pid}", headers=t.lakshmi).json()["state"] == "BRD_REVIEW"
    assert t.ba(t.lakshmi)["session"]["state"] == "BRD_GENERATED"

    md = client.get(f"/api/projects/{t.pid}/brd/1.md")
    assert md.status_code == 200 and md.text == b["markdown"]
    assert md.headers["content-type"].startswith("text/markdown") and md.headers["x-brd-sha256"] == b["sha256"]
    assert 'filename="brd-v1.md"' in md.headers["content-disposition"]
    assert client.get(f"/api/projects/{t.pid}/brd?version=1").json()["sha256"] == b["sha256"]


def test_missing_things_are_404s_in_the_standard_shape(t, client):
    assert client.get(f"/api/projects/{t.pid}/brd").json()["error"]["code"] == "NO_BRD"
    assert client.get(f"/api/projects/{t.pid}/brd/1.md").status_code == 404
    assert client.get("/api/projects/9999/brd").json()["error"]["code"] == "PROJECT_NOT_FOUND"
    ready(t)
    script_brd(t, draft(members=t.ids))
    generate(t)
    t.run_job()
    assert client.get(f"/api/projects/{t.pid}/brd?version=2").status_code == 404
    assert client.get(f"/api/projects/{t.pid}/brd/2.md").status_code == 404


# ---------------- who and when ----------------

def test_only_the_lead_may_generate(t, client):
    ready(t)
    for who in (t.ravi, t.meena, t.arjun, login(client, "stranger@example.com", "S")):
        assert generate(t, who).status_code == 403
    assert client.post(f"/api/projects/{t.pid}/brd/generate").status_code == 401


def test_generation_is_refused_until_the_analysis_is_ready(t, client):
    r = generate(t)
    assert r.status_code == 409 and r.json()["error"]["code"] == "BA_NOT_READY"
    t.script(t.out(R2, conflicts=[conflict()]))                                          # a red gate keeps it ACTIVE
    t.post_run()
    t.run_job()
    assert generate(t).json()["error"]["code"] == "BA_NOT_READY"


def test_a_second_click_after_generation_is_refused_and_creates_nothing(t, client, db):
    ready(t)
    script_brd(t, draft(members=t.ids))
    generate(t)
    t.run_job()
    again = generate(t)
    assert again.status_code == 409 and again.json()["error"]["code"] == "PROJECT_STATE"
    from app.models import BRD
    assert db.query(BRD).count() == 1


def test_two_queued_jobs_still_make_only_one_brd(t, client, db):
    ready(t)
    backend = script_brd(t, draft(members=t.ids))
    first, second = generate(t).json()["job_id"], generate(t).json()["job_id"]            # a double click before either runs
    t.run_job()
    t.run_job()
    from app.models import BRD
    assert db.query(BRD).count() == 1 and len(backend.calls) == 1
    assert client.get(f"/api/jobs/{second}").json()["result"]["already_generated"] is True
    assert client.get(f"/api/jobs/{first}").json()["result"]["already_generated"] is False


def test_a_broken_ai_leaves_a_retrying_job_and_no_brd(t, client):
    ready(t)
    set_brd_generator(BRDGenerator(None))
    job_id = generate(t).json()["job_id"]
    t.run_job()
    j = client.get(f"/api/jobs/{job_id}").json()
    assert j["state"] == "QUEUED" and "not configured" in j["error"]
    assert client.get(f"/api/projects/{t.pid}/brd").status_code == 404
    assert client.get(f"/api/projects/{t.pid}", headers=t.lakshmi).json()["state"] == "REQUIREMENTS"


def test_an_invalid_draft_is_reported_on_the_job_and_creates_no_brd(t, client):
    ready(t)
    script_brd(t, {"nonsense": 1}, {"nonsense": 2})                                       # schema-invalid twice
    job_id = generate(t).json()["job_id"]
    t.run_job()
    j = client.get(f"/api/jobs/{job_id}").json()
    assert j["state"] == "QUEUED" and "could not produce a valid draft" in j["error"]
    assert client.get(f"/api/projects/{t.pid}/brd").status_code == 404
