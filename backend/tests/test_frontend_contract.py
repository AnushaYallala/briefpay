"""The web app (frontend/) and the API must agree. These tests read the front-end source and fail if either side drifts."""
import re
from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.services import seed_demo as sd
from app.services.state_machines import CAMPAIGN_TRANSITIONS, PROJECT_TRANSITIONS
from tests.test_seed import seeded  # noqa: F401  (the demo data, to compare real responses)

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "frontend" / "src"


def read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def block(text: str, start: str) -> str:
    """The body of `export const NAME ... = {` up to its closing `};`."""
    i = text.index(start)
    return text[i: text.index("\n};", i)]


def keys_of(text: str) -> set[str]:
    return set(re.findall(r"^  ([A-Z_]+): \{", text, re.M))


def matching(text: str, open_at: int) -> int:
    """Index of the `}` that closes the `{` at `open_at`."""
    depth, i = 0, open_at
    while True:
        depth += (text[i] == "{") - (text[i] == "}")
        if depth == 0:
            return i
        i += 1


def body_of(type_source: str, name: str) -> str:
    """The text inside the braces of `export type NAME = [Base &] { ... };`, written on one line or many."""
    start = type_source.index("{", type_source.index(f"export type {name} = "))
    return type_source[start + 1: matching(type_source, start)]


def fields_of(type_source: str, name: str) -> set[str]:
    """Top-level field names of the type (fields of nested inline objects are not included)."""
    body = body_of(type_source, name)
    while (flat := re.sub(r"\{[^{}]*\}", "", body)) != body:
        body = flat
    return set(re.findall(r"(\w+)\??:", body))


def test_every_project_and_campaign_state_has_words_in_the_web_app():
    states = read("lib/states.ts")
    assert keys_of(block(states, "export const PROJECT_STATES")) == set(PROJECT_TRANSITIONS)
    assert keys_of(block(states, "export const CAMPAIGN_STATES")) == set(CAMPAIGN_TRANSITIONS)


def test_the_demo_people_in_the_web_app_are_the_seeded_ones():
    personas = read("lib/personas.ts")
    found = re.findall(r'\{ key: "(\w+)", name: "(\w+)", role: "[^"]+", email: "([^"]+)" \}', personas)
    assert [k for k, _, _ in found] == list(sd.PEOPLE)
    for key, name, email in found:
        assert email == sd.email(key) and name == sd.PEOPLE[key][0]


def test_the_types_match_what_the_api_really_returns(client, seeded):  # noqa: F811
    types = read("lib/types.ts")
    cards = client.get("/api/projects").json()["projects"]
    assert cards and all(set(c) == fields_of(types, "ProjectCard") for c in cards)
    with_campaign = [c for c in cards if c["campaign"]]
    assert with_campaign and all(set(c["campaign"]) == fields_of(types, "CampaignSummary") for c in with_campaign)


def test_login_and_me_have_the_shape_the_web_app_expects(client, seeded):  # noqa: F811
    types = read("lib/types.ts")
    login = client.post("/api/auth/login", json={"email": sd.email("lakshmi"), "display_name": "Lakshmi"}).json()
    assert set(login) == {"token", "user"} and set(login["user"]) == fields_of(types, "User")
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login['token']}"}).json()
    assert set(me) == {"user", "memberships"} and me["memberships"] and set(me["memberships"][0]) == fields_of(types, "Membership")
    assert {m["role"] for m in me["memberships"]} <= {"LEAD", "SPONSOR", "SUPPORTER", "FREELANCER"}


