"""Submissions and their automatic checks (T-31, first half): rules for submitting, the check plan, the AUTO_CHECKS job, the API."""
import base64

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models import BRD, AutoCheck, Job, LedgerEntry, ProjectMember, Submission, User
from app.services import jobs
from app.services import submission_service as svc
from app.services.autochecks import AutoChecker
from app.services.safe_fetch import SafeFetcher
from tests.factories import World
from tests.test_autochecks import HOSTS, resolver
from tests.test_plans_api import hdr, lead_user, person

SHA = "a" * 40
REPO = "https://github.com/anu/velugu-cove"
SITE = "https://velugu.example"
HOSTS["velugu.example"] = ["93.184.216.40"]

PAGES = {
    "/": '<html><head><meta name="viewport" content="width=device-width"></head><body>Velugu Cove</body></html>',
    "/stay": "<html><body>Sea Breeze Homestay</body></html>",
    "/contact": "<html><body><form>Send enquiry</form></body></html>",
}


def content():
    return {
        "sitemap": [{"path": "/", "purpose": "home"}, {"path": "/stay", "purpose": "stay"}, {"path": "/contact", "purpose": "form"}],
        "requirements": [
            {"code": "REQ-001", "acceptance_criteria": [
                {"id": "AC-1", "auto_check_hint": {"type": "PAGE_CONTAINS", "path": "/contact", "text": "Send enquiry"}},
                {"id": "AC-2", "auto_check_hint": {"type": "FILE_EXISTS", "path": "src/form.js"}},
                {"id": "AC-3", "auto_check_hint": None}]},
            {"code": "REQ-002", "acceptance_criteria": [
                {"id": "AC-1", "auto_check_hint": {"type": "MOBILE_VIEWPORT", "path": None}},
                {"id": "AC-2", "auto_check_hint": {"type": "URL_REACHABLE", "path": "/stay"}}]},
        ]}


class Internet:
    """The freelancer's site and GitHub, scripted. `github` maps a path to (status, json)."""

    def __init__(self, pages=None, github=None):
        self.pages, self.sent = PAGES if pages is None else pages, []
        self.github = github if github is not None else {
            "/repos/anu/velugu-cove": (200, {"private": False}),
            f"/repos/anu/velugu-cove/commits/{SHA}": (200, {"sha": SHA}),
            "/repos/anu/velugu-cove/contents/src/form.js": (200, {"type": "file", "size": 5, "encoding": "base64",
                                                                  "content": base64.b64encode(b"hello").decode()}),
        }

    def __call__(self, request):
        self.sent.append(request)
        if request.headers["host"] == "api.github.com":
            hit = self.github.get(request.url.path)
            return httpx.Response(hit[0], json=hit[1]) if hit else httpx.Response(404, json={})
        body = self.pages.get(request.url.path)
        return httpx.Response(404, text="nope") if body is None else httpx.Response(200, text=body)

    def checker(self):
        return AutoChecker(SafeFetcher(resolver=resolver, transport=httpx.MockTransport(self)))


@pytest.fixture()
def w(db):
    w = World(db)
    w.project.state = "IN_PROGRESS"
    db.get(BRD, w.contract.brd_id).content_json = content()
    db.commit()
    return w


@pytest.fixture(autouse=True)
def reset_factory():
    yield
    svc.configure(None)


def freelancer(w):
    return db_member(w, w.contract.freelancer_member_id)


def db_member(w, member_id):
    return w.db.get(ProjectMember, member_id)


def submit(w, **over):
    args = dict(repo_url=REPO, commit_sha=SHA, deployed_url=SITE, notes=None)
    args.update(over)
    return svc.create_submission(w.db, w.project, freelancer(w), **args)


def snapshot(w):
    return (w.db.query(Submission).count(), w.project.state, w.db.query(Job).count(), w.db.query(LedgerEntry).count())


# =============================== submitting ===============================

