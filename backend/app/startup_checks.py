"""Refuse to start in production with a configuration that would be unsafe or silently broken (T-61, closes GAP-57).

`APP_ENV=prod` means "a real host": a default or short JWT secret would let anyone forge a login token, a SQLite file on a free
host disappears on every restart, and this build only ever talks to the PayPal sandbox. Those are errors and stop the start.
Things that merely weaken the demo (no Gemini key, local images, no webhook id, open demo endpoints) are warnings in the log.
Messages never contain a secret value.
"""
import logging
from dataclasses import dataclass

log = logging.getLogger("briefpay.startup")

MIN_SECRET_LENGTH = 32
LOCAL_MARKERS = ("localhost", "127.0.0.1")


class ConfigError(Exception):
    """The configuration is not safe to run in production."""


@dataclass(frozen=True)
class Finding:
    level: str          # ERROR | WARNING
    code: str
    message: str


def _local(url: str) -> bool:
    return any(m in (url or "").lower() for m in LOCAL_MARKERS)


def check(s) -> list[Finding]:
    """Every problem with these settings. Pure: it only reads the settings it is given."""
    out: list[Finding] = []

    def err(code, msg):
        out.append(Finding("ERROR", code, msg))

    def warn(code, msg):
        out.append(Finding("WARNING", code, msg))

    if s.jwt_secret == "change-me" or len(s.jwt_secret or "") < MIN_SECRET_LENGTH:
        err("WEAK_JWT_SECRET", f"JWT_SECRET must be set to a random value of at least {MIN_SECRET_LENGTH} characters (anyone could forge a login otherwise)")
    if (s.database_url or "").startswith("sqlite"):
        err("SQLITE_IN_PRODUCTION", "DATABASE_URL points to SQLite; a free host has no persistent disk, so all data would vanish on restart. Use PostgreSQL")
    if s.paypal_env != "sandbox":
        err("NOT_SANDBOX", "PAYPAL_ENV must be 'sandbox': this build never handles real money")
    if (s.paypal_client_id or s.paypal_client_secret) and not (s.paypal_client_id and s.paypal_client_secret):
        err("HALF_PAYPAL_CREDENTIALS", "set both PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET, or neither")
    if s.paypal_client_id and not s.paypal_webhook_id:
        warn("NO_WEBHOOK_ID", "PAYPAL_WEBHOOK_ID is empty: every PayPal webhook will be refused with 503 (the poll fallback still confirms steps)")
    if not s.paypal_client_id:
        warn("NO_PAYPAL", "PayPal is not configured: no pledge can be taken and no money plan can run")
    if s.image_provider.lower() == "local":
        warn("LOCAL_IMAGES", "IMAGE_PROVIDER=local: screenshots are stored on the host's disk and disappear on restart; use cloudinary")
    elif s.image_provider.lower() == "cloudinary" and not s.cloudinary_url:
        err("NO_CLOUDINARY_URL", "IMAGE_PROVIDER=cloudinary needs CLOUDINARY_URL")
    if s.ai_provider != "replay" and not s.gemini_api_key:
        warn("NO_GEMINI_KEY", "GEMINI_API_KEY is empty: the AI agents are unavailable (questions fall back to templates; scoring and judging report 503)")
    if s.demo_mode:
        warn("DEMO_MODE", "DEMO_MODE is on: persona switching, the reconcile report and the tamper simulation are open to any signed-in user (fine for the hackathon demo)")
    if _local(s.app_base_url):
        warn("LOCAL_APP_BASE_URL", "APP_BASE_URL still points to localhost: upload and view links would be wrong")
    if _local(s.web_base_url):
        warn("LOCAL_WEB_BASE_URL", "WEB_BASE_URL still points to localhost")
    if any(_local(o) for o in s.cors_origin_list) and not any(not _local(o) for o in s.cors_origin_list):
        warn("CORS_LOCAL_ONLY", "CORS_ORIGINS only lists localhost: the deployed web app will be blocked")
    return out


def enforce(s, logger: logging.Logger | None = None) -> list[Finding]:
    """Log every finding; in production raise ConfigError if any is an ERROR. Elsewhere (dev, tests) nothing is raised."""
    logger = logger or log
    findings = check(s)
    for f in findings:
        (logger.error if f.level == "ERROR" else logger.warning)("%s: %s", f.code, f.message)
    errors = [f for f in findings if f.level == "ERROR"]
    if errors and s.app_env == "prod":
        raise ConfigError("unsafe production configuration: " + "; ".join(f"{f.code}: {f.message}" for f in errors))
    return findings
