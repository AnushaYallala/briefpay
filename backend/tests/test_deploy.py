"""Deployment (T-61): the production start-up checks, render.yaml, and that every list of settings agrees with the code."""
import asyncio
import re
from pathlib import Path

import pytest
import yaml

from app import startup_checks as sc
from app.config import Settings, get_settings

REPO = Path(__file__).resolve().parents[2]
RENDER = REPO / "render.yaml"
SECRET = "S3cr3t-value-that-must-never-be-logged-0123456789"


def prod(**over) -> Settings:
    """A healthy production configuration; tests break one thing at a time."""
    base = dict(app_env="prod", jwt_secret="j" * 40, database_url="postgresql+psycopg://u:" + SECRET + "@db.example.com:5432/d?sslmode=require",
                database_ssl_ca="/etc/secrets/ca.pem", paypal_env="sandbox", paypal_client_id="id", paypal_client_secret=SECRET, paypal_webhook_id="WH-1",
                gemini_api_key=SECRET, ai_model="m", image_provider="cloudinary", cloudinary_url="cloudinary://k:" + SECRET + "@c", demo_mode=False,
                app_base_url="https://api.example.com", web_base_url="https://web.example.com", cors_origins="https://web.example.com")
    base.update(over)
    return Settings(_env_file=None, **base)


def codes(s, level=None):
    return sorted(f.code for f in sc.check(s) if level is None or f.level == level)


# =============================== start-up checks ===============================

def test_a_healthy_production_configuration_has_no_findings():
    assert sc.check(prod()) == []
    assert sc.enforce(prod()) == []


@pytest.mark.parametrize("over,code", [
    ({"jwt_secret": "change-me"}, "WEAK_JWT_SECRET"), ({"jwt_secret": "short"}, "WEAK_JWT_SECRET"), ({"jwt_secret": "x" * 31}, "WEAK_JWT_SECRET"),
    ({"database_url": "sqlite:///./x.db"}, "SQLITE_IN_PRODUCTION"),
    ({"paypal_env": "live"}, "NOT_SANDBOX"), ({"paypal_env": ""}, "NOT_SANDBOX"),
    ({"paypal_client_secret": ""}, "HALF_PAYPAL_CREDENTIALS"), ({"paypal_client_id": ""}, "HALF_PAYPAL_CREDENTIALS"),
    ({"image_provider": "cloudinary", "cloudinary_url": ""}, "NO_CLOUDINARY_URL"),
])
def test_each_unsafe_setting_is_an_error(over, code):
    assert code in codes(prod(**over), "ERROR")


def test_a_32_character_secret_is_long_enough():
    assert "WEAK_JWT_SECRET" not in codes(prod(jwt_secret="x" * 32))


@pytest.mark.parametrize("over,code", [
    ({"paypal_webhook_id": ""}, "NO_WEBHOOK_ID"), ({"paypal_client_id": "", "paypal_client_secret": ""}, "NO_PAYPAL"),
    ({"image_provider": "local"}, "LOCAL_IMAGES"), ({"gemini_api_key": ""}, "NO_GEMINI_KEY"), ({"demo_mode": True}, "DEMO_MODE"),
    ({"app_base_url": "http://localhost:8000"}, "LOCAL_APP_BASE_URL"), ({"web_base_url": "http://127.0.0.1:3000"}, "LOCAL_WEB_BASE_URL"),
    ({"cors_origins": "http://localhost:3000"}, "CORS_LOCAL_ONLY"),
])
def test_each_weakness_is_only_a_warning(over, code):
    s = prod(**over)
    assert code in codes(s, "WARNING") and codes(s, "ERROR") == []
    assert sc.enforce(s)                                           # warnings never stop the start


def test_replay_mode_does_not_need_a_gemini_key_and_cors_with_a_real_origin_is_fine():
    assert "NO_GEMINI_KEY" not in codes(prod(ai_provider="replay", gemini_api_key=""))
    assert "CORS_LOCAL_ONLY" not in codes(prod(cors_origins="http://localhost:3000,https://web.example.com"))


def test_production_refuses_to_start_on_any_error_and_lists_them_all():
    bad = prod(jwt_secret="change-me", database_url="sqlite:///x.db", paypal_env="live")
    with pytest.raises(sc.ConfigError) as e:
        sc.enforce(bad)
    text = str(e.value)
    assert all(c in text for c in ("WEAK_JWT_SECRET", "SQLITE_IN_PRODUCTION", "NOT_SANDBOX"))