def test_a_submission_starts_an_attempt_moves_the_project_and_queues_the_checks(w):
    sub, job = submit(w, commit_sha=SHA.upper(), notes="  ready for review  ")
    assert (sub.attempt_no, sub.state, sub.commit_sha, sub.notes) == (1, "SUBMITTED", SHA, "ready for review")
    assert w.project.state == "VERIFYING"
    assert (job.type, job.payload_json, job.state) == ("AUTO_CHECKS", {"submission_id": sub.id}, "QUEUED")
    change = w.db.scalars(select(LedgerEntry).order_by(LedgerEntry.seq.desc())).first()
    assert change.type == "STATE_CHANGE" and change.meta_json["to"] == "VERIFYING" and change.actor.startswith("user:")


def test_blank_notes_are_stored_as_nothing(w):
    assert submit(w, notes="   ")[0].notes is None


@pytest.mark.parametrize("who", ["lead", "other_freelancer", "unsigned"])
def test_only_the_freelancer_of_the_signed_contract_can_submit(w, who):
    member = w.lead
    if who == "other_freelancer":
        u = User(email="x@x.com", display_name="X")
        w.db.add(u)
        w.db.flush()
        member = ProjectMember(project_id=w.project.id, user_id=u.id, role="FREELANCER")
        w.db.add(member)
        w.db.flush()
    if who == "unsigned":
        member, w.contract.signed_at = freelancer(w), None
    before = snapshot(w)
    with pytest.raises(svc.SubmissionError) as e:
        svc.create_submission(w.db, w.project, member, repo_url=REPO, commit_sha=SHA, deployed_url=SITE, notes=None)
    assert (e.value.code, e.value.status) == ("NOT_THE_FREELANCER", 403) and snapshot(w) == before


@pytest.mark.parametrize("state", ["PLEDGING", "VERIFYING", "PAYOUT_READY", "PAID", "REFUNDING"])
def test_work_is_accepted_only_while_the_project_is_in_progress(w, state):
    w.project.state = state
    before = snapshot(w)
    with pytest.raises(svc.SubmissionError) as e:
        submit(w)
    assert e.value.code == "PROJECT_STATE" and snapshot(w) == before


@pytest.mark.parametrize("over,code", [
    ({"repo_url": "https://gitlab.com/anu/x"}, "BAD_REPO_URL"), ({"repo_url": "https://github.com/anu"}, "BAD_REPO_URL"),
    ({"repo_url": "https://github.com/anu/x/tree/main"}, "BAD_REPO_URL"), ({"repo_url": ""}, "BAD_REPO_URL"),
    ({"commit_sha": "main"}, "BAD_COMMIT"), ({"commit_sha": "abc"}, "BAD_COMMIT"), ({"commit_sha": "g" * 40}, "BAD_COMMIT"),
    ({"commit_sha": SHA + "a"}, "BAD_COMMIT"), ({"commit_sha": ""}, "BAD_COMMIT"),
    ({"deployed_url": "http://velugu.example"}, "BAD_DEPLOYED_URL"), ({"deployed_url": "ftp://velugu.example"}, "BAD_DEPLOYED_URL"),
    ({"deployed_url": "https://u:p@velugu.example"}, "BAD_DEPLOYED_URL"), ({"deployed_url": "https://velugu.example:99999"}, "BAD_DEPLOYED_URL"),
    ({"deployed_url": "https://velugu .example"}, "BAD_DEPLOYED_URL"), ({"deployed_url": "https://"}, "BAD_DEPLOYED_URL"),
    ({"deployed_url": "https://" + "a" * 500 + ".example"}, "BAD_DEPLOYED_URL"), ({"deployed_url": "javascript:alert(1)"}, "BAD_DEPLOYED_URL"),
    ({"deployed_url": "http://localhost:3000"}, "BAD_DEPLOYED_URL"),            # only in dev
    ({"notes": "x" * 2001}, "NOTES_TOO_LONG"),
])
def test_bad_input_is_refused_with_a_clear_code_and_changes_nothing(w, monkeypatch, over, code):
    monkeypatch.setattr(get_settings(), "app_env", "prod")
    before = snapshot(w)
    with pytest.raises(svc.SubmissionError) as e:
        submit(w, **over)
    assert (e.value.code, e.value.status) == (code, 422) and snapshot(w) == before


