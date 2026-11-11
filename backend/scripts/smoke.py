"""Check that a running BriefPay (with the demo data loaded) shows what the demo story needs. Read-only apart from signing in.

    cd backend
    .venv/Scripts/python scripts/smoke.py                                   # API on http://localhost:8000/api
    .venv/Scripts/python scripts/smoke.py --api http://localhost:8000/api --web http://localhost:3000

Each line is one fact about the demo data, in plain words: [ OK ] or [FAIL]. Exit code 0 means every check passed.
Needs the demo seed (`scripts/seed.py`). With --web it also checks that every page of the web app is served.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.seed_demo import DOMAIN, PEOPLE, TITLE_A, TITLE_B  # noqa: E402

PAGES = ["", "login", "project", "ba", "brd", "contract", "campaign", "submit", "verify", "plans", "ledger", "audit"]


class Api:
    """A tiny wrapper so the same checks run against a live server (httpx) or an in-process test client."""

    def __init__(self, session, base: str = ""):
        self.session, self.base = session, base.rstrip("/")
        self.tokens: dict[str, str] = {}

    def _headers(self, who: str | None):
        return {"Authorization": f"Bearer {self.tokens[who]}"} if who else {}

    def get(self, path: str, who: str | None = None):
        r = self.session.get(self.base + path, headers=self._headers(who))
        return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else None)

    def login(self, key: str):
        name = PEOPLE[key][0]
        r = self.session.post(self.base + "/auth/login", json={"email": f"{key}@{DOMAIN}", "display_name": name})
        assert r.status_code == 200, f"{key} could not sign in ({r.status_code})"
        self.tokens[key] = r.json()["token"]


def check(label: str, results: list, fn):
    try:
        detail = fn()
        results.append((True, label, detail or ""))
    except AssertionError as e:
        results.append((False, label, str(e) or "failed"))
    except Exception as e:  # noqa: BLE001  (a broken server must show up as a failed line, not a traceback)
        results.append((False, label, f"{type(e).__name__}: {e}"))


def run(api: Api, web_get=None, out=print) -> int:
    results: list = []
    ctx: dict = {}

    def projects():
        code, data = api.get("/projects")
        assert code == 200, f"the project list answered {code}"
        by_title = {p["title"]: p for p in data["projects"]}
        assert TITLE_A in by_title and TITLE_B in by_title, f"the two demo projects are not both there (found {sorted(by_title)})"
        ctx["a"], ctx["b"] = by_title[TITLE_A]["id"], by_title[TITLE_B]["id"]
        return f"{len(by_title)} projects, including both demo ones"

    check("The server is up and the database answers", results, lambda: (lambda c, d: (c == 200 or (_ for _ in ()).throw(AssertionError(f"health answered {c}"))) and "ok")(*api.get("/healthz")))
    check("Anyone can see the two demo projects", results, projects)
    if "a" not in ctx:
        return report(results, out)
    a, b = ctx["a"], ctx["b"]

    def people():
        roles = {}
        for key in PEOPLE:
            api.login(key)
            code, me = api.get("/auth/me", key)
            assert code == 200, f"{key}: /auth/me answered {code}"
            roles[key] = {m["project_id"]: m["role"] for m in me["memberships"]}
        assert roles["lakshmi"].get(a) == "LEAD" and roles["lakshmi"].get(b) == "LEAD", "Lakshmi should lead both projects"
        assert roles["ravi"].get(b) == "SPONSOR" and roles["meena"].get(b) == "SPONSOR", "Ravi and Meena should be sponsors"
        assert roles["arjun"].get(b) == "FREELANCER", "Arjun should be the freelancer"
        return "Lakshmi leads, Ravi and Meena sponsor, Arjun builds"

    check("The four demo people can sign in with the right roles", results, people)
    if "lakshmi" not in api.tokens:
        return report(results, out)

    def round_one():
        code, ledger = api.get(f"/projects/{a}/ledger")
        assert code == 200 and ledger["public"] is True, "the ledger should be public for a visitor"
        types = [r["type"] for r in ledger["rows"]]
        assert "PLEDGE_VOIDED" in types and "PLEDGE_CAPTURED" not in types, "round one should have released holds and collected nothing"
        assert ledger["totals"]["pool_balance_cents"] == 0, "nothing should be in the pool"
        code, p = api.get(f"/projects/{a}")
        assert p["campaign"]["state"] == "FAILED", f"round one should be FAILED (it is {p['campaign']['state']})"
        return "round one missed its goal, holds released, nobody charged"

    check("Round one: the goal was missed and nobody was charged", results, round_one)

    def funded():
        code, ledger = api.get(f"/projects/{b}/ledger")
        assert ledger["totals"]["pool_balance_cents"] == 40000, f"the pool should hold $400.00 (it holds {ledger['totals']['pool_balance_cents']})"
        assert sum(1 for r in ledger["rows"] if r["type"] == "PLEDGE_CAPTURED") == 3, "three pledges should have been collected"
        seqs = [r["seq"] for r in ledger["rows"]]
        assert seqs == list(range(1, len(seqs) + 1)), "ledger rows should be numbered without gaps"
        code, camp = api.get(f"/projects/{b}")
        assert camp["campaign"]["state"] == "CAPTURED", "the campaign should be funded"
        return f"$400.00 collected from 3 pledges; {len(seqs)} ledger rows, no gaps"

    check("The build-phase project is funded: $400 in the pool", results, funded)

    def brief_and_contract():
        code, brd = api.get(f"/projects/{b}/brd")
        assert code == 200 and brd["status"] == "APPROVED" and len(brd["sha256"]) == 64, "the brief should be approved and fingerprinted"
        assert len(brd["content"]["requirements"]) == 9, f"nine requirements expected (found {len(brd['content']['requirements'])})"
        code, c = api.get(f"/projects/{b}/contract", "lakshmi")
        assert code == 200 and c["status"] == "SIGNED" and c["brd_sha256"] == brd["sha256"], "the contract should be signed against that exact brief"
        return "brief approved (9 requirements); contract signed against the same fingerprint"

    check("The brief is approved and the contract is signed against it", results, brief_and_contract)

    def verification():
        code, subs = api.get(f"/projects/{b}/submissions", "lakshmi")
        assert code == 200 and len(subs["submissions"]) == 2, "two submissions expected"
        first, second = subs["submissions"][0], subs["submissions"][-1]
        assert first["state"] == "NEEDS_CHANGES" and second["state"] == "VERIFIED", f"expected rejected then verified (got {first['state']}, {second['state']})"
        code, d = api.get(f"/submissions/{second['id']}", "lakshmi")
        assert d["report"]["overall"] == "VERIFIED" and d["report"]["must_pass_pct"] == 100, "the second report should pass every must-have"
        code, d1 = api.get(f"/submissions/{first['id']}", "lakshmi")
        assert d1["auto_check_summary"]["FAIL"] >= 1, "the first attempt should have a failing automatic check"
        return "attempt 1 rejected (a check failed), attempt 2 verified (100% of must-haves)"

    check("The work was rejected once, then verified", results, verification)

    def plans():
        code, data = api.get(f"/projects/{b}/plans", "lakshmi")
        assert code == 200 and data["plans"], "the build-phase project should have a money plan"
        kinds = {p["kind"]: p["state"] for p in data["plans"]}
        assert kinds.get("CAPTURE_PLEDGES") == "DONE", f"the collect-pledges plan should be done (it is {kinds.get('CAPTURE_PLEDGES')})"
        code, a_plans = api.get(f"/projects/{a}/plans", "lakshmi")
        assert any(p["kind"] == "RELEASE_HOLDS" and p["state"] == "DONE" for p in a_plans["plans"]), "round one should have a finished release-holds plan"
        return "collect-pledges done (build phase); release-holds done (round one)"

    check("Money plans: collected on one project, released on the other", results, plans)

    def privacy():
        code, _ = api.get(f"/projects/{b}/plans")
        assert code in (401, 403), f"a visitor should not see plans (got {code})"
        code, _ = api.get(f"/projects/{b}/agent-runs")
        assert code in (401, 403), f"a visitor should not see the AI audit trail (got {code})"
        code, runs = api.get(f"/projects/{b}/agent-runs", "lakshmi")
        assert code == 200, f"a member should see the AI audit trail (got {code})"
        code, ledger = api.get(f"/projects/{b}/ledger")
        assert "@" not in str(ledger), "the public ledger must not show email addresses"
        code, camp = api.get(f"/campaigns/{(api.get(f'/projects/{b}')[1]['campaign']['id'])}")
        assert "lead" not in camp, "the public campaign view must not carry the organiser's data"
        return "visitors cannot see plans or the audit trail; the public ledger shows no emails"

    check("Privacy: visitors see the public parts only", results, privacy)

    def organiser_view():
        cid = api.get(f"/projects/{b}")[1]["campaign"]["id"]
        code, camp = api.get(f"/campaigns/{cid}", "lakshmi")
        assert code == 200 and "lead" in camp, "the lead should get the organiser's data"
        code, camp = api.get(f"/campaigns/{cid}", "ravi")
        assert code == 200 and "lead" not in camp, "a sponsor should not get the organiser's data"
        return "only the lead gets the organiser's data"

    check("Only the lead sees the organiser's view of the campaign", results, organiser_view)

    if web_get is not None:
        for page in PAGES:
            def served(page=page):
                code, text = web_get("/" + (page + "/" if page else ""))
                assert code == 200, f"/{page} answered {code}"
                assert "BriefPay" in text, f"/{page} does not look like the BriefPay app"
                return ""
            check(f"The web app serves /{page}", results, served)
    return report(results, out)


def report(results: list, out=print) -> int:
    for ok, label, detail in results:
        out(f"[ OK ] {label}" + (f" - {detail}" if detail else "") if ok else f"[FAIL] {label} - {detail}")
    failed = sum(1 for ok, _, _ in results if not ok)
    out("")
    out(f"{len(results) - failed} of {len(results)} checks passed." + ("" if not failed else f" {failed} FAILED."))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    import httpx
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--api", default="http://localhost:8000/api", help="the API address, ending in /api")
    ap.add_argument("--web", default=None, help="the web app address (optional), for example http://localhost:3000")
    args = ap.parse_args(argv)
    with httpx.Client(timeout=30) as session:
        web_get = None
        if args.web:
            base = args.web.rstrip("/")
            web_get = lambda path: (lambda r: (r.status_code, r.text))(session.get(base + path, follow_redirects=True))  # noqa: E731
        return run(Api(session, args.api), web_get)


if __name__ == "__main__":
    raise SystemExit(main())
