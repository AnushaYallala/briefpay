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


def fields_of(type_source: str, name: str) -> set[str]:
    """Field names of `export type NAME = { ... };`, whether it is written on one line or many."""
    start = type_source.index(f"export type {name} = {{") + len(f"export type {name} = {{")
    body = type_source[start: type_source.index("};", start)]
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
