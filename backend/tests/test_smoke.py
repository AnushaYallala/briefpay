"""The smoke-check script (scripts/smoke.py) works against the demo data, and fails loudly when something is wrong."""
import importlib.util
from pathlib import Path

import pytest

from tests.test_seed import seeded  # noqa: F401

SPEC = importlib.util.spec_from_file_location("smoke", Path(__file__).resolve().parents[1] / "scripts" / "smoke.py")
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class InProcess:
    """Adapts FastAPI's TestClient (whose paths start with /api) to the small interface the script uses."""

    def __init__(self, client):
        self.client = client

    def get(self, path, headers=None):
        return self.client.get("/api" + path, headers=headers)

    def post(self, path, json=None, headers=None):
        return self.client.post("/api" + path, json=json, headers=headers)


def run(client, web_get=None):
    lines: list[str] = []
    code = smoke.run(smoke.Api(InProcess(client), ""), web_get, out=lines.append)
    return code, lines


def test_every_check_passes_on_the_demo_data(client, seeded):  # noqa: F811
    code, lines = run(client)
    assert code == 0, "\n".join(lines)
    assert sum(1 for l in lines if l.startswith("[ OK ]")) == 10 and not any(l.startswith("[FAIL]") for l in lines)
    assert lines[-1] == "10 of 10 checks passed."


def test_an_empty_database_fails_with_a_reason_and_stops_early(client):
    code, lines = run(client)
    assert code == 1
    assert any(l.startswith("[FAIL] Anyone can see the two demo projects") and "not both there" in l for l in lines)
    assert len(lines) == 4                                                  # the health line, the failed line, a blank line, the summary
    assert lines[-1] == "1 of 2 checks passed. 1 FAILED."


def test_a_broken_fact_is_reported_by_name(client, seeded, db):  # noqa: F811
    from app.models import Campaign
    db.get(Campaign, 1).state = "OPEN"                                      # pretend round one never ended
    db.commit()
    code, lines = run(client)
    assert code == 1
    assert any(l.startswith("[FAIL] Round one") and "round one should be FAILED (it is OPEN)" in l for l in lines)
    assert sum(1 for l in lines if l.startswith("[FAIL]")) == 1             # only that fact is reported


def test_the_web_checks_report_each_page(client, seeded):  # noqa: F811
    served = []

    def web_get(path):
        served.append(path)
        return (200, "<title>BriefPay</title>") if path != "/audit/" else (404, "")

    code, lines = run(client, web_get)
    assert served == ["/"] + [f"/{p}/" for p in smoke.PAGES[1:]]
    assert code == 1 and [l for l in lines if l.startswith("[FAIL]")] == ["[FAIL] The web app serves /audit - /audit answered 404"]
    code, lines = run(client, lambda path: (200, "some other site"))
    assert code == 1 and sum(1 for l in lines if "does not look like the BriefPay app" in l) == len(smoke.PAGES)


def test_a_crashing_check_is_a_failed_line_not_a_traceback():
    class Dead:
        def get(self, *a, **k):
            raise ConnectionError("refused")

        post = get

    lines: list[str] = []
    assert smoke.run(smoke.Api(Dead(), ""), None, out=lines.append) == 1
    assert lines[0] == "[FAIL] The server is up and the database answers - ConnectionError: refused"
    assert any("Anyone can see the two demo projects" in l and l.startswith("[FAIL]") for l in lines)


def test_the_dev_server_starts_in_demo_mode_but_a_build_never_does_by_itself():
    root = Path(__file__).resolve().parents[2]
    dev = (root / "frontend" / ".env.development").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_DEMO_MODE=true" in dev and "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api" in dev
    secretish = [l for l in dev.splitlines() if l and not l.startswith("#") and not l.startswith("NEXT_PUBLIC_")]
    assert secretish == []                                                              # only public values may live in this file
    assert not (root / "frontend" / ".env.production").exists() and not (root / "frontend" / ".env").exists()
    render = (root / "render.yaml").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_DEMO_MODE" in render                                            # the deployed site sets its own value on purpose


def _break_brief(db):
    from app.models import BRD
    for b in db.query(BRD).all():
        b.status = "PENDING_APPROVAL"


def _break_contract(db):
    from app.models import Contract
    for c in db.query(Contract).all():
        c.signed_at = None


