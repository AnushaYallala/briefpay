from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.agents.ba_agent import BAAgent, BAQuestionsAgent, set_ba_agents
from app.models import BASession, Job
from app.services import jobs
from tests.ba_factory import R0, R1, R2, conflict, output, question, questions, requirement
from tests.factories import scripted_adapter

SAMPLE = "\n".join(f"Speaker {i % 3 + 1}: line number {i}" for i in range(1, 31))


def login(client, email, name):
    return {"Authorization": "Bearer " + client.post("/api/auth/login", json={"email": email, "display_name": name}).json()["token"]}


class Team:
    """Velugu Cove through the real API: Lakshmi (lead), Ravi and Meena (sponsors), Arjun (freelancer)."""

    def __init__(self, client, db):
        self.client, self.db = client, db
        self.lakshmi = login(client, "lakshmi@example.com", "Lakshmi")
        self.pid = client.post("/api/projects", headers=self.lakshmi, json={
            "title": "Velugu Cove website", "budget_cents": 40000, "delivery_days": 5, "members": [
                {"email": "ravi@example.com", "display_name": "Ravi", "role": "SPONSOR"},
                {"email": "meena@example.com", "display_name": "Meena", "role": "SPONSOR"},
                {"email": "arjun@example.com", "display_name": "Arjun", "role": "FREELANCER"}]}).json()["id"]
        self.ravi, self.meena, self.arjun = (login(client, f"{n}@example.com", n.title()) for n in ("ravi", "meena", "arjun"))
        members = client.get(f"/api/projects/{self.pid}", headers=self.lakshmi).json()["members"]
        self.m = {x["display_name"]: x["id"] for x in members}
        self.ids = (self.m["Lakshmi"], self.m["Ravi"], self.m["Meena"])
        assert client.post(f"/api/projects/{self.pid}/transcripts", headers=self.lakshmi,
                           json={"text": SAMPLE, "source_name": "meeting.txt"}).status_code == 201
        self.factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)

    def script(self, *outs):
        adapter, backend = scripted_adapter(self.db, *outs)
        set_ba_agents((BAAgent(adapter), BAQuestionsAgent(adapter)))
        return backend

    def out(self, cov, **kw):
        return output(cov, members=self.ids, **kw)

    def run_job(self):
        assert jobs.run_one(self.factory) is True
        self.db.expire_all()

    def ba(self, who):
        return self.client.get(f"/api/projects/{self.pid}/ba", headers=who).json()

    def post_run(self, who=None):
        return self.client.post(f"/api/projects/{self.pid}/ba/run", headers=who or self.lakshmi)


@pytest.fixture()
def t(client, db):
    team = Team(client, db)
    yield team
    set_ba_agents(None)


# ---------------- the demo scene over HTTP ----------------