def test_the_error_shape_the_web_app_parses_is_the_one_the_api_sends(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and set(r.json()["error"]) == {"code", "message", "details"}
    assert r.json()["error"]["code"] in re.findall(r'"([A-Z_]+)"', re.search(r"SIGNED_OUT_CODES = new Set\(\[(.*?)\]\)", read("lib/api.ts")).group(1))
    bad = client.post("/api/auth/login", json={"email": "not-an-email", "display_name": "x"})
    assert bad.status_code == 422 and isinstance(bad.json()["detail"], list) and {"loc", "msg"} <= set(bad.json()["detail"][0])


def test_the_web_app_signs_out_on_exactly_the_codes_the_api_uses_for_a_missing_or_bad_token(client):
    missing = client.get("/api/auth/me").json()["error"]["code"]
    bad = client.get("/api/auth/me", headers={"Authorization": "Bearer junk"}).json()["error"]["code"]
    listed = set(re.findall(r'"([A-Z_]+)"', re.search(r"SIGNED_OUT_CODES = new Set\(\[(.*?)\]\)", read("lib/api.ts")).group(1)))
    assert (missing, bad) == ("UNAUTHENTICATED", "BAD_TOKEN") and listed == {missing, bad}


def test_every_public_variable_the_web_app_reads_is_documented():
    used = set()
    for p in SRC.rglob("*.ts*"):
        used |= set(re.findall(r"process\.env\.(NEXT_PUBLIC_\w+)", p.read_text(encoding="utf-8")))
    example = (REPO / ".env.example").read_text(encoding="utf-8")
    assert used and all(f"{name}=" in example for name in used), used
    blueprint = yaml.safe_load((REPO / "render.yaml").read_text(encoding="utf-8"))
    web = {e["key"] for s in blueprint["services"] if s["name"] == "briefpay-web" for e in s["envVars"]}
    assert used <= web, used - web


def test_the_defaults_of_the_web_app_match_the_backend_defaults():
    api = read("lib/api.ts")
    s = Settings(_env_file=None)
    assert f'"{s.app_base_url}/api"' in api                                      # default API base
    package = (REPO / "frontend" / "package.json").read_text(encoding="utf-8")
    port = re.search(r"next dev -p (\d+)", package).group(1)
    assert f"http://localhost:{port}" in s.cors_origin_list and s.web_base_url == f"http://localhost:{port}"


def test_the_web_app_is_a_static_export_with_client_components_only():
    config = (REPO / "frontend" / "next.config.mjs").read_text(encoding="utf-8")
    assert 'output: "export"' in config and "unoptimized: true" in config
    assert not (SRC / "app" / "api").exists(), "no Next API routes in a static export (D-010)"
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", config, flags=re.S)                 # comments may mention the words
    assert not re.search(r"\brewrites\b|\bredirects\b|\bheaders\b", code)


@pytest.mark.parametrize("name", ["package-lock.json", "package.json", "tsconfig.json", "next.config.mjs"])
def test_the_files_a_clean_checkout_needs_are_there(name):
    assert (REPO / "frontend" / name).is_file()


def test_every_project_state_has_a_step_and_an_explanation_in_the_web_app():
    steps = read("lib/steps.ts")
    step_of = set(re.findall(r"\b([A-Z_]{3,}): (?:\d|null)\b", block(steps, "export const STEP_OF")))
    what_next = keys_of_lines(block(steps, "export const WHAT_NEXT"))
    assert step_of == set(PROJECT_TRANSITIONS) == what_next


def keys_of_lines(text: str) -> set[str]:
    return set(re.findall(r'^  ([A-Z_]+): "', text, re.M))


def nested_fields(type_source: str, name: str, field: str) -> set[str]:
    """Field names of an inline object type such as `holds: { count: number; ... }` inside `export type NAME`."""
    body = body_of(type_source, name)
    start = body.index("{", body.index(f"{field}: {{"))
    return set(re.findall(r"(\w+)\??:", body[start + 1: matching(body, start)]))


def test_the_project_page_types_match_a_real_member_and_visitor_response(client, seeded):  # noqa: F811
    types = read("lib/types.ts")
    pid = seeded["payout_ready_project_id"]
    visitor = client.get(f"/api/projects/{pid}").json()
    login = client.post("/api/auth/login", json={"email": sd.email("lakshmi"), "display_name": "Lakshmi"}).json()
    lead = client.get(f"/api/projects/{pid}", headers={"Authorization": f"Bearer {login['token']}"}).json()
    declared = fields_of(types, "ProjectDetail") | fields_of(types, "ProjectCard")
    for view in (visitor, lead):
        assert set(view) - {"transcript"} <= declared and (declared - {"transcript"}) <= set(view)
    member_fields = fields_of(types, "Member")
    seen = set().union(*[set(m) for m in visitor["members"] + lead["members"]])
    assert seen == member_fields, (seen ^ member_fields)                       # every declared field really exists, and none is missing
    assert {"id", "role", "display_name", "business_name", "business_type"} <= set(visitor["members"][0])
    assert "email" not in visitor["members"][0] and "email" in lead["members"][0]          # visitors never get contact details
    assert visitor["viewer"] is None and set(lead["viewer"]) == {"role", "member_id"}


def test_the_money_box_type_matches_the_real_response(client, seeded):  # noqa: F811
    types = read("lib/types.ts")
    login = client.post("/api/auth/login", json={"email": sd.email("lakshmi"), "display_name": "Lakshmi"}).json()
    got = client.get(f"/api/projects/{seeded['payout_ready_project_id']}/money", headers={"Authorization": f"Bearer {login['token']}"}).json()
    assert set(got) == fields_of(types, "Money") | set()
    assert set(got["holds"]) == nested_fields(types, "Money", "holds")
    assert set(got["campaign"]) == nested_fields(types, "Money", "campaign")
    plan = client.get(f"/api/projects/{seeded['payout_ready_project_id']}/money", headers={"Authorization": f"Bearer {login['token']}"}).json()["open_plans"]
    assert isinstance(plan, list)


def test_the_plan_words_in_the_money_box_cover_every_plan_kind():
    kinds = set(re.findall(r"\b([A-Z_]{6,}): \"", block(read("lib/plans.ts"), "export const PLAN_WORDS")))
    assert kinds == {"CAPTURE_PLEDGES", "RELEASE_HOLDS", "FREELANCER_PAYOUT", "REFUND_CAPTURED"}


def auth_header(client, who="lakshmi"):
    login = client.post("/api/auth/login", json={"email": sd.email(who), "display_name": who.title()}).json()
    return {"Authorization": f"Bearer {login['token']}"}


def test_the_ledger_types_match_the_real_responses(client, seeded):  # noqa: F811
    types = read("lib/types.ts")
    pid = seeded["payout_ready_project_id"]
    for headers in (None, auth_header(client)):
        got = client.get(f"/api/projects/{pid}/ledger", headers=headers).json()
        assert set(got) == fields_of(types, "LedgerResponse") and set(got["totals"]) == nested_fields(types, "LedgerResponse", "totals")
        assert got["rows"] and all(set(r) == fields_of(types, "LedgerRow") for r in got["rows"])
    assert client.get(f"/api/projects/{pid}/ledger").json()["public"] is True


def test_every_ledger_row_type_has_words_in_the_web_app():
    from app.services.ledger import LEDGER_TYPES
    labels = set(re.findall(r'^  ([A-Z_]+): "', block(read("lib/ledger.ts"), "export const TYPE_LABELS"), re.M))
    assert labels == set(LEDGER_TYPES)


def test_the_paypal_match_response_matches_what_the_web_app_reads(client, seeded):  # noqa: F811
    from app.services import ledger_match
    types = read("lib/types.ts")
    got = client.get(f"/api/projects/{seeded['payout_ready_project_id']}/ledger/paypal-match", headers=auth_header(client)).json()
    assert set(got) == fields_of(types, "MatchResponse")
    statuses = set(re.findall(r'"([A-Z_]+)"', re.search(r"export type MatchStatus = (.*?);", types).group(1)))
    assert statuses == set(ledger_match.RESULTS) == set(got["counts"])
    assert got["results"] and all(set(v) <= {"status", "detail", "paypal_ref", "paypal_status", "paypal_cents"} and v["status"] in statuses for v in got["results"].values())
    symbols = set(re.findall(r"^  ([A-Z_]+): \{ symbol:", read("lib/ledger.ts"), re.M))
    assert symbols == set(ledger_match.RESULTS)


def test_the_status_chips_the_ledger_prints_are_the_ones_the_grid_knows():
    from app.services.ledger_views import STATUS_CHIP
    assert set(STATUS_CHIP) <= set(re.findall(r'^  ([A-Z_]+): "', read("lib/ledger.ts"), re.M))


def test_the_ledger_refresh_rate_is_gentle():
    assert re.search(r"REFRESH_MS = 15000;", read("lib/ledger.ts"))


def test_the_audit_trail_type_matches_the_real_response_and_the_words_cover_every_agent(client, db, seeded):  # noqa: F811
    from app.agents import ba_agent, brd_generator, guardian_llm, strategist, verifier
    from app.models.tables import AgentRun
    types = read("lib/types.ts")
    pid = seeded["payout_ready_project_id"]
    db.add(AgentRun(project_id=pid, agent="BA_SCORE", provider="gemini", model="m", prompt_version="v1", input_hash="h" * 64, latency_ms=12,
                    input_tokens=1, output_tokens=2, status="OK", output_json={"a": 1}, error=None))
    db.commit()
    got = client.get(f"/api/projects/{pid}/agent-runs", headers=auth_header(client)).json()
    assert set(got) == fields_of(types, "AgentRunsResponse")
    assert got["rows"] and all(set(r) == fields_of(types, "AgentRun") for r in got["rows"])
    names = {ba_agent.SCORE_AGENT, ba_agent.QUESTIONS_AGENT, brd_generator.AGENT, verifier.QUESTIONS_AGENT, verifier.JUDGE_AGENT, guardian_llm.AGENT, strategist.AGENT}
    labelled = set(re.findall(r'^  ([A-Z_]+): "', block(read("lib/audit.ts"), "export const AGENT_LABELS"), re.M))
    assert labelled == names
    assert client.get(f"/api/projects/{pid}/agent-runs").status_code in (401, 403)           # members only


def test_the_audit_result_words_cover_every_status_the_adapter_writes():
    source = (Path(__file__).resolve().parents[1] / "app" / "agents" / "llm_adapter.py").read_text(encoding="utf-8")
    written = set(re.findall(r'"(SCHEMA_INVALID|ERROR|OK|REPLAYED)"', source))
    shown = set(re.findall(r'^  ([A-Z_]+): \{ label:', block(read("lib/audit.ts"), "export const RUN_STATUS"), re.M))
    assert shown == written == {"OK", "REPLAYED", "SCHEMA_INVALID", "ERROR"}


def test_the_audit_refresh_rate_is_gentle():
    assert re.search(r"AUDIT_REFRESH_MS = 20000;", read("lib/audit.ts"))


def test_the_plan_types_match_real_responses_and_the_words_cover_every_state(client, db, seeded):  # noqa: F811
    from app.services import guardian_rules as g
    from app.services.guardian_tamper import MUTATIONS
    types = read("lib/types.ts")
    pid = seeded["payout_ready_project_id"]
    headers = auth_header(client)
    listing = client.get(f"/api/projects/{pid}/plans", headers=headers).json()
    assert set(listing) == fields_of(types, "PlansResponse") and listing["plans"]
    assert all(set(p) == fields_of(types, "PlanListItem") for p in listing["plans"])
    detail = client.get(f"/api/plans/{listing['plans'][0]['id']}", headers=headers).json()
    declared = fields_of(types, "PlanDetail") | fields_of(types, "PlanListItem")
    assert set(detail) <= declared and declared - set(detail) <= {"earliest_honor_until"}
    assert detail["steps"] and all(set(s) == fields_of(types, "PlanStep") for s in detail["steps"])
    built = client.post(f"/api/projects/{pid}/plans", json={"kind": "FREELANCER_PAYOUT"}, headers=headers)
    assert built.status_code == 201, built.text
    assert set(built.json()) - {"earliest_honor_until"} <= declared
    plan_ids = [built.json()["id"]]
    # a real Guardian review, so its shape is checked too
    from tests.factories import FakeReader
    from app.main import app
    from app.services import paypal_io
    from app.agents.guardian_llm import GuardianLLM, get_guardian_llm
    app.dependency_overrides[paypal_io.get_reader] = lambda: FakeReader(db)
    app.dependency_overrides[get_guardian_llm] = lambda: GuardianLLM(None)          # no model: the AI review is "unavailable"
    try:
        reviewed = client.post(f"/api/plans/{plan_ids[0]}/review", headers=headers)
    finally:
        app.dependency_overrides.pop(paypal_io.get_reader, None)
        app.dependency_overrides.pop(get_guardian_llm, None)
    assert reviewed.status_code == 200, reviewed.text
    shown = reviewed.json()
    assert shown["reviews"] and all(set(r) == fields_of(types, "GuardianReview") for r in shown["reviews"])
    assert shown["reviews"][0]["rules"] and all(set(r) == fields_of(types, "GuardianRule") for r in shown["reviews"][0]["rules"])

    # the words
    plans_ts = read("lib/plans.ts")
    assert keys_of(block(plans_ts, "export const PLAN_STATES")) == {"PROPOSED", "REVIEWED", "APPROVED", "EXECUTING", "DONE", "PARTIAL", "FAILED", "BLOCKED"}
    assert keys_of(block(plans_ts, "export const STEP_STATES")) == {"PENDING", "SENT", "CONFIRMED", "FAILED"}
    assert set(re.findall(r'\b([A-Z_]{6,}): "', block(plans_ts, "export const OP_WORDS"))) == set(g.BUCKET_FOR_OP)
    assert set(re.findall(r"^  ([A-Z_]+): \{ symbol", block(plans_ts, "export const RULE_STATUS"), re.M)) == {g.PASS, g.FAIL, g.UNVERIFIED, g.SKIPPED}
    assert set(re.findall(r"^  ([A-Z_]+): \{ label", block(plans_ts, "export const DECISIONS"), re.M)) == {"ALLOW", "HOLD", "BLOCK"}
    tampers = dict(re.findall(r'^  ([A-Z_]+): \{ kind: "([A-Z_]+)"', block(plans_ts, "export const TAMPERS"), re.M))
    assert tampers == {name: kind for name, (kind, _) in MUTATIONS.items()}
    catches = {m.group(1): set(re.findall(r'"(G-\d\d)"', m.group(2))) for m in re.finditer(r'^  ([A-Z_]+): \{ kind: "[A-Z_]+", label: "[^"]*", catches: \[([^\]]*)\]', block(plans_ts, "export const TAMPERS"), re.M)}
    assert catches == {name: expected for name, (_, expected) in MUTATIONS.items()}


def test_plan_refresh_is_gentle_and_the_plan_kinds_have_words():
    plans_ts = read("lib/plans.ts")
    assert re.search(r"PLAN_REFRESH_MS = 5000;", plans_ts)
    from app.services.guardian_rules import APPLICABLE
    kinds = set(re.findall(r'\b([A-Z_]{6,}): "', block(plans_ts, "export const PLAN_WORDS")))
    assert kinds == set(APPLICABLE) - {"REAUTH_PLEDGES"}                    # reauthorisation plans are not built yet