def test_a_localhost_site_is_allowed_in_dev_only(w, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "dev")
    assert svc.valid_deployed_url("http://localhost:3000") and svc.valid_deployed_url("http://127.0.0.1:8080/x")
    assert not svc.valid_deployed_url("http://10.0.0.1")
    monkeypatch.setattr(get_settings(), "app_env", "prod")
    assert not svc.valid_deployed_url("http://localhost:3000")


def test_a_second_submission_cannot_start_while_one_is_being_checked(w):
    submit(w)
    w.project.state = "IN_PROGRESS"
    for state in svc.ACTIVE_STATES:
        w.db.scalars(select(Submission)).first().state = state
        with pytest.raises(svc.SubmissionError) as e:
            submit(w)
        assert e.value.code == "SUBMISSION_ACTIVE"


def test_a_resubmission_after_needs_changes_is_attempt_two_and_a_fourth_attempt_is_refused(w):
    for n in (1, 2, 3):
        sub, _ = submit(w)
        assert sub.attempt_no == n
        sub.state, w.project.state = "NEEDS_CHANGES", "IN_PROGRESS"
    before = snapshot(w)
    with pytest.raises(svc.SubmissionError) as e:
        submit(w)
    assert e.value.code == "MAX_ATTEMPTS" and snapshot(w) == before


# =============================== the check plan ===============================

def test_the_plan_has_the_defaults_then_the_sitemap_then_each_hint_without_duplicates():
    sub = Submission(repo_url=REPO, commit_sha=SHA, deployed_url=SITE)
    plan = svc.plan_checks(content(), sub)
    kinds = [(p["check_type"], p["inputs"].get("path"), p["requirement_code"], p["criterion_id"]) for p in plan]
    assert kinds == [
        ("REPO_PUBLIC", None, None, None), ("COMMIT_EXISTS", None, None, None), ("URL_REACHABLE", "/", None, None),
        ("URL_REACHABLE", "/stay", None, None), ("URL_REACHABLE", "/contact", None, None),
        ("PAGE_CONTAINS", "/contact", "REQ-001", "AC-1"), ("FILE_EXISTS", "src/form.js", "REQ-001", "AC-2"),
        ("MOBILE_VIEWPORT", "/", "REQ-002", "AC-1"), ("URL_REACHABLE", "/stay", "REQ-002", "AC-2"),
    ]
    assert plan[5]["inputs"]["text"] == "Send enquiry"
    assert svc.plan_checks(content(), sub) == plan                      # stable


def test_the_plan_is_capped_and_survives_an_empty_or_odd_brd():
    sub = Submission(repo_url=REPO, commit_sha=SHA, deployed_url=SITE)
    big = {"sitemap": [{"path": f"/p{i}"} for i in range(200)], "requirements": []}
    assert len(svc.plan_checks(big, sub)) == svc.MAX_CHECKS
    assert [p["check_type"] for p in svc.plan_checks({}, sub)] == ["REPO_PUBLIC", "COMMIT_EXISTS", "URL_REACHABLE"]
    odd = {"requirements": [{"code": "REQ-009", "acceptance_criteria": [{"id": "AC-1", "auto_check_hint": {"type": "NOPE"}}]}]}
    assert len(svc.plan_checks(odd, sub)) == 3


# =============================== the job ===============================

def checks_of(w, sub):
    return list(w.db.scalars(select(AutoCheck).where(AutoCheck.submission_id == sub.id).order_by(AutoCheck.id)))