def test_outside_production_errors_are_logged_but_do_not_stop_anything(caplog):
    s = prod(app_env="dev", jwt_secret="change-me", database_url="sqlite:///x.db")
    with caplog.at_level("WARNING", logger="briefpay.startup"):
        findings = sc.enforce(s)
    assert {f.code for f in findings} >= {"WEAK_JWT_SECRET", "SQLITE_IN_PRODUCTION"}
    assert any("WEAK_JWT_SECRET" in r.message for r in caplog.records)


def test_no_message_ever_contains_a_secret_value():
    s = prod(jwt_secret="change-me", database_url="sqlite:///x.db", paypal_env="live", paypal_webhook_id="", demo_mode=True,
             image_provider="local", app_base_url="http://localhost:8000")
    for f in sc.check(s):
        assert SECRET not in f.message
    with pytest.raises(sc.ConfigError) as e:
        sc.enforce(prod(jwt_secret="change-me", cloudinary_url="", paypal_client_secret=""))
    assert SECRET not in str(e.value)


def test_the_app_refuses_to_start_in_production_with_a_bad_configuration(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "settings", prod(jwt_secret="change-me"))

    async def start():
        async with main.lifespan(main.app):
            pass
    with pytest.raises(sc.ConfigError):
        asyncio.run(start())


def test_the_default_development_settings_start_fine():
    assert sc.enforce(get_settings().model_copy(update={"app_env": "dev"})) is not None


# =============================== render.yaml ===============================