def test_the_whole_conversation_from_58_to_93_through_the_api(t, client):
    L, M = t.ids[0], t.ids[2]
    t.script(t.out(R0, conflicts=[conflict()], requirements=[requirement("R1", by=t.ids, criteria=())], out_of_scope=[]),
             questions(question(to=(L, M)), question("D6", "What should a visitor see when the enquiry form works?")),
             t.out(R1, conflicts=[conflict()]),
             questions(question("D3", "Which of your own needs is still missing from our list?", options=None)),
             t.out(R2, conflicts=[conflict(True, "Enquiry form only, no payments on the site")]))

    before = t.ba(t.lakshmi)
    assert before["session"] is None and before["can_run"] is True and t.ba(t.ravi)["can_run"] is False

    r = t.post_run()
    assert r.status_code == 202
    t.run_job()
    job = client.get(f"/api/jobs/{r.json()['job_id']}").json()
    assert job["state"] == "DONE" and job["result"] == {"score": 58, "round": 0, "state": "ACTIVE", "questions": 2}

    view = t.ba(t.ravi)
    assert (view["session"]["state"], view["session"]["round"], view["session"]["current_score"]) == ("ACTIVE", 0, 58)
    assert view["session"]["target_score"] == 90 and view["session"]["max_rounds"] == 5
    assert view["score"]["total"] == 58 and [g["id"] for g in view["score"]["gates"] if not g["passed"]] == ["GT-2", "GT-3", "GT-4"]
    assert len(view["score"]["dimensions"]) == 10 and view["score"]["dimensions"][4]["name"] == "Functional requirements"
    q_named, q_all = view["questions"]
    assert q_named["can_answer"] is False and q_all["can_answer"] is True            # Ravi isn't named in the first question
    assert q_named["dimension_name"] == "Functional requirements" and q_named["suggested_options"] == ["Enquiry form only", "Online booking"]
    assert t.ba(t.lakshmi)["questions"][0]["can_answer"] is True and t.ba(t.arjun)["questions"][0]["can_answer"] is False

    def answer(who, q, text, **kw):
        return client.post(f"/api/ba/questions/{q['id']}/answers", headers=who, json={"answer_text": text, **kw})

    assert answer(t.lakshmi, q_named, "Enquiry form only", selected_option="Enquiry form only").json() == {"question_status": "OPEN", "round_complete": False}
    assert answer(t.meena, q_named, "Agreed, no payments on the site").json() == {"question_status": "ANSWERED", "round_complete": False}
    done = answer(t.ravi, q_all, "A success message and a reference number")
    assert done.status_code == 201 and done.json() == {"question_status": "ANSWERED", "round_complete": True}

    t.run_job()
    mid = t.ba(t.lakshmi)
    assert (mid["session"]["round"], mid["session"]["current_score"]) == (1, 79)
    [q3] = [q for q in mid["questions"] if q["status"] == "OPEN"]
    assert q3["round"] == 1 and q3["addressed_to"] == ["ALL"]
    assert answer(t.lakshmi, q3, "The boat tours must be listed").json()["round_complete"] is True
    # the earlier answers are visible to every member with names attached
    first = mid["questions"][0]
    assert {(a["member_name"], a["answer_text"]) for a in first["answers"]} == {("Lakshmi", "Enquiry form only"), ("Meena", "Agreed, no payments on the site")}

    t.run_job()
    final = t.ba(t.lakshmi)
    assert (final["session"]["state"], final["session"]["round"], final["score"]["total"]) == ("READY", 2, 93)
    assert all(g["passed"] for g in final["score"]["gates"]) and final["score"]["capped"] is False
    assert [(h["round"], h["total"]) for h in final["history"]] == [(0, 58), (1, 79), (2, 93)]
    assert not [q for q in final["questions"] if q["status"] == "OPEN"]


# ---------------- who may do what ----------------

def test_only_the_lead_runs_skips_and_finalizes(t, client):
    t.script(t.out(R0, conflicts=[conflict()]), questions(question()))
    for who in (t.ravi, t.meena, t.arjun):
        assert t.post_run(who).status_code == 403
    assert client.post(f"/api/projects/{t.pid}/ba/run").status_code == 401
    assert t.post_run(login(client, "stranger@example.com", "S")).status_code == 403
    t.post_run()
    t.run_job()
    q = t.ba(t.lakshmi)["questions"][0]
    assert client.post(f"/api/ba/questions/{q['id']}/skip", headers=t.ravi).status_code == 403
    assert client.post(f"/api/projects/{t.pid}/ba/finalize", headers=t.ravi).status_code == 403
    r = client.post(f"/api/ba/questions/{q['id']}/skip", headers=t.lakshmi)
    assert r.status_code == 200 and r.json() == {"question_status": "SKIPPED", "round_complete": True}


def test_viewing_and_answering_need_membership_and_a_sponsor_role(t, client):
    t.script(t.out(R0, conflicts=[conflict()]), questions(question(to=("ALL",))))
    t.post_run()
    t.run_job()
    q = t.ba(t.lakshmi)["questions"][0]
    stranger = login(client, "stranger@example.com", "S")
    assert client.get(f"/api/projects/{t.pid}/ba", headers=stranger).status_code == 403
    assert client.get(f"/api/projects/{t.pid}/ba").status_code == 401
    for who in (stranger, t.arjun):
        r = client.post(f"/api/ba/questions/{q['id']}/answers", headers=who, json={"answer_text": "hello"})
        assert r.status_code == 403
    assert t.ba(t.arjun)["questions"][0]["can_answer"] is False                       # freelancer may read, never answer
    assert client.post("/api/ba/questions/9999/answers", headers=t.ravi, json={"answer_text": "x"}).status_code == 404
    assert client.post(f"/api/ba/questions/{q['id']}/answers", headers=t.ravi, json={"answer_text": ""}).status_code == 422