def test_the_job_saves_every_check_with_its_requirement_and_moves_to_questioning(w):
    sub, _ = submit(w)
    net = Internet()
    out = svc.run_auto_checks(w.db, sub.id, net.checker())
    assert out == {"effect": "CHECKED", "submission_id": sub.id, "PASS": 9, "FAIL": 0, "ERROR": 0}
    assert sub.state == "QUESTIONING"
    rows = checks_of(w, sub)
    assert len(rows) == 9 and {r.result for r in rows} == {"PASS"}
    form = next(r for r in rows if r.check_type == "PAGE_CONTAINS")
    assert (form.requirement_code, form.input_json["criterion_id"], form.input_json["text"]) == ("REQ-001", "AC-1", "Send enquiry")
    assert next(r for r in rows if r.check_type == "REPO_PUBLIC").requirement_code is None


def test_each_page_is_fetched_once_however_many_criteria_use_it(w):
    sub, _ = submit(w)
    net = Internet()
    svc.run_auto_checks(w.db, sub.id, net.checker())
    paths = [r.url.path for r in net.sent if r.headers["host"] == "velugu.example"]
    assert sorted(paths) == ["/", "/contact", "/stay"]            # "/" is used by 2 checks, "/stay" by 2: one request each


def test_failures_and_errors_are_recorded_separately(w):
    sub, _ = submit(w)
    pages = {k: v for k, v in PAGES.items() if k != "/contact"}           # the enquiry page is missing
    github = {"/repos/anu/velugu-cove": (403, {"message": "rate limit"})}  # GitHub says no (rate limit) to everything
    out = svc.run_auto_checks(w.db, sub.id, Internet(pages, github).checker())
    by = {(r.check_type, r.input_json.get("path")): r for r in checks_of(w, sub)}
    assert by[("PAGE_CONTAINS", "/contact")].result == "FAIL" and by[("URL_REACHABLE", "/contact")].result == "FAIL"
    assert by[("REPO_PUBLIC", None)].result == "ERROR" and by[("COMMIT_EXISTS", None)].result == "FAIL"   # 404 from the script: unknown commit
    assert by[("FILE_EXISTS", "src/form.js")].result == "FAIL"
    assert out["PASS"] + out["FAIL"] + out["ERROR"] == 9 and out["ERROR"] >= 1 and out["FAIL"] >= 4
    assert sub.state == "QUESTIONING"           # a failed check does not stop the pipeline: it informs the judge


def test_an_unreachable_site_makes_errors_not_a_crash(w):
    sub, _ = submit(w)
    checker = AutoChecker(SafeFetcher(resolver=lambda h, p: (_ for _ in ()).throw(OSError()), transport=httpx.MockTransport(Internet())))
    out = svc.run_auto_checks(w.db, sub.id, checker)
    assert out["ERROR"] == 9 and sub.state == "QUESTIONING"


def test_running_the_job_twice_does_not_duplicate_anything(w):
    sub, _ = submit(w)
    svc.run_auto_checks(w.db, sub.id, Internet().checker())
    ids = [r.id for r in checks_of(w, sub)]
    assert svc.run_auto_checks(w.db, sub.id, Internet().checker()) == {"effect": "ALREADY_DONE", "state": "QUESTIONING"}
    assert [r.id for r in checks_of(w, sub)] == ids


def test_a_run_that_died_half_way_is_cleared_and_redone(w):
    sub, _ = submit(w)
    sub.state = "AUTO_CHECKING"
    w.db.add(AutoCheck(submission_id=sub.id, check_type="URL_REACHABLE", input_json={}, result="PASS"))
    w.db.flush()
    svc.run_auto_checks(w.db, sub.id, Internet().checker())
    assert len(checks_of(w, sub)) == 9 and sub.state == "QUESTIONING"


def test_the_job_ignores_unknown_and_already_judged_submissions(w):
    assert svc.run_auto_checks(w.db, 999, Internet().checker())["effect"] == "SKIPPED"
    sub, _ = submit(w)
    sub.state = "VERIFIED"
    assert svc.run_auto_checks(w.db, sub.id, Internet().checker())["effect"] == "ALREADY_DONE" and checks_of(w, sub) == []