def _break_verification(db):
    from app.models import Submission
    for s in db.query(Submission).all():
        s.state = "NEEDS_CHANGES"


def _break_plan(db):
    from app.models import MoneyPlan
    for p in db.query(MoneyPlan).filter(MoneyPlan.kind == "CAPTURE_PLEDGES").all():
        p.state = "FAILED"


def _break_roles(db):
    from app.models import ProjectMember
    for m in db.query(ProjectMember).filter(ProjectMember.role == "FREELANCER").all():
        m.role = "SUPPORTER"


@pytest.mark.parametrize("breaker,line_start,reason", [
    (_break_brief, "[FAIL] The brief is approved and the contract is signed against it", "the brief should be approved"),
    (_break_contract, "[FAIL] The brief is approved and the contract is signed against it", "the contract should be signed"),
    (_break_verification, "[FAIL] The work was rejected once, then verified", "expected rejected then verified"),
    (_break_plan, "[FAIL] Money plans: collected on one project, released on the other", "the collect-pledges plan should be done"),
    (_break_roles, "[FAIL] The four demo people can sign in with the right roles", "Arjun should be the freelancer"),
])
def test_each_fact_is_checked_on_its_own(client, seeded, db, breaker, line_start, reason):  # noqa: F811
    breaker(db)
    db.commit()
    code, lines = run(client)
    failed = [l for l in lines if l.startswith("[FAIL]")]
    assert code == 1 and len(failed) == 1, failed
    assert failed[0].startswith(line_start) and reason in failed[0]


# ---- every individual assertion in the script is proven to bite: record the real answers once, spoil one field at a time ----

class Recording(smoke.Api):
    def __init__(self, session):
        super().__init__(session, "")
        self.log = {}

    def get(self, path, who=None):
        res = super().get(path, who)
        self.log[(path, who)] = res
        return res


class Replay(smoke.Api):
    def __init__(self, log, mutate):
        super().__init__(None, "")
        self.log, self.mutate = log, mutate

    def get(self, path, who=None):
        import copy
        code, data = copy.deepcopy(self.log[(path, who)])
        fn = self.mutate.get((path, who))
        return fn(code, data) if fn else (code, data)

    def login(self, key):
        self.tokens[key] = "token"