def test_answer_errors_use_the_standard_error_shape(t, client):
    t.script(t.out(R0, conflicts=[conflict()]), questions(question(to=(t.ids[1],), options=("A", "B"))))
    t.post_run()
    t.run_job()
    q = t.ba(t.lakshmi)["questions"][0]
    url = f"/api/ba/questions/{q['id']}/answers"
    r = client.post(url, headers=t.meena, json={"answer_text": "not for me"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_ADDRESSED"
    r = client.post(url, headers=t.ravi, json={"answer_text": "x", "selected_option": "C"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_OPTION"
    assert client.post(url, headers=t.ravi, json={"answer_text": "A it is", "selected_option": "A"}).status_code == 201
    r = client.post(url, headers=t.ravi, json={"answer_text": "again"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "QUESTION_CLOSED"


# ---------------- running ----------------

def test_run_is_refused_without_a_transcript_while_questions_are_open_and_when_rate_limited(t, client, db):
    r = client.post("/api/projects", headers=t.lakshmi, json={"title": "Empty project", "budget_cents": 1000})
    assert client.post(f"/api/projects/{r.json()['id']}/ba/run", headers=t.lakshmi).json()["error"]["code"] == "NO_TRANSCRIPT"

    t.script(t.out(R0, conflicts=[conflict()]), questions(question()))
    t.post_run()
    t.run_job()
    refused = t.post_run()
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "QUESTIONS_OPEN"
    assert t.ba(t.lakshmi)["can_run"] is False

    for _ in range(8):
        db.add(Job(type="BA_RUN", payload_json={"project_id": t.pid}, state="DONE"))
    db.commit()
    q = t.ba(t.lakshmi)["questions"][0]
    client.post(f"/api/ba/questions/{q['id']}/skip", headers=t.lakshmi)
    db.expire_all()
    limited = t.post_run()
    assert limited.status_code == 429 and limited.json()["error"]["code"] == "RATE_LIMITED"


def test_a_broken_ai_shows_up_as_a_retrying_job_not_a_corrupted_analysis(t, client):
    set_ba_agents((BAAgent(None), BAQuestionsAgent(None)))
    job_id = t.post_run().json()["job_id"]
    t.run_job()
    j = client.get(f"/api/jobs/{job_id}").json()
    assert j["state"] == "QUEUED" and "not configured" in j["error"] and j["attempts"] == 1
    assert t.ba(t.lakshmi)["score"] is None and t.ba(t.lakshmi)["questions"] == []
    # fix the AI, make the retry due, and it completes normally
    t.script(t.out(R0, conflicts=[conflict()]), questions(question()))
    t.db.query(Job).filter(Job.id == job_id).update({"run_after": datetime.now(timezone.utc) - timedelta(seconds=1)})
    t.db.commit()
    t.run_job()
    assert client.get(f"/api/jobs/{job_id}").json()["state"] == "DONE" and t.ba(t.lakshmi)["score"]["total"] == 58


# ---------------- finalize ----------------

def test_finalize_accepts_the_gaps_after_the_round_limit(t, client, db):
    t.script(t.out(R1, conflicts=[conflict()]))
    sess = BASession(project_id=t.pid, state="ACTIVE", round=5, current_score=0)
    db.add(sess)
    db.commit()
    t.post_run()
    t.run_job()
    view = t.ba(t.lakshmi)
    assert view["session"]["state"] == "MAX_ROUNDS" and view["can_finalize"] is True and view["can_run"] is False
    assert t.post_run().json()["error"]["code"] == "BA_DONE"
    r = client.post(f"/api/projects/{t.pid}/ba/finalize", headers=t.lakshmi)
    assert r.status_code == 200 and r.json() == {"state": "FINALIZED", "score": 79}
    again = client.post(f"/api/projects/{t.pid}/ba/finalize", headers=t.lakshmi)
    assert again.status_code == 409 and again.json()["error"]["code"] == "NOT_FINALIZABLE"


def test_finalize_is_refused_before_the_limit(t, client):
    t.script(t.out(R0, conflicts=[conflict()]), questions(question()))
    t.post_run()
    t.run_job()
    r = client.post(f"/api/projects/{t.pid}/ba/finalize", headers=t.lakshmi)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_FINALIZABLE"