@pytest.fixture(scope="module")
def blueprint():
    return yaml.safe_load(RENDER.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def api(blueprint):
    return next(s for s in blueprint["services"] if s["name"] == "briefpay-api")


def env(api):
    return {e["key"]: e for e in api["envVars"]}


def test_the_api_service_is_a_free_python_web_service_that_migrates_then_serves(api):
    assert (api["type"], api["runtime"], api["plan"], api["rootDir"]) == ("web", "python", "free", "backend")
    assert api["buildCommand"] == "pip install -r requirements.txt"
    assert api["startCommand"] == "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    assert api["healthCheckPath"] == "/api/healthz"


def test_the_health_check_path_is_a_real_route(client):
    assert client.get("/api/healthz").status_code == 200


def test_the_python_version_asked_for_is_the_one_we_test_with():
    import sys
    wanted = next(e["value"] for e in yaml.safe_load(RENDER.read_text(encoding="utf-8"))["services"][0]["envVars"] if e["key"] == "PYTHON_VERSION")
    assert wanted.startswith(f"{sys.version_info.major}.{sys.version_info.minor}")


def test_the_blueprint_fixes_the_safe_settings(api):
    e = env(api)
    assert (e["APP_ENV"]["value"], e["PAYPAL_ENV"]["value"], e["IMAGE_PROVIDER"]["value"], e["DEMO_MODE"]["value"]) == ("prod", "sandbox", "cloudinary", "true")
    assert e["JWT_SECRET"] == {"key": "JWT_SECRET", "generateValue": True}


def test_every_secret_is_typed_in_the_dashboard_never_written_in_the_file(api):
    secrets = ["DATABASE_URL", "PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID", "GEMINI_API_KEY", "CLOUDINARY_URL", "GITHUB_TOKEN"]
    e = env(api)
    for key in secrets:
        assert e[key] == {"key": key, "sync": False}, key
    text = RENDER.read_text(encoding="utf-8")
    for pattern in (r"cloudinary://", r"postgres(ql)?(\+\w+)?://", r"AIza[0-9A-Za-z_-]{10,}", r"-----BEGIN", r"ghp_[0-9A-Za-z]{10,}"):
        assert not re.search(pattern, text), pattern


def test_every_variable_in_the_blueprint_is_a_real_setting(api):
    fields = {n.upper() for n in Settings.model_fields}
    unknown = [k for k in env(api) if k not in fields and k != "PYTHON_VERSION"]
    assert unknown == []


def test_the_blueprint_settings_pass_the_production_checks_once_the_dashboard_values_are_filled_in(api):
    values = {k: v["value"] for k, v in env(api).items() if "value" in v and k != "PYTHON_VERSION"}
    values.update(JWT_SECRET="g" * 48, DATABASE_URL="postgresql+psycopg://u:p@db.example.com/d?sslmode=require", PAYPAL_CLIENT_ID="i", PAYPAL_CLIENT_SECRET="s",
                  PAYPAL_WEBHOOK_ID="w", GEMINI_API_KEY="g", CLOUDINARY_URL="cloudinary://k:s@c", APP_BASE_URL="https://api.example.com",
                  WEB_BASE_URL="https://web.example.com", CORS_ORIGINS="https://web.example.com")
    s = Settings(_env_file=None, **{k.lower(): v for k, v in values.items()})
    assert [f for f in sc.check(s) if f.level == "ERROR"] == []


# =============================== the lists agree ===============================

def example_keys() -> list[str]:
    keys = []
    for line in (REPO / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("# ---------- frontend"):
            break
        m = re.match(r"^([A-Z][A-Z0-9_]*)=", line)
        if m:
            keys.append(m.group(1))
    return keys


def test_env_example_lists_exactly_the_backend_settings():
    fields = {n.upper() for n in Settings.model_fields}
    keys = example_keys()
    assert sorted(set(fields) - set(keys)) == [] and sorted(set(keys) - set(fields)) == []
    assert len(keys) == len(set(keys))


def test_spec_section_14_3_lists_every_backend_setting():
    spec = (REPO / "docs" / "SPEC.md").read_text(encoding="utf-8")
    section = spec[spec.index("### 14.3 Environment variables"):]
    section = section[:section.index("```", section.index("```") + 3)]
    listed = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", section, re.M))
    missing = {n.upper() for n in Settings.model_fields} - listed
    assert missing == set()


def test_the_deploy_guide_names_every_dashboard_value_and_every_webhook_event_we_handle():
    guide = (REPO / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
    blueprint = yaml.safe_load(RENDER.read_text(encoding="utf-8"))
    for svc in blueprint["services"]:
        for e in svc["envVars"]:
            if e.get("sync") is False:
                assert e["key"] in guide, e["key"]
    source = (REPO / "backend" / "app" / "services" / "webhook_processing.py").read_text(encoding="utf-8")
    events = set(re.findall(r'"((?:PAYMENT|CHECKOUT)\.[A-Z.\-]+[A-Z])"', source))
    assert events >= {"PAYMENT.CAPTURE.COMPLETED", "PAYMENT.AUTHORIZATION.VOIDED", "CHECKOUT.ORDER.APPROVED"}
    for ev in events:
        assert ev in guide, ev
    assert "PAYMENT.PAYOUTS-ITEM.*" in guide and "PAYMENT.PAYOUTSBATCH.*" in guide


def test_the_web_service_is_a_static_site_built_from_the_frontend(blueprint):
    web = next(s for s in blueprint["services"] if s["name"] == "briefpay-web")
    assert (web["type"], web["runtime"], web["rootDir"], web["staticPublishPath"]) == ("web", "static", "frontend", "out")
    assert web["buildCommand"] == "npm ci && npm run build"
    keys = {e["key"]: e for e in web["envVars"]}
    assert keys["NEXT_PUBLIC_DEMO_MODE"]["value"] == "true"
    assert all(k.startswith("NEXT_PUBLIC_") for k in keys), "only public values belong in the browser bundle: no secret may be named here"
    assert keys["NEXT_PUBLIC_API_BASE_URL"] == {"key": "NEXT_PUBLIC_API_BASE_URL", "sync": False}


def test_ci_checks_both_halves_on_the_versions_we_ship():
    ci = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    assert sorted(ci["jobs"]) == ["backend", "frontend"]
    import sys
    py = next(s for s in ci["jobs"]["backend"]["steps"] if s.get("uses", "").startswith("actions/setup-python"))["with"]["python-version"]
    assert py == f"{sys.version_info.major}.{sys.version_info.minor}"
    node = next(s for s in ci["jobs"]["frontend"]["steps"] if s.get("uses", "").startswith("actions/setup-node"))["with"]["node-version"]
    assert node == "22"
    runs = [s["run"] for s in ci["jobs"]["frontend"]["steps"] if "run" in s]
    assert runs == ["npm ci", "npm run typecheck", "npm test", "npm run build"]