def test_every_assertion_in_the_script_fails_on_its_own_message(client, seeded):  # noqa: F811
    import copy
    rec = Recording(InProcess(client))
    assert smoke.run(rec, None, out=lambda _: None) == 0
    a, b = seeded["failed_round_project_id"], seeded["payout_ready_project_id"]
    cid = rec.log[(f"/projects/{b}", None)][1]["campaign"]["id"]
    L = (f"/projects/{b}/ledger", None)
    A = (f"/projects/{a}/ledger", None)

    def edit(fn):
        def wrapped(code, data):
            fn(data)
            return code, data
        return wrapped

    def drop_row(d):
        del d["rows"][3]

    def retype(old, new):
        def f(d):
            next(r for r in d["rows"] if r["type"] == old)["type"] = new
        return f

    def memberships(who, project, role):
        def f(d):
            for m in d["memberships"]:
                if m["project_id"] == project:
                    m["role"] = role
        return f

    cases = {
        "round one collected money": (A, edit(retype("PLEDGE_VOIDED", "PLEDGE_CAPTURED")), "released holds and collected nothing"),
        "round one ledger not public": (A, edit(lambda d: d.update(public=False)), "ledger should be public"),
        "round one pool not empty": (A, edit(lambda d: d["totals"].update(pool_balance_cents=100)), "nothing should be in the pool"),
        "round one not failed": ((f"/projects/{a}", None), edit(lambda d: d["campaign"].update(state="OPEN")), "round one should be FAILED"),
        "pool short": (L, edit(lambda d: d["totals"].update(pool_balance_cents=39999)), "the pool should hold $400.00"),
        "a pledge not collected": (L, edit(retype("PLEDGE_CAPTURED", "PLEDGE_VOIDED")), "three pledges should have been collected"),
        "ledger gap": (L, edit(drop_row), "numbered without gaps"),
        "campaign not funded": ((f"/projects/{b}", None), edit(lambda d: d["campaign"].update(state="OPEN")), "the campaign should be funded"),
        "brief not approved": ((f"/projects/{b}/brd", None), edit(lambda d: d.update(status="PENDING_APPROVAL")), "approved and fingerprinted"),
        "brief fingerprint short": ((f"/projects/{b}/brd", None), edit(lambda d: d.update(sha256="abc")), "approved and fingerprinted"),
        "eight requirements": ((f"/projects/{b}/brd", None), edit(lambda d: d["content"]["requirements"].pop()), "nine requirements expected"),
        "contract unsigned": ((f"/projects/{b}/contract", "lakshmi"), edit(lambda d: d.update(status="OFFERED")), "the contract should be signed"),
        "contract for another brief": ((f"/projects/{b}/contract", "lakshmi"), edit(lambda d: d.update(brd_sha256="0" * 64)), "that exact brief"),
        "one submission": ((f"/projects/{b}/submissions", "lakshmi"), edit(lambda d: d["submissions"].pop()), "two submissions expected"),
        "first attempt not rejected": ((f"/projects/{b}/submissions", "lakshmi"), edit(lambda d: d["submissions"][0].update(state="VERIFIED")), "expected rejected then verified"),
        "second report weak": (None, None, "the second report should pass every must-have"),
        "first attempt had no failing check": (None, None, "failing automatic check"),
        "visitor sees plans": ((f"/projects/{b}/plans", None), lambda c, d: (200, {"plans": []}), "a visitor should not see plans"),
        "visitor sees audit trail": ((f"/projects/{b}/agent-runs", None), lambda c, d: (200, {"rows": []}), "a visitor should not see the AI audit trail"),
        "member refused audit trail": ((f"/projects/{b}/agent-runs", "lakshmi"), lambda c, d: (403, d), "a member should see the AI audit trail"),
        "email in the public ledger": (L, edit(lambda d: d["rows"][0].update(counterparty="someone@example.com")), "must not show email addresses"),
        "public campaign carries organiser data": ((f"/campaigns/{cid}", None), edit(lambda d: d.update(lead={})), "must not carry the organiser's data"),
        "lead gets no organiser data": ((f"/campaigns/{cid}", "lakshmi"), edit(lambda d: d.pop("lead", None)), "the lead should get the organiser's data"),
        "sponsor gets organiser data": ((f"/campaigns/{cid}", "ravi"), edit(lambda d: d.update(lead={})), "a sponsor should not get the organiser's data"),
        "Lakshmi not lead of one": (("/auth/me", "lakshmi"), edit(lambda d: memberships("lakshmi", a, "SPONSOR")(d)), "Lakshmi should lead both projects"),
        "Ravi not a sponsor": (("/auth/me", "ravi"), edit(lambda d: memberships("ravi", b, "SUPPORTER")(d)), "Ravi and Meena should be sponsors"),
        "Meena not a sponsor": (("/auth/me", "meena"), edit(lambda d: memberships("meena", b, "SUPPORTER")(d)), "Ravi and Meena should be sponsors"),
        "Arjun not the freelancer": (("/auth/me", "arjun"), edit(lambda d: memberships("arjun", b, "SUPPORTER")(d)), "Arjun should be the freelancer"),
        "auth/me broken": (("/auth/me", "ravi"), lambda c, d: (500, d), "/auth/me answered 500"),
        "project list broken": (("/projects", None), lambda c, d: (500, d), "the project list answered 500"),
    }
    subs = rec.log[(f"/projects/{b}/submissions", "lakshmi")][1]["submissions"]
    cases["second report weak"] = ((f"/submissions/{subs[-1]['id']}", "lakshmi"), edit(lambda d: d["report"].update(must_pass_pct=90)), cases["second report weak"][2])
    cases["first attempt had no failing check"] = ((f"/submissions/{subs[0]['id']}", "lakshmi"), edit(lambda d: d["auto_check_summary"].update(FAIL=0)), cases["first attempt had no failing check"][2])

    silent = lambda _: None  # noqa: E731
    assert smoke.run(Replay(copy.deepcopy(rec.log), {}), None, out=silent) == 0          # the untouched recording passes
    for name, (key, fn, fragment) in cases.items():
        lines: list[str] = []
        code = smoke.run(Replay(copy.deepcopy(rec.log), {key: fn}), None, out=lines.append)
        failed = [l for l in lines if l.startswith("[FAIL]")]
        assert code == 1 and len(failed) == 1 and fragment in failed[0], f"{name}: {failed or 'nothing failed'}"