def test_the_real_job_runner_runs_the_checks_with_the_installed_checker(w, db):
    sub, _ = submit(w)
    db.commit()
    svc.configure(lambda: Internet().checker())
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    assert jobs.run_one(factory) is True
    db.expire_all()
    assert db.get(Submission, sub.id).state == "QUESTIONING" and len(checks_of(w, sub)) == 9
    assert db.query(Job).one().state == "DONE"


@pytest.mark.parametrize("env,local", [("dev", True), ("prod", False), ("staging", False)])
def test_the_default_checker_is_a_locked_down_fetcher_and_allows_localhost_only_in_dev(monkeypatch, env, local):
    monkeypatch.setattr(get_settings(), "app_env", env)
    c = svc.default_checker()
    assert c.site.allowed_hosts is None and c.github.allowed_hosts == {"api.github.com"}
    assert c.site.allow_local is local and c.github.allow_local is False


# =============================== API ===============================

def url(w, tail=""):
    return f"/api/projects/{w.project.id}/submissions{tail}"


def freelancer_user(w):
    return w.db.get(User, freelancer(w).user_id)


BODY = {"repo_url": REPO, "commit_sha": SHA, "deployed_url": SITE, "notes": "done"}


def test_submit_then_read_over_http(client, w, db):
    r = client.post(url(w), json=BODY, headers=hdr(freelancer_user(w)))
    assert r.status_code == 202 and r.json()["attempt_no"] == 1
    sid = r.json()["submission_id"]
    svc.configure(lambda: Internet().checker())
    assert jobs.run_one(sessionmaker(bind=db.get_bind(), expire_on_commit=False)) is True
    db.expire_all()
    for who in (lead_user(w), freelancer_user(w)):                      # both members can read it
        got = client.get(f"/api/submissions/{sid}", headers=hdr(who)).json()
        assert got["state"] == "QUESTIONING" and got["auto_check_summary"] == {"PASS": 9, "FAIL": 0, "ERROR": 0}
        assert got["questions"] == [] and got["report"] is None and len(got["auto_checks"]) == 9
    listing = client.get(url(w), headers=hdr(lead_user(w))).json()["submissions"]
    assert [(s["id"], s["attempt_no"], s["state"]) for s in listing] == [(sid, 1, "QUESTIONING")]


def test_api_permissions_and_errors(client, w):
    assert client.post(url(w), json=BODY).status_code == 401
    assert client.post(url(w), json=BODY, headers=hdr(lead_user(w))).status_code == 403          # the lead is not the freelancer
    outsider = person(World(w.db, tag="o"), "FREELANCER", "outsider")
    assert client.post(url(w), json=BODY, headers=hdr(outsider)).status_code == 403
    assert client.post("/api/projects/9999/submissions", json=BODY, headers=hdr(freelancer_user(w))).status_code == 404
    bad = client.post(url(w), json={**BODY, "commit_sha": "main"}, headers=hdr(freelancer_user(w)))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "BAD_COMMIT"
    assert client.post(url(w), json={"repo_url": REPO}, headers=hdr(freelancer_user(w))).status_code == 422
    assert client.post(url(w), json={**BODY, "notes": "x" * 5001}, headers=hdr(freelancer_user(w))).status_code == 422
    assert w.db.query(Submission).count() == 0 and w.project.state == "IN_PROGRESS"
    ok = client.post(url(w), json=BODY, headers=hdr(freelancer_user(w)))
    assert ok.status_code == 202
    again = client.post(url(w), json=BODY, headers=hdr(freelancer_user(w)))
    assert again.status_code == 409 and again.json()["error"]["code"] in ("PROJECT_STATE", "SUBMISSION_ACTIVE")
    sid = ok.json()["submission_id"]
    assert client.get(f"/api/submissions/{sid}").status_code == 401
    assert client.get(f"/api/submissions/{sid}", headers=hdr(outsider)).status_code == 403
    assert client.get("/api/submissions/9999", headers=hdr(lead_user(w))).status_code == 404
    assert client.get(url(w), headers=hdr(outsider)).status_code == 403
    assert client.get("/api/projects/9999/submissions", headers=hdr(lead_user(w))).status_code == 404
